"""Convert BrewUnited's yeast database page into data/yeasts_brewunited.csv.

Usage:
    python scripts/import_brewunited_yeast.py [--fetch]

Reads the saved copy at data/sources/brewunited_yeast_database.html. With
--fetch it first downloads a fresh copy (one request) from
https://www.brewunited.com/yeast_database.php
"""

from __future__ import annotations

import csv
import re
import sys
import urllib.request
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_URL = "https://www.brewunited.com/yeast_database.php"
SAVED_HTML = ROOT / "data" / "sources" / "brewunited_yeast_database.html"
OUT = ROOT / "data" / "yeasts_brewunited.csv"

COLUMNS = [
    "label", "name", "code", "lab", "type", "form",
    "temp_min_f", "temp_max_f", "attenuation", "flocculation",
    "best_for", "notes", "issues",
]  # fmt: skip


class TableRows(HTMLParser):
    """Collects the cells of every <tr class="row1|row2"> as text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get("class") or ""
        if tag == "tr":
            self._row = [] if cls.startswith("row") else None
        elif tag == "td" and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append("\n")

    def handle_endtag(self, tag):
        if tag == "td" and self._row is not None and self._cell is not None:
            self._row.append("".join(self._cell))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if len(self._row) == 8:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def tidy(text: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", unescape(text).replace(" ", " ")).strip()


# A product code is a token containing a digit, like 1056, WLP001, CL-0010,
# US-05, 71B-1122, ECY29. "RC 212" is the one code with a space.
CODE = r"(RC 212|[A-Z]{0,4}-?\d[\w/-]*)"


def split_code(name: str) -> tuple[str, str]:
    """'1056 American Ale' -> ('1056', 'American Ale').

    Handles codes at the end too ('Northeast Ale ECY29'), and names that
    repeat the code at both ends ('1010 American Wheat 1010').
    """
    name = re.sub(r"\s+-\s+", " ", name)  # "Lalvin - K1V-1116"
    m = re.match(rf"^{CODE}\s+(.+)$", name)
    if m:
        code, rest = m.groups()
        trimmed = re.sub(rf"\s*\b{re.escape(code)}$", "", rest).strip()
        # Keep "Lalvin D-47" whole rather than shrinking it to just "Lalvin".
        return code, trimmed if len(trimmed.split()) > 1 else rest
    m = re.match(rf"^(.+?)\s+{CODE}$", name)
    if m and any(ch.isdigit() for ch in m.group(2)):
        return m.group(2), m.group(1)
    return "", name


FLOCCULATION = {
    "low": "Low",
    "medium low": "Low-Medium",
    "medium": "Medium",
    "medium hig": "Medium-High",  # truncated on the source page
    "medium high": "Medium-High",
    "high": "High",
    "very high": "Very High",
}

LABS = {"DCL/Fermentis": "Fermentis", "Lallemand - Lal": "Lallemand (Lalvin)"}


def parse_temp(text: str) -> tuple[float | None, float | None]:
    nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", text)]
    if len(nums) >= 2:
        return nums[0], nums[1]
    if len(nums) == 1:
        return nums[0], nums[0]
    return None, None


def parse_row(cells: list[str]) -> dict:
    name, lab, typ, form, temp, att, floc, notes = (tidy(c) for c in cells)
    issues = []

    # Glitches on the source page: "Array " and "- " prefixes.
    name = re.sub(r"^(Array\s+|-\s+)", "", name).strip()

    tmin, tmax = parse_temp(temp)
    if tmin is None or tmax is None:
        issues.append("no temperature range")
    elif tmax <= tmin or tmax < 40:
        issues.append(f"suspicious temperature range {temp}")

    m = re.search(r"\d+(?:\.\d+)?", att)
    attenuation = float(m.group()) if m else None
    if attenuation is None or attenuation == 0:
        issues.append("no attenuation")
        attenuation = None
    elif not 50 <= attenuation <= 100:
        issues.append(f"suspicious attenuation {att}")

    best_for = ""
    note_lines = [line.strip() for line in notes.split("\n") if line.strip()]
    kept = []
    for line in note_lines:
        if line.lower().startswith("best for:"):
            best_for = line.split(":", 1)[1].strip()
        else:
            kept.append(line)

    code, name = split_code(name)
    return {
        "name": name,
        "code": code,
        "lab": LABS.get(lab, lab),
        "type": typ,
        "form": form,
        "temp_min_f": tmin,
        "temp_max_f": tmax,
        "attenuation": attenuation,
        "flocculation": FLOCCULATION.get(floc.lower(), floc),
        "best_for": best_for,
        "notes": " ".join(kept),
        "issues": "; ".join(issues),
    }


def main() -> None:
    if "--fetch" in sys.argv:
        req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0 (personal homebrew calculator)"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            SAVED_HTML.write_bytes(resp.read())
        print(f"downloaded {SOURCE_URL}")

    parser = TableRows()
    parser.feed(SAVED_HTML.read_text(encoding="utf-8", errors="replace"))
    parsed = [parse_row(r) for r in parser.rows]

    # Drop exact duplicates (US-05 is listed 8 times) and placeholder rows
    # (32-32 °F, no flocculation) for strains that have a complete entry.
    rows, seen, dropped = [], set(), []
    for r in parsed:
        key = tuple(r.values())
        if key in seen:
            dropped.append(f"duplicate: {r['code']} {r['name']}".strip())
            continue
        seen.add(key)
        if r["temp_max_f"] == 32 and not r["flocculation"]:
            dropped.append(f"placeholder: {r['name']} ({r['lab']})")
            continue
        rows.append(r)

    # Several strains have a complete entry plus a bare one (no notes or
    # "best for", often slightly different numbers). Keep the complete one.
    def strain(r):
        return (r["lab"], r["code"] or r["name"].lower())

    def described(r):
        return bool(r["notes"] or r["best_for"])

    has_described = {strain(r) for r in rows if described(r)}
    kept = []
    for r in rows:
        if not described(r) and strain(r) in has_described:
            dropped.append(f"bare entry for {r['code']} {r['name']} ({r['lab']})".replace("  ", " "))
        else:
            kept.append(r)
    rows = kept

    # Unique label for picking a yeast in the app: "WLP001 California Ale",
    # or "Nottingham (Danstar)" when there's no code. Remaining repeats
    # (Belle Saison has two different bare entries) get numbered.
    labels: dict[str, int] = {}
    for r in rows:
        label = f"{r['code']} {r['name']}" if r["code"] else f"{r['name']} ({r['lab']})"
        labels[label.lower()] = labels.get(label.lower(), 0) + 1
        if labels[label.lower()] > 1:
            label += f" #{labels[label.lower()]}"
            r["issues"] = "; ".join(filter(None, [r["issues"], "another entry for this strain has different values"]))
        r["label"] = label

    rows.sort(key=lambda r: (r["lab"].lower(), r["code"], r["name"].lower()))
    for d in dropped:
        print("  dropped", d)

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    flagged = sum(1 for r in rows if r["issues"])
    print(f"wrote {len(rows)} yeasts -> {OUT.relative_to(ROOT)} ({flagged} flagged in the 'issues' column)")


if __name__ == "__main__":
    main()
