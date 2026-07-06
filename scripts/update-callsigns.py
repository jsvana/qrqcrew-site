#!/usr/bin/env python3
"""Detect member callsign changes via QRZ and update the member list files.

QRZ merges records when an operator gets a new callsign, so looking up the old
call returns the new one (see scripts/qrz.py). This script checks every
callsign in members.txt against QRZ and rewrites the member files when a
change is found.

Usage:
    python3 scripts/update-callsigns.py               # dry run: report changes
    python3 scripts/update-callsigns.py --apply       # rewrite the files
    python3 scripts/update-callsigns.py --map KI5GTR=NQ5A --apply
                                                      # apply a known change
                                                      # without querying QRZ

Live checks need QRZ_USERNAME / QRZ_PASSWORD in the environment; --map works
offline. Files updated: members.txt, qrqcrew-notes.txt, data/qrz_cache.json.
"""

import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qrz import QRZClient, QRZError, QRZNotFound, load_cache, save_cache

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMBERS_FILE = os.path.join(ROOT, "members.txt")
NOTES_FILE = os.path.join(ROOT, "qrqcrew-notes.txt")
CACHE_FILE = os.path.join(ROOT, "data", "qrz_cache.json")

CALLSIGN_RE = re.compile(r"^[A-Z0-9/]+$")


def member_callsigns(path):
    calls = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            call = line.split()[0].upper()
            if CALLSIGN_RE.match(call):
                calls.append(call)
    return calls


def detect_changes(calls):
    """Query QRZ for every callsign; return {old: new} for changed ones."""
    client = QRZClient.from_env()
    if client is None:
        print(
            "ERROR: QRZ_USERNAME / QRZ_PASSWORD not set. Set them for live "
            "checks, or apply a known change with --map OLD=NEW.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        client.login()
    except QRZError as e:
        print(f"ERROR: QRZ login failed: {e}", file=sys.stderr)
        sys.exit(1)

    changes = {}
    print(f"Checking {len(calls)} callsigns against QRZ...")
    for call in calls:
        try:
            res = client.resolve(call)
        except QRZNotFound:
            print(f"  {call}: not found on QRZ (removed or lapsed?)", file=sys.stderr)
            continue
        except QRZError as e:
            print(f"  {call}: QRZ error: {e}", file=sys.stderr)
            continue
        if res.changed:
            changes[call] = res.current
            print(f"  {call} -> {res.current}")
        time.sleep(0.3)  # be polite to QRZ
    return changes


def rewrite_file(path, changes, apply):
    """Replace old callsigns at the start of data lines; keep the file sorted.

    Member files are '<CALL> <anchor> <details>' lines under a comment header;
    lines are sorted by callsign, so re-sort after renaming.
    """
    with open(path) as f:
        lines = f.read().splitlines()

    header, data = [], []
    for line in lines:
        (header if not line.strip() or line.startswith("#") else data).append(line)

    changed = []
    updated = []
    for line in data:
        call, sep, rest = line.partition(" ")
        new = changes.get(call.upper())
        if new:
            changed.append((call.upper(), new))
            line = new + sep + rest
        updated.append(line)

    if not changed:
        print(f"{os.path.relpath(path, ROOT)}: no changes")
        return False

    updated.sort(key=lambda l: l.split()[0])
    for old, new in changed:
        print(f"{os.path.relpath(path, ROOT)}: {old} -> {new}")

    if apply:
        with open(path, "w") as f:
            f.write("\n".join(header + updated) + "\n")
    return True


def prune_cache(changes, apply):
    """Drop replaced callsigns from the QRZ cache so the new ones get fresh
    lookups on the next map build."""
    cache = load_cache(CACHE_FILE)
    stale = [old for old in changes if old in cache]
    if not stale:
        return
    print(f"data/qrz_cache.json: dropping stale entries: {', '.join(stale)}")
    if apply:
        for old in stale:
            del cache[old]
        save_cache(CACHE_FILE, cache)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply", action="store_true",
        help="rewrite the member files (default is a dry run)",
    )
    parser.add_argument(
        "--map", action="append", default=[], metavar="OLD=NEW",
        help="apply a known callsign change without querying QRZ (repeatable)",
    )
    args = parser.parse_args()

    changes = {}
    for mapping in args.map:
        old, sep, new = mapping.upper().partition("=")
        if not sep or not CALLSIGN_RE.match(old) or not CALLSIGN_RE.match(new):
            parser.error(f"invalid --map value: {mapping!r} (expected OLD=NEW)")
        changes[old] = new

    if not changes:
        changes = detect_changes(member_callsigns(MEMBERS_FILE))

    if not changes:
        print("No callsign changes detected.")
        return 0

    any_changed = False
    for path in (MEMBERS_FILE, NOTES_FILE):
        any_changed |= rewrite_file(path, changes, args.apply)
    prune_cache(changes, args.apply)

    if any_changed and not args.apply:
        print("\nDry run only. Re-run with --apply to write the changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
