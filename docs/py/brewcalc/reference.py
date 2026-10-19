"""Ingredient and style reference data, read from the CSV files in data/."""

from __future__ import annotations

import csv
import os
from collections import Counter
from functools import cache
from pathlib import Path

from brewcalc.calcs import StyleRange

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _read(name: str) -> list[dict]:
    with (DATA_DIR / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _by_name(rows: list[dict], numeric: tuple[str, ...]) -> dict[str, dict]:
    out = {}
    for row in rows:
        for key in numeric:
            row[key] = float(row[key])
        out[row["name"]] = row
    return out


@cache
def grains() -> dict[str, dict]:
    # A fermentable with a producer is keyed (and shown in the dropdown) as "Pilsen Malt, Briess"; `item` keeps the plain name.
    rows = _read("grains.csv")
    for row in rows:
        row["item"] = row["name"]
        row["producer"] = (row.get("producer") or "").strip()
        if row["producer"]:
            row["name"] = f"{row['item']}, {row['producer']}"
    return _by_name(rows, ("lovibond", "ppg"))


# Two hop lists are available. The comprehensive list (default, data/hops_comprehensive.csv) is built from Hop Growers
# of America, NZ Hops, British Hops and BarthHaas data, with a source noted on every row. The Brewer's Friend export
# is for personal use only and is kept as an option. Choose with the BREWCALC_HOPS environment variable:
# "comprehensive" (default) or "bf".
HOPS_FILES = {"comprehensive": "hops_comprehensive.csv", "bf": "HopsReference_BF.csv"}
HOPS_FILE = HOPS_FILES.get(os.environ.get("BREWCALC_HOPS", "comprehensive").lower(), HOPS_FILES["comprehensive"])
_HOP_COLUMNS = {"Name": "name", "Type": "type", "Average AA": "alpha_acid", "Recommended Use": "use"}


@cache
def hops() -> dict[str, dict]:
    with (DATA_DIR / HOPS_FILE).open(newline="", encoding="utf-8-sig") as f:
        rows = [{_HOP_COLUMNS.get(k, k): v for k, v in row.items()} for row in csv.DictReader(f)]
    return _by_name(rows, ("alpha_acid",))


# The yeast reference is the BrewUnited list. To go back to the spreadsheet's list, change this to
# "yeasts.csv" and use `_by_name(_read(YEASTS_FILE), ("attenuation",))` in yeasts().
YEASTS_FILE = "yeasts_brewunited.csv"


@cache
def yeasts() -> dict[str, dict]:
    """Yeasts keyed by name (so saved recipes keep working). Names that appear more than once
    across labs are keyed by their unique label instead, e.g. "WLP650 Brettanomyces Bruxellensis"."""
    rows = _read(YEASTS_FILE)
    counts = Counter(r["name"] for r in rows)
    out = {}
    for r in rows:
        key = r["name"] if counts[r["name"]] == 1 else r["label"]
        lo, hi = r["temp_min_f"], r["temp_max_f"]
        out[key] = {
            **r,
            "name": key,
            "attenuation": float(r["attenuation"]),
            "attenuation_range": "",  # not in this list
            "temp_range_f": f"{float(lo):g}-{float(hi):g}" if lo and hi else "",
            "alcohol_tolerance": "",  # not in this list
        }
    return out


STYLE_RANGES = ("abv", "ibu", "og", "fg", "srm")

# Names used by the old style list (and so by saved recipes) that the BJCP 2021 guidelines renamed.
STYLE_ALIASES = {
    "light american lager": "1A. American Light Lager",
    "standard american lager": "1B. American Lager",
    "premium american lager": "1B. American Lager",
    "dark american lager": "2C. International Dark Lager",
    "classic american pilsner": "27. Historical Beer: Pre-Prohibition Lager",
    "american wheat": "1D. American Wheat Beer",
    "bohemian pilsner": "3B. Czech Premium Pale Lager",
    "dortmunder export": "5C. German Helles Exportbier",
    "classic rauchbier": "6B. Rauchbier",
    "octoberfest/marzen": "6A. Märzen",
    "maibock/helles bock": "4C. Helles Bock",
    "traditional bock": "6C. Dunkles Bock",
    "dusseldorf altbier": "7B. Altbier",
    "north german altbier": "7B. Altbier",
    "weizen/weissbier": "10A. Weissbier",
    "dunkelweizen": "10B. Dunkles Weissbier",
    "weizenbock": "10C. Weizenbock",
    "kolsch": "5B. Kölsch",
    "standard bitter": "11A. Ordinary Bitter",
    "esb": "11C. Strong Bitter",
    "english ipa": "12C. English IPA",
    "english mild brown": "13A. Dark Mild",
    "brown porter": "13C. English Porter",
    "robust porter": "20A. American Porter",
    "northern english brown": "13B. British Brown Ale",
    "southern english brown": "13B. British Brown Ale",
    "scottish light": "14A. Scottish Light",
    "scottish heavy": "14B. Scottish Heavy",
    "scottish export": "14C. Scottish Export",
    "strong scotch ale": "17C. Wee Heavy",
    "irish red": "15A. Irish Red Ale",
    "dry stout": "15B. Irish Stout",
    "american amber": "19A. American Amber Ale",
    "american brown": "19C. American Brown Ale",
    "english barleywine": "17D. English Barley Wine",
    "american barleywine": "22C. American Barleywine",
    "imperial ipa": "22A. Double IPA",
    "russian imperial stout": "20C. Imperial Stout",
    "foreign extra stout": "16D. Foreign Extra Stout",
    "german pilsner": "5D. German Pils",
    "german rye (roggenbier)": "27. Historical Beer: Roggenbier",
    "flanders red": "23B. Flanders Red Ale",
    "flanders brown/oud bruin": "23C. Oud Bruin",
    "unblended lambic": "23D. Lambic",
    "witbier": "24A. Witbier",
    "belgian witbier": "24A. Witbier",
    "belgian pale ale": "24B. Belgian Pale Ale",
    "biere de garde": "24C. Bière de Garde",
    "belgian blond": "25A. Belgian Blond Ale",
    "belgian saison": "25B. Saison",
    "belgian golden strong": "25C. Belgian Golden Strong Ale",
    "belgian double": "26B. Belgian Dubbel",
    "belgian tripel": "26C. Belgian Tripel",
    "belgian dark strong": "26D. Belgian Dark Strong Ale",
    "belgian specialty ale": "24B. Belgian Pale Ale",
    "other smoked beer": "32B. Specialty Smoked Beer",
    "blonde ale": "18A. Blonde Ale",
    "american pale ale": "18B. American Pale Ale",
    "american stout": "20B. American Stout",
    "american ipa": "21A. American IPA",
    "california common": "19B. California Common",
    "cream ale": "1C. Cream Ale",
    "berliner weisse": "23A. Berliner Weisse",
    "munich helles": "4A. Munich Helles",
    "munich dunkel": "8A. Munich Dunkel",
    "schwarzbier": "8B. Schwarzbier",
    "vienna lager": "7A. Vienna Lager",
    "doppelbock": "9A. Doppelbock",
    "eisbock": "9B. Eisbock",
    "baltic porter": "9C. Baltic Porter",
    "sweet stout": "16A. Sweet Stout",
    "oatmeal stout": "16B. Oatmeal Stout",
    "old ale": "17B. Old Ale",
    "gueuze": "23E. Gueuze",
    "fruit lambic": "23F. Fruit Lambic",
}


def _pair(row: dict, key: str):
    lo, hi = row[f"{key}_min"], row[f"{key}_max"]
    return (float(lo), float(hi)) if lo != "" and hi != "" else None


@cache
def styles() -> dict[str, StyleRange]:
    """BJCP 2021 styles keyed by their numbered name, e.g. "21A. American IPA"."""
    out = {}
    for row in _read("styles.csv"):
        info = {k: v for k, v in row.items() if v and k != "name" and not k.endswith(("_min", "_max"))}
        out[row["name"]] = StyleRange(row["name"], *(_pair(row, k) for k in STYLE_RANGES), info=info)
    return out


def find_style(name: str | None) -> StyleRange | None:
    """Look a style up by its exact name, then without the number ("American IPA"), then by an old name."""
    if not name:
        return None
    table = styles()
    if name in table:
        return table[name]
    key = name.strip().lower()
    for style_name, style in table.items():
        if style_name.lower() == key or style_name.split(". ", 1)[-1].lower() == key:
            return style
    alias = STYLE_ALIASES.get(key)
    return table.get(alias) if alias else None


@cache
def srm_colors() -> list[tuple[float, str]]:
    return sorted((float(r["srm_max"]), r["color"]) for r in _read("srm_colors.csv"))
