#!/usr/bin/env python3
"""Unit tests for scripts/qrz.py (run: python3 -m unittest discover scripts)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qrz import (
    QRZAuthError,
    QRZClient,
    QRZError,
    QRZNotFound,
    base_callsign,
    cache_entry,
    parse_response,
)

LOGIN_OK = """<?xml version="1.0" encoding="utf-8"?>
<QRZDatabase version="1.34" xmlns="http://xmldata.qrz.com">
  <Session>
    <Key>abcd1234abcd1234abcd1234abcd1234</Key>
    <Count>123</Count>
    <SubExp>Wed Jan 1 12:34:03 2027</SubExp>
    <GMTime>Mon Jul  6 12:00:00 2026</GMTime>
  </Session>
</QRZDatabase>
"""

LOGIN_BAD = """<?xml version="1.0" encoding="utf-8"?>
<QRZDatabase version="1.34" xmlns="http://xmldata.qrz.com">
  <Session>
    <Error>Username/password incorrect</Error>
    <GMTime>Mon Jul  6 12:00:00 2026</GMTime>
  </Session>
</QRZDatabase>
"""

# Lookup of a callsign that has NOT changed.
LOOKUP_W6JSV = """<?xml version="1.0" encoding="utf-8"?>
<QRZDatabase version="1.34" xmlns="http://xmldata.qrz.com">
  <Callsign>
    <call>W6JSV</call>
    <fname>Jay</fname>
    <name>V</name>
    <state>CA</state>
    <country>United States</country>
    <dxcc>291</dxcc>
  </Callsign>
  <Session>
    <Key>abcd1234abcd1234abcd1234abcd1234</Key>
    <GMTime>Mon Jul  6 12:00:00 2026</GMTime>
  </Session>
</QRZDatabase>
"""

# Lookup of KI5GTR after Les changed to NQ5A: QRZ merges the records and
# answers with the current callsign, listing the old one under aliases.
LOOKUP_KI5GTR_MERGED = """<?xml version="1.0" encoding="utf-8"?>
<QRZDatabase version="1.34" xmlns="http://xmldata.qrz.com">
  <Callsign>
    <call>NQ5A</call>
    <aliases>KI5GTR</aliases>
    <fname>Les</fname>
    <name>D</name>
    <state>TX</state>
    <country>United States</country>
    <dxcc>291</dxcc>
  </Callsign>
  <Session>
    <Key>abcd1234abcd1234abcd1234abcd1234</Key>
    <GMTime>Mon Jul  6 12:00:00 2026</GMTime>
  </Session>
</QRZDatabase>
"""

LOOKUP_NOT_FOUND = """<?xml version="1.0" encoding="utf-8"?>
<QRZDatabase version="1.34" xmlns="http://xmldata.qrz.com">
  <Session>
    <Key>abcd1234abcd1234abcd1234abcd1234</Key>
    <Error>Not found: XX9XXX</Error>
    <GMTime>Mon Jul  6 12:00:00 2026</GMTime>
  </Session>
</QRZDatabase>
"""

SESSION_TIMEOUT = """<?xml version="1.0" encoding="utf-8"?>
<QRZDatabase version="1.34" xmlns="http://xmldata.qrz.com">
  <Session>
    <Error>Session Timeout</Error>
    <GMTime>Mon Jul  6 12:00:00 2026</GMTime>
  </Session>
</QRZDatabase>
"""


class FakeFetch:
    """Scripted fetcher: pops one canned response per request."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, params):
        self.requests.append(params)
        return self.responses.pop(0)


def make_client(*responses):
    return QRZClient("user", "pass", fetch=FakeFetch(responses))


class TestBaseCallsign(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(base_callsign("NQ5A"), "NQ5A")

    def test_suffix(self):
        self.assertEqual(base_callsign("W6JY/P"), "W6JY")

    def test_prefix(self):
        self.assertEqual(base_callsign("DL/K1ABC"), "K1ABC")


class TestParseResponse(unittest.TestCase):
    def test_session_only(self):
        session, record = parse_response(LOGIN_OK)
        self.assertEqual(session["Key"], "abcd1234abcd1234abcd1234abcd1234")
        self.assertIsNone(record)

    def test_record_fields(self):
        _, record = parse_response(LOOKUP_KI5GTR_MERGED)
        self.assertEqual(record.call, "NQ5A")
        self.assertEqual(record.aliases, ["KI5GTR"])
        self.assertEqual(record.state, "TX")
        self.assertEqual(record.fields["fname"], "Les")


class TestLogin(unittest.TestCase):
    def test_success(self):
        client = make_client(LOGIN_OK)
        self.assertEqual(client.login(), "abcd1234abcd1234abcd1234abcd1234")

    def test_bad_credentials(self):
        client = make_client(LOGIN_BAD)
        with self.assertRaises(QRZAuthError):
            client.login()

    def test_missing_credentials(self):
        with self.assertRaises(QRZAuthError):
            QRZClient("", "")

    def test_from_env_absent(self):
        os.environ.pop("QRZ_USERNAME", None)
        os.environ.pop("QRZ_PASSWORD", None)
        self.assertIsNone(QRZClient.from_env())


class TestLookup(unittest.TestCase):
    def test_logs_in_first(self):
        client = make_client(LOGIN_OK, LOOKUP_W6JSV)
        record = client.lookup("w6jsv")
        self.assertEqual(record.call, "W6JSV")
        self.assertEqual(record.state, "CA")

    def test_not_found(self):
        client = make_client(LOGIN_OK, LOOKUP_NOT_FOUND)
        with self.assertRaises(QRZNotFound):
            client.lookup("XX9XXX")

    def test_session_timeout_retries_once(self):
        client = make_client(LOGIN_OK, SESSION_TIMEOUT, LOGIN_OK, LOOKUP_W6JSV)
        record = client.lookup("W6JSV")
        self.assertEqual(record.call, "W6JSV")

    def test_persistent_timeout_raises(self):
        client = make_client(LOGIN_OK, SESSION_TIMEOUT, LOGIN_OK, SESSION_TIMEOUT)
        with self.assertRaises(QRZError):
            client.lookup("W6JSV")


class TestResolve(unittest.TestCase):
    def test_unchanged_callsign(self):
        client = make_client(LOGIN_OK, LOOKUP_W6JSV)
        res = client.resolve("W6JSV")
        self.assertFalse(res.changed)
        self.assertEqual(res.current, "W6JSV")

    def test_changed_callsign_ki5gtr_to_nq5a(self):
        client = make_client(LOGIN_OK, LOOKUP_KI5GTR_MERGED)
        res = client.resolve("KI5GTR")
        self.assertTrue(res.changed)
        self.assertEqual(res.queried, "KI5GTR")
        self.assertEqual(res.current, "NQ5A")
        self.assertIn("KI5GTR", res.record.aliases)

    def test_portable_suffix_not_a_change(self):
        client = make_client(LOGIN_OK, LOOKUP_W6JSV)
        res = client.resolve("W6JSV/P")
        self.assertFalse(res.changed)
        # The lookup itself was for the base call.
        self.assertEqual(client._fetch.requests[-1]["callsign"], "W6JSV")


class TestCacheEntry(unittest.TestCase):
    def test_includes_current_call_and_aliases(self):
        _, record = parse_response(LOOKUP_KI5GTR_MERGED)
        entry = cache_entry(record)
        self.assertEqual(entry["call"], "NQ5A")
        self.assertEqual(entry["state"], "TX")
        self.assertEqual(entry["aliases"], ["KI5GTR"])

    def test_omits_empty_fields(self):
        _, record = parse_response(LOOKUP_W6JSV)
        entry = cache_entry(record)
        self.assertNotIn("aliases", entry)
        self.assertEqual(entry["call"], "W6JSV")


if __name__ == "__main__":
    unittest.main()
