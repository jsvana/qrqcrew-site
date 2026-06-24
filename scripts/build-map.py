#!/usr/bin/env python3
"""Build data/locations.json for the QRQ Crew presence map.

Country illumination is derived directly from each member's callsign prefix
(DXCC), so the map works with zero configuration. If QRZ XML API credentials
are available (env vars QRZ_USERNAME / QRZ_PASSWORD), member QTH states/
provinces are looked up as well and cached in data/qrz_cache.json so we only
query callsigns we haven't seen before.

The output is presence-only ("illumination, no quantity bias"): a region is
either lit or it isn't -- we never expose member counts.
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMBERS_FILE = os.path.join(ROOT, "members.txt")
OUTPUT_FILE = os.path.join(ROOT, "data", "locations.json")
CACHE_FILE = os.path.join(ROOT, "data", "qrz_cache.json")

QRZ_AGENT = "qrqcrew-map/1.0"
QRZ_BASE = "https://xmldata.qrz.com/xml/current/"

# ISO 3166-1: alpha-2 -> (numeric "ccn3", display name).
# ccn3 is what the world-atlas TopoJSON uses as its feature id, so the map
# matches on the numeric code and is immune to country-name spelling drift.
ISO = {
    "US": ("840", "United States"),
    "CA": ("124", "Canada"),
    "MX": ("484", "Mexico"),
    "DE": ("276", "Germany"),
    "GB": ("826", "United Kingdom"),
    "FR": ("250", "France"),
    "IT": ("380", "Italy"),
    "ES": ("724", "Spain"),
    "PT": ("620", "Portugal"),
    "AT": ("040", "Austria"),
    "AL": ("008", "Albania"),
    "CO": ("170", "Colombia"),
    "JP": ("392", "Japan"),
    "AU": ("036", "Australia"),
    "NL": ("528", "Netherlands"),
    "BE": ("056", "Belgium"),
    "CH": ("756", "Switzerland"),
    "SE": ("752", "Sweden"),
    "NO": ("578", "Norway"),
    "FI": ("246", "Finland"),
    "DK": ("208", "Denmark"),
    "PL": ("616", "Poland"),
    "CZ": ("203", "Czechia"),
    "IE": ("372", "Ireland"),
    "RU": ("643", "Russia"),
    "UA": ("804", "Ukraine"),
    "BR": ("076", "Brazil"),
    "AR": ("032", "Argentina"),
    "CL": ("152", "Chile"),
    "NZ": ("554", "New Zealand"),
    "ZA": ("710", "South Africa"),
    "CN": ("156", "China"),
    "KR": ("410", "South Korea"),
    "IN": ("356", "India"),
}

# Callsign prefix -> ISO alpha-2. Matched longest-first (3, then 2, then 1
# leading characters). This is a pragmatic DXCC table covering current members
# plus common DX entities; QRZ (when configured) is authoritative and overrides.
PREFIX_COUNTRY = {}


def _add_prefixes(iso2, prefixes):
    for p in prefixes:
        PREFIX_COUNTRY[p] = iso2


# United States: AA-AL, K, N, W
_add_prefixes("US", ["AA", "AB", "AC", "AD", "AE", "AF", "AG", "AH",
                     "AI", "AJ", "AK", "AL", "K", "N", "W"])
# Canada
_add_prefixes("CA", ["VA", "VE", "VO", "VY", "VX", "CF", "CG", "CH",
                     "CI", "CJ", "CK", "CY", "CZ"])
# Mexico
_add_prefixes("MX", ["XA", "XB", "XC", "XD", "XE", "XF", "XG", "XH", "XI"])
# Germany
_add_prefixes("DE", ["DA", "DB", "DC", "DD", "DF", "DG", "DH", "DJ", "DK",
                     "DL", "DM", "DN", "DO", "DP", "DQ", "DR"])
# United Kingdom
_add_prefixes("GB", ["G", "M", "2E"])
# France
_add_prefixes("FR", ["F"])
# Italy
_add_prefixes("IT", ["I"])
# Spain
_add_prefixes("ES", ["EA", "EB", "EC", "ED", "EE", "EF", "EG", "EH"])
# Portugal
_add_prefixes("PT", ["CT", "CR", "CS", "CQ"])
# Austria
_add_prefixes("AT", ["OE"])
# Albania
_add_prefixes("AL", ["ZA"])
# Colombia
_add_prefixes("CO", ["HK", "HJ", "5J", "5K"])
# Japan
_add_prefixes("JP", ["JA", "JE", "JF", "JG", "JH", "JI", "JJ", "JK", "JL",
                     "JM", "JN", "JO", "JP", "JQ", "JR", "JS", "7J", "7K",
                     "7L", "7M", "7N", "8J"])
# Australia
_add_prefixes("AU", ["VK", "AX"])
# A handful of other common DX entities for future members
_add_prefixes("NL", ["PA", "PB", "PC", "PD", "PE", "PF", "PG", "PH", "PI"])
_add_prefixes("BE", ["ON", "OO", "OP", "OQ", "OR", "OS", "OT"])
_add_prefixes("CH", ["HB"])
_add_prefixes("SE", ["SA", "SB", "SC", "SD", "SE", "SF", "SG", "SH", "SI",
                     "SJ", "SK", "SL", "SM"])
_add_prefixes("NO", ["LA", "LB", "LC", "LD", "LE", "LF", "LG", "LH", "LI",
                     "LJ", "LK", "LL", "LM", "LN"])
_add_prefixes("FI", ["OF", "OG", "OH", "OI"])
_add_prefixes("DK", ["OU", "OV", "OW", "OX", "OY", "OZ"])
_add_prefixes("PL", ["SN", "SO", "SP", "SQ", "SR"])
_add_prefixes("CZ", ["OK", "OL"])
_add_prefixes("IE", ["EI", "EJ"])
_add_prefixes("RU", ["R", "UA", "UB", "UC", "UD", "UE", "UF", "UG", "UH", "UI"])
_add_prefixes("UA", ["UR", "US", "UT", "UU", "UV", "UW", "UX", "UY", "UZ",
                     "EM", "EN", "EO"])
_add_prefixes("BR", ["PP", "PQ", "PR", "PS", "PT", "PU", "PV", "PW", "PX", "PY"])
_add_prefixes("AR", ["LU", "LV", "LW", "AY", "AZ"])
# Chile uses CA-CE; Canada in our roster uses VA/VE (added above), so the
# C-block belongs to Chile. CT (Portugal) is re-asserted afterwards in case the
# CT-prefixed Portuguese block was touched.
_add_prefixes("CL", ["CA", "CB", "CC", "CD", "CE"])
_add_prefixes("NZ", ["ZL", "ZM"])
_add_prefixes("ZA", ["ZR", "ZS", "ZT", "ZU"])
PREFIX_COUNTRY["CT"] = "PT"

# USPS state/territory code -> (FIPS id used by us-atlas TopoJSON, display name)
US_STATES = {
    "AL": ("01", "Alabama"), "AK": ("02", "Alaska"), "AZ": ("04", "Arizona"),
    "AR": ("05", "Arkansas"), "CA": ("06", "California"), "CO": ("08", "Colorado"),
    "CT": ("09", "Connecticut"), "DE": ("10", "Delaware"),
    "DC": ("11", "District of Columbia"), "FL": ("12", "Florida"),
    "GA": ("13", "Georgia"), "HI": ("15", "Hawaii"), "ID": ("16", "Idaho"),
    "IL": ("17", "Illinois"), "IN": ("18", "Indiana"), "IA": ("19", "Iowa"),
    "KS": ("20", "Kansas"), "KY": ("21", "Kentucky"), "LA": ("22", "Louisiana"),
    "ME": ("23", "Maine"), "MD": ("24", "Maryland"), "MA": ("25", "Massachusetts"),
    "MI": ("26", "Michigan"), "MN": ("27", "Minnesota"), "MS": ("28", "Mississippi"),
    "MO": ("29", "Missouri"), "MT": ("30", "Montana"), "NE": ("31", "Nebraska"),
    "NV": ("32", "Nevada"), "NH": ("33", "New Hampshire"), "NJ": ("34", "New Jersey"),
    "NM": ("35", "New Mexico"), "NY": ("36", "New York"),
    "NC": ("37", "North Carolina"), "ND": ("38", "North Dakota"), "OH": ("39", "Ohio"),
    "OK": ("40", "Oklahoma"), "OR": ("41", "Oregon"), "PA": ("42", "Pennsylvania"),
    "RI": ("44", "Rhode Island"), "SC": ("45", "South Carolina"),
    "SD": ("46", "South Dakota"), "TN": ("47", "Tennessee"), "TX": ("48", "Texas"),
    "UT": ("49", "Utah"), "VT": ("50", "Vermont"), "VA": ("51", "Virginia"),
    "WA": ("53", "Washington"), "WV": ("54", "West Virginia"),
    "WI": ("55", "Wisconsin"), "WY": ("56", "Wyoming"),
}


def parse_members(path):
    """Return list of callsigns from members.txt (skips comments/blank lines)."""
    calls = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            call = line.split()[0].upper()
            if re.match(r"^[A-Z0-9/]+$", call):
                calls.append(call)
    return calls


def base_callsign(call):
    """Strip portable/operating suffixes & prefixes (e.g. W6JY/P, K1ABC/4)."""
    if "/" in call:
        parts = [p for p in call.split("/") if p]
        # Choose the longest part as the "home" call (handles K1ABC/4 and DL/K1ABC)
        parts.sort(key=len, reverse=True)
        return parts[0]
    return call


def country_from_call(call):
    """Resolve ISO alpha-2 country from a callsign prefix, or None."""
    c = base_callsign(call)
    for n in (3, 2, 1):
        iso2 = PREFIX_COUNTRY.get(c[:n])
        if iso2:
            return iso2
    return None


# ---------------------------------------------------------------------------
# QRZ XML API (optional)
# ---------------------------------------------------------------------------

QRZ_NS = "{http://xmldata.qrz.com}"


def _qrz_get(params):
    url = QRZ_BASE + "?" + urllib.parse.urlencode(params, safe=";")
    req = urllib.request.Request(url, headers={"User-Agent": QRZ_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def qrz_login(username, password):
    """Return a QRZ session key, or raise."""
    xml = _qrz_get({"username": username, "password": password, "agent": QRZ_AGENT})
    root = ET.fromstring(xml)
    session = root.find(f"{QRZ_NS}Session")
    if session is None:
        raise RuntimeError("QRZ: no session element in response")
    err = session.find(f"{QRZ_NS}Error")
    if err is not None and err.text:
        raise RuntimeError(f"QRZ login error: {err.text.strip()}")
    key = session.find(f"{QRZ_NS}Key")
    if key is None or not key.text:
        raise RuntimeError("QRZ: login returned no session key")
    return key.text.strip()


def qrz_lookup(session_key, call):
    """Return dict with state/country for a callsign, or {} if not found."""
    xml = _qrz_get({"s": session_key, "callsign": call})
    root = ET.fromstring(xml)
    cs = root.find(f"{QRZ_NS}Callsign")
    if cs is None:
        return {}
    out = {}
    for tag in ("state", "country", "dxcc"):
        el = cs.find(f"{QRZ_NS}{tag}")
        if el is not None and el.text:
            out[tag] = el.text.strip()
    return out


def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    return {}


def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2, sort_keys=True)
        f.write("\n")


def enrich_with_qrz(calls, cache):
    """Look up any callsigns missing from the cache. Returns True if QRZ ran."""
    username = os.environ.get("QRZ_USERNAME")
    password = os.environ.get("QRZ_PASSWORD")
    if not username or not password:
        print("QRZ credentials not set -- skipping state lookup (countries only).")
        return False

    missing = [c for c in calls if c not in cache]
    if not missing:
        print("QRZ: all callsigns cached, nothing to look up.")
        return True

    print(f"QRZ: looking up {len(missing)} new callsign(s)...")
    try:
        key = qrz_login(username, password)
    except Exception as e:  # noqa: BLE001 - fall back to cache/countries
        print(f"QRZ login failed: {e}", file=sys.stderr)
        return False

    for call in missing:
        try:
            cache[call] = qrz_lookup(key, base_callsign(call))
        except Exception as e:  # noqa: BLE001 - record empty, keep going
            print(f"QRZ lookup failed for {call}: {e}", file=sys.stderr)
            cache[call] = {}
        time.sleep(0.3)  # be polite to QRZ
    return True


def build():
    calls = parse_members(MEMBERS_FILE)
    print(f"Parsed {len(calls)} member callsigns")

    cache = load_cache()
    used_qrz = enrich_with_qrz(calls, cache)
    if used_qrz:
        save_cache(cache)

    countries = {}   # ccn3 -> {iso2, ccn3, name}
    states = {}      # fips -> {usps, fips, name}
    unresolved = []

    for call in calls:
        iso2 = country_from_call(call)
        if iso2 and iso2 in ISO:
            ccn3, name = ISO[iso2]
            countries[ccn3] = {"iso2": iso2, "ccn3": ccn3, "name": name}
        else:
            unresolved.append(call)

        # State (US/QRZ only)
        info = cache.get(call) or {}
        st = (info.get("state") or "").upper()
        if st in US_STATES:
            fips, sname = US_STATES[st]
            states[fips] = {"usps": st, "fips": fips, "name": sname}

    if unresolved:
        print(f"WARNING: {len(unresolved)} callsign(s) could not be resolved to a "
              f"country: {', '.join(unresolved)}", file=sys.stderr)

    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "member_count": len(calls),
        "source": "qrz+callsign" if used_qrz else "callsign",
        "countries": sorted(countries.values(), key=lambda c: c["name"]),
        "us_states": sorted(states.values(), key=lambda s: s["name"]),
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")

    print(f"Wrote {OUTPUT_FILE}: "
          f"{len(payload['countries'])} countries, "
          f"{len(payload['us_states'])} US states")
    return 0


if __name__ == "__main__":
    sys.exit(build())
