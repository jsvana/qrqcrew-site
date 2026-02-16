#!/usr/bin/env python3
"""Fetch the QRQ Crew roster CSV from Google Sheets and generate a static roster.html."""

import csv
import io
import sys
import urllib.request
from datetime import datetime, timezone

SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRBfNWrtgvUxTJQL96aK4g7ctZZ-Z572mBEbsscarGQWrbHg66yfxf-Jxw-bZ1ke7KX0zhJk6nUFWhL"
    "/pub?output=csv"
)

MONTHS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def format_date(date_str: str) -> str:
    """Convert MM/DD/YYYY to 'Mon DD, YYYY'."""
    parts = date_str.split("/")
    if len(parts) != 3:
        return date_str
    try:
        month = int(parts[0]) - 1
        day = int(parts[1])
        year = parts[2]
        if 0 <= month < 12:
            return f"{MONTHS[month]} {day}, {year}"
    except ValueError:
        pass
    return date_str


def html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def fetch_csv() -> str:
    req = urllib.request.Request(SHEET_CSV_URL, headers={"User-Agent": "QRQCrew-Roster-Builder/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_members(csv_text: str) -> list[dict]:
    lines = csv_text.splitlines()

    # Find header row containing "Callsign"
    header_idx = -1
    for i, line in enumerate(lines):
        if "Callsign" in line:
            header_idx = i
            break
    if header_idx == -1:
        return []

    # Parse data rows after header
    data_text = "\n".join(lines[header_idx:])
    reader = csv.DictReader(io.StringIO(data_text))

    members = []
    for row in reader:
        callsign = row.get("Callsign", "").strip()
        name = row.get("Name", "").strip()
        join_date = row.get("Join Date", "").strip()
        try:
            qc_number = int(row.get("QC #", "0").strip())
        except ValueError:
            qc_number = 0

        if callsign and qc_number:
            members.append({
                "callsign": callsign,
                "name": name,
                "join_date": join_date,
                "qc_number": qc_number,
            })

    members.sort(key=lambda m: m["qc_number"])
    return members


def render_member_row(member: dict) -> str:
    qc = member["qc_number"]
    callsign = html_escape(member["callsign"])
    name = html_escape(member["name"])
    date = html_escape(format_date(member["join_date"]))

    row_class = ""
    badge = ""
    if qc <= 3:
        row_class = "founder"
        badge = '<span class="founder-badge">Founder</span>'
    elif member["callsign"].upper() == "W6JSV":
        row_class = "tech-guy"
        badge = '<span class="tech-badge">Resident Computer Guy</span>'

    return f"""                <div class="member-row {row_class}">
                    <span class="qc-number">QC #{qc}</span>
                    <span class="callsign">
                        <a href="https://www.qrz.com/db/{callsign}" target="_blank" rel="noopener">{callsign}</a>
                    </span>
                    <span class="name">{name}{badge}</span>
                    <span class="join-date">{date}</span>
                </div>"""


def generate_html(members: list[dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
    count = len(members)
    count_text = f"{count} Member{'s' if count != 1 else ''}"
    member_rows = "\n".join(render_member_row(m) for m in members)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Member Roster | QRQ Crew Club</title>
    <link rel="icon" type="image/svg+xml" href="favicon.svg">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=Source+Sans+Pro:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --navy: #1B3A57;
            --navy-dark: #132A40;
            --slate-blue: #4A7C9B;
            --light-blue: #7BA3BE;
            --cream: #FDFBF7;
            --white: #FFFFFF;
            --text-dark: #2C3E50;
            --text-muted: #5D6D7E;
            --border-light: #D5DFE5;
            --gold: #C9A227;
            --tech-blue: #4A90A4;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Source Sans Pro', Georgia, serif;
            background-color: var(--cream);
            color: var(--text-dark);
            line-height: 1.7;
            min-height: 100vh;
        }}

        .container {{
            max-width: 960px;
            margin: 0 auto;
            padding: 0 24px;
        }}

        header {{
            background: var(--white);
            border-bottom: 3px solid var(--navy);
            padding: 30px 0;
        }}

        .header-content {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-top: 16px;
        }}

        .back-link {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            color: var(--slate-blue);
            text-decoration: none;
            font-size: 0.9rem;
            transition: color 0.3s ease;
        }}

        .back-link:hover {{
            color: var(--navy);
        }}

        h1 {{
            font-family: 'Playfair Display', Georgia, serif;
            font-size: 2rem;
            font-weight: 600;
            color: var(--navy);
        }}

        .member-count {{
            font-size: 0.9rem;
            color: var(--text-muted);
        }}

        main {{
            padding: 40px 0 80px;
        }}

        .roster-header {{
            display: grid;
            grid-template-columns: 80px 120px 1fr 140px;
            gap: 16px;
            padding: 16px 20px;
            background: var(--navy);
            color: var(--white);
            font-size: 0.75rem;
            font-weight: 600;
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }}

        .roster-table {{
            background: var(--white);
            border: 1px solid var(--border-light);
            border-top: none;
        }}

        .member-row {{
            display: grid;
            grid-template-columns: 80px 120px 1fr 140px;
            gap: 16px;
            padding: 16px 20px;
            border-bottom: 1px solid var(--border-light);
            align-items: center;
            transition: background 0.2s ease;
        }}

        .member-row:hover {{
            background: rgba(74, 124, 155, 0.05);
        }}

        .member-row:last-child {{
            border-bottom: none;
        }}

        .member-row.founder {{
            background: linear-gradient(90deg, rgba(201, 162, 39, 0.08) 0%, transparent 100%);
        }}

        .member-row.tech-guy {{
            background: linear-gradient(90deg, rgba(74, 144, 164, 0.08) 0%, transparent 100%);
        }}

        .tech-guy .qc-number {{
            color: var(--tech-blue);
        }}

        .qc-number {{
            font-family: 'Playfair Display', Georgia, serif;
            font-weight: 600;
            color: var(--slate-blue);
        }}

        .founder .qc-number {{
            color: var(--gold);
        }}

        .callsign {{
            font-weight: 600;
            color: var(--navy);
        }}

        .callsign a {{
            color: var(--navy);
            text-decoration: none;
            transition: color 0.2s ease;
        }}

        .callsign a:hover {{
            color: var(--slate-blue);
            text-decoration: underline;
        }}

        .name {{
            color: var(--text-dark);
        }}

        .founder-badge {{
            display: inline-block;
            font-size: 0.65rem;
            font-weight: 600;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            color: var(--gold);
            background: rgba(201, 162, 39, 0.15);
            padding: 2px 8px;
            margin-left: 8px;
            vertical-align: middle;
        }}

        .tech-badge {{
            display: inline-block;
            font-size: 0.65rem;
            font-weight: 600;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            color: var(--tech-blue);
            background: rgba(74, 144, 164, 0.15);
            padding: 2px 8px;
            margin-left: 8px;
            vertical-align: middle;
        }}

        .join-date {{
            color: var(--text-muted);
            font-size: 0.9rem;
        }}

        .error {{
            text-align: center;
            padding: 40px 20px;
            background: var(--white);
            border: 1px solid var(--border-light);
            color: var(--text-muted);
        }}

        .error a {{
            color: var(--slate-blue);
        }}

        .roster-footer {{
            margin-top: 40px;
            text-align: center;
            padding: 24px;
            background: var(--white);
            border: 1px solid var(--border-light);
        }}

        .roster-footer p {{
            color: var(--text-muted);
            font-size: 0.9rem;
            margin-bottom: 8px;
        }}

        .roster-footer a {{
            color: var(--slate-blue);
            text-decoration: none;
        }}

        .roster-footer a:hover {{
            text-decoration: underline;
        }}

        .last-updated {{
            font-size: 0.8rem;
            color: var(--text-muted);
            opacity: 0.7;
        }}

        footer {{
            background: var(--navy);
            color: var(--white);
            padding: 30px 0;
            text-align: center;
        }}

        .footer-text {{
            font-size: 0.85rem;
            opacity: 0.8;
        }}

        .footer-text a {{
            color: var(--light-blue);
            text-decoration: none;
        }}

        .footer-text a:hover {{
            text-decoration: underline;
        }}

        @media (max-width: 700px) {{
            .container {{
                padding: 0 16px;
            }}

            .roster-header {{
                display: none;
            }}

            .roster-table {{
                border: none;
                background: transparent;
            }}

            .member-row {{
                display: block;
                background: var(--white);
                border: 1px solid var(--border-light);
                border-radius: 4px;
                padding: 16px;
                margin-bottom: 12px;
            }}

            .member-row:hover {{
                background: var(--white);
            }}

            .member-row.founder {{
                background: var(--white);
                border-left: 3px solid var(--gold);
            }}

            .member-row.tech-guy {{
                background: var(--white);
                border-left: 3px solid var(--tech-blue);
            }}

            .tech-guy .qc-number {{
                background: var(--tech-blue);
                color: var(--white);
            }}

            .qc-number {{
                display: inline-block;
                font-size: 0.8rem;
                background: var(--navy);
                color: var(--white);
                padding: 2px 10px;
                border-radius: 3px;
                margin-bottom: 8px;
            }}

            .founder .qc-number {{
                background: var(--gold);
                color: var(--white);
            }}

            .callsign {{
                display: block;
                font-size: 1.25rem;
                margin-bottom: 4px;
            }}

            .name {{
                display: block;
                font-size: 1rem;
                color: var(--text-dark);
                margin-bottom: 8px;
            }}

            .founder-badge {{
                display: inline-block;
                margin-left: 0;
                margin-top: 4px;
            }}

            .join-date {{
                display: block;
                font-size: 0.85rem;
                color: var(--text-muted);
            }}

            .join-date::before {{
                content: 'Joined ';
            }}

            .header-content {{
                flex-direction: column;
                align-items: flex-start;
                gap: 8px;
            }}

            h1 {{
                font-size: 1.5rem;
            }}

            .roster-footer {{
                margin-top: 20px;
            }}
        }}
    </style>
</head>
<body>
    <header>
        <div class="container">
            <a href="index.html" class="back-link">&larr; Back to Home</a>
            <div class="header-content">
                <h1>Member Roster</h1>
                <span class="member-count">{count_text}</span>
            </div>
        </div>
    </header>

    <main>
        <div class="container">
            <div class="roster-header">
                <span>QC #</span>
                <span>Callsign</span>
                <span>Name</span>
                <span>Joined</span>
            </div>

            <div class="roster-table">
{member_rows}
            </div>

            <div class="roster-footer">
                <p>Want to join the crew? <a href="index.html#membership">Learn how to become a member</a></p>
                <p class="last-updated">Last updated: {now}</p>
            </div>
        </div>
    </main>

    <footer>
        <div class="container">
            <div class="footer-morse">&minus;&middot;&minus;&middot; &minus;&minus;&middot;&minus; / &minus;&minus;&middot;&minus; &minus;&middot;&minus;&middot;</div>
            <p class="footer-text">
                QRQ Crew Club &copy; 2025 &middot; <a href="index.html">Home</a>
            </p>
        </div>
    </footer>
</body>
</html>
"""


def main() -> int:
    print("Fetching roster CSV...")
    try:
        csv_text = fetch_csv()
    except Exception as e:
        print(f"ERROR: Failed to fetch CSV: {e}", file=sys.stderr)
        return 1

    members = parse_members(csv_text)
    if not members:
        print("ERROR: No members parsed from CSV", file=sys.stderr)
        return 1

    print(f"Parsed {len(members)} members")

    html = generate_html(members)
    with open("roster.html", "w") as f:
        f.write(html)

    print("Generated roster.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
