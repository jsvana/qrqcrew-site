#!/usr/bin/env python3
"""Small QRZ XML API client library with callsign-change detection.

QRZ merges records when an operator receives a new callsign: looking up the
old callsign returns the *current* record, whose <call> element holds the new
callsign and whose <aliases> element lists the previous one(s). Example: after
Les (QC #38) changed KI5GTR -> NQ5A, a lookup of KI5GTR returns call=NQ5A with
KI5GTR in the aliases. This module exposes that as `QRZClient.resolve()`, so
callers can detect and follow callsign changes.

Usage:
    client = QRZClient.from_env()          # QRZ_USERNAME / QRZ_PASSWORD
    res = client.resolve("KI5GTR")
    res.changed  -> True
    res.current  -> "NQ5A"

Network access is injectable (the `fetch` argument) so the library can be
unit-tested without touching qrz.com.
"""

import json
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

QRZ_BASE = "https://xmldata.qrz.com/xml/current/"
QRZ_NS = "{http://xmldata.qrz.com}"
DEFAULT_AGENT = "qrqcrew-site/1.0"

# Session <Error> values that mean "log in again and retry", not "give up".
_SESSION_ERRORS = ("session timeout", "invalid session key")


class QRZError(Exception):
    """Base error for QRZ API problems."""


class QRZAuthError(QRZError):
    """Login failed or credentials missing."""


class QRZNotFound(QRZError):
    """QRZ has no record for the callsign."""


@dataclass
class QRZRecord:
    """One callsign record as returned by QRZ."""

    call: str
    aliases: list = field(default_factory=list)
    fname: str = ""
    name: str = ""
    state: str = ""
    country: str = ""
    dxcc: str = ""
    fields: dict = field(default_factory=dict)  # every raw XML field


@dataclass
class Resolution:
    """Result of resolving a (possibly outdated) callsign."""

    queried: str
    current: str
    changed: bool
    record: QRZRecord


def base_callsign(call):
    """Strip portable prefixes/suffixes (W6JY/P, DL/K1ABC) to the home call."""
    if "/" in call:
        parts = [p for p in call.split("/") if p]
        parts.sort(key=len, reverse=True)
        return parts[0]
    return call


def _default_fetch(params):
    url = QRZ_BASE + "?" + urllib.parse.urlencode(params, safe=";")
    req = urllib.request.Request(
        url, headers={"User-Agent": params.get("agent", DEFAULT_AGENT)}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_response(xml_text):
    """Parse a QRZ XML response into (session_fields, QRZRecord or None)."""
    root = ET.fromstring(xml_text)

    session = {}
    sess_el = root.find(f"{QRZ_NS}Session")
    if sess_el is not None:
        for el in sess_el:
            tag = el.tag.replace(QRZ_NS, "")
            session[tag] = (el.text or "").strip()

    record = None
    cs = root.find(f"{QRZ_NS}Callsign")
    if cs is not None:
        fields = {}
        for el in cs:
            tag = el.tag.replace(QRZ_NS, "")
            fields[tag] = (el.text or "").strip()
        aliases = [a for a in fields.get("aliases", "").replace(";", ",").split(",") if a]
        record = QRZRecord(
            call=fields.get("call", "").upper(),
            aliases=[a.strip().upper() for a in aliases],
            fname=fields.get("fname", ""),
            name=fields.get("name", ""),
            state=fields.get("state", "").upper(),
            country=fields.get("country", ""),
            dxcc=fields.get("dxcc", ""),
            fields=fields,
        )
    return session, record


class QRZClient:
    """Minimal QRZ XML API client (login, lookup, callsign-change resolve)."""

    def __init__(self, username, password, agent=DEFAULT_AGENT, fetch=None):
        if not username or not password:
            raise QRZAuthError("QRZ username and password are required")
        self.username = username
        self.password = password
        self.agent = agent
        self._fetch = fetch or _default_fetch
        self._key = None

    @classmethod
    def from_env(cls, agent=DEFAULT_AGENT, fetch=None):
        """Build a client from QRZ_USERNAME / QRZ_PASSWORD, or return None."""
        username = os.environ.get("QRZ_USERNAME")
        password = os.environ.get("QRZ_PASSWORD")
        if not username or not password:
            return None
        return cls(username, password, agent=agent, fetch=fetch)

    def login(self):
        xml_text = self._fetch(
            {"username": self.username, "password": self.password, "agent": self.agent}
        )
        session, _ = parse_response(xml_text)
        error = session.get("Error")
        if error:
            raise QRZAuthError(f"QRZ login error: {error}")
        key = session.get("Key")
        if not key:
            raise QRZAuthError("QRZ login returned no session key")
        self._key = key
        return key

    def lookup(self, call, _retry=True):
        """Return the QRZRecord for a callsign (follows QRZ merges/aliases)."""
        call = base_callsign(call.strip().upper())
        if self._key is None:
            self.login()
        xml_text = self._fetch({"s": self._key, "callsign": call})
        session, record = parse_response(xml_text)

        error = session.get("Error", "")
        if error:
            if error.lower().startswith("not found"):
                raise QRZNotFound(f"QRZ has no record for {call}")
            if any(s in error.lower() for s in _SESSION_ERRORS) and _retry:
                self._key = None
                return self.lookup(call, _retry=False)
            if record is None:
                raise QRZError(f"QRZ error for {call}: {error}")
        if record is None or not record.call:
            raise QRZError(f"QRZ returned no callsign record for {call}")
        return record

    def resolve(self, call):
        """Look up a callsign and report whether it has been replaced.

        QRZ answers a lookup of a superseded callsign with the current record,
        so a mismatch between the queried call and the returned <call> means
        the operator changed callsigns.
        """
        queried = base_callsign(call.strip().upper())
        record = self.lookup(queried)
        current = record.call
        return Resolution(
            queried=queried,
            current=current,
            changed=current != queried,
            record=record,
        )


# ---------------------------------------------------------------------------
# Shared lookup cache helpers (data/qrz_cache.json)
# ---------------------------------------------------------------------------

def load_cache(path):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    return {}


def save_cache(path, cache):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(cache, f, indent=2, sort_keys=True)
        f.write("\n")


def cache_entry(record):
    """Cache dict for a QRZRecord, including the current call for
    callsign-change detection by later builds."""
    entry = {"call": record.call}
    for key in ("state", "country", "dxcc"):
        value = getattr(record, key)
        if value:
            entry[key] = value
    if record.aliases:
        entry["aliases"] = record.aliases
    return entry
