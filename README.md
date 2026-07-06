# QRQ Crew Club

Static website for the QRQ Crew Club, a high-speed CW (Morse code) amateur radio group.

## Pages

- `index.html` - Main landing page with club information
- `roster.html` - Member roster

## Scripts

- `scripts/qrz.py` - QRZ XML API client library with callsign-change
  detection (QRZ answers a lookup of a superseded callsign with the current
  record, so old calls resolve to new ones)
- `scripts/build-roster.py` - Builds `roster.html` from the Google Sheet;
  with `QRZ_USERNAME`/`QRZ_PASSWORD` set it displays changed callsigns under
  their current call
- `scripts/build-map.py` - Builds `data/locations.json` for the crew map and
  warns when a member's callsign has changed
- `scripts/update-callsigns.py` - Checks every member callsign against QRZ
  and rewrites `members.txt`/`qrqcrew-notes.txt` when calls change
  (dry run by default; `--apply` to write, `--map OLD=NEW` for offline use)

Run the library tests with `python3 -m unittest discover -s scripts`.
