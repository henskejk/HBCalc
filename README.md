# Brewing Calculator

A local web app version of `BrewingCalculator_JKH.xlsx`: recipe calculator,
saved recipes, brew-day logs, and the grain / hop / yeast / style reference.

## Running it

One-time setup (already done on this Mac):

```bash
conda env create -f environment.yml
```

Start the app by double-clicking `run.command` in Finder, or from a terminal:

```bash
~/Coding/brewing-calculator/run.command
```

then open http://localhost:8501. Stop it with Ctrl+C. (The script uses the
`brewing_calculator` environment directly, so there's no need to
`conda activate` first. After changing code in `brewcalc/`, restart it.)

### React version

There is also a React version of the same app (same calculations, same `brewing.db`; the Streamlit version
above is untouched and still works). It needs two extra packages, once:

```bash
conda install -n brewing_calculator -c conda-forge starlette uvicorn
```

then double-click `run_react.command` (or run `./run_react.command`) and open http://localhost:8000.
Add `--lan` to reach it from a phone. Details in `web/README.md`.

### Hosted version (GitHub Pages)

`docs/` is a static build of the React app that runs the same Python (`brewcalc/`) inside the browser using
[Pyodide](https://pyodide.org), so it needs no server. Saved recipes and brew logs are kept in that browser's own
storage (they stay on that device; use Download recipe to move one). Rebuild it after any change to the code or
reference data, then commit `docs/`:

```bash
cd web && npm run build:static
```

To publish: repository Settings → Pages → Deploy from a branch → `main` / `/docs`. To try it locally:
`cd docs && python3 -m http.server 8001`, then open http://localhost:8001.

### From your phone on brew day

By default only this Mac can open the app. To reach it from a phone on the
same Wi-Fi, start it with:

```bash
~/Coding/brewing-calculator/run.command --lan
```

and open the "Network URL" it prints (like `http://192.168.1.23:8501`) on
the phone. There's no password, so anyone on your home network could open it
while it's running this way.

## What's where

| Path | What it is |
|---|---|
| `app.py` | Entry point; sets up the three pages |
| `views/` | The pages: Calculator, Brew Day, Ingredients |
| `api.py` | JSON server for the React version (a thin layer over `brewcalc/`) |
| `web/` | The React version: source in `web/src/`, built app in `web/dist/` |
| `docs/` | Static build of the React app for GitHub Pages (Python runs in the browser) |
| `brewcalc/service.py` | What each API request does, with no web framework (shared by `api.py` and the hosted version) |
| `run_react.command` | Starts the React version |
| `brewcalc/calcs.py` | All brewing formulas (no UI code) |
| `brewcalc/recipe.py` | Recipe format and conversion to calculator inputs |
| `brewcalc/db.py` | Saved recipes and brew logs (SQLite) |
| `data/grains.csv`, `hops_comprehensive.csv`, `yeasts_brewunited.csv`, `styles.csv`, `srm_colors.csv` | The reference data the app loads. Each row names its source; edit freely |
| `data/example_recipe.json` | An example American IPA (loaded by "Load spreadsheet example") |
| `brewing.db` | Your saved recipes and logs (created on first save; not in git) |
| `scripts/import_brewunited_yeast.py` | Rebuilds `yeasts_brewunited.csv` from [BrewUnited's yeast database](https://www.brewunited.com/yeast_database.php) (`--fetch` downloads a fresh copy) |
| `tests/` | Checks against the spreadsheet's values |

Back up `brewing.db` to keep your recipes and logs. Recipes can also be
downloaded as `.json` files from the sidebar.

## Differences from the spreadsheet

The formulas and results match the spreadsheet (tests check this to 12
significant digits), except for these fixes:

- **Step infusions:** boiling water for a step now uses Palmer's equation
  correctly (divide by boiling temp − *target* temp) and counts water added in
  earlier steps. The spreadsheet under-dosed by about 30%: 7.1 qt instead of
  10.3 qt for the 170 °F mash-out.
- **Sparge water** is a water balance (pre-boil volume + grain absorption +
  deadspace − mash water) instead of lbs of grain ÷ 2.
- **Hop rows 31-35** in the spreadsheet had a formula that overstated IBUs
  ~100x; all hop rows now use the same formula.
- **Ingredient lookups** are exact matches. The spreadsheet's `LOOKUP` needed
  sorted lists, and its ranges shifted row by row, so some grains couldn't be
  found and some hops could pick up the wrong alpha acid.
- **New:** per-hop alpha acid override, attenuation override, hop "use"
  (first wort / boil / flameout / whirlpool / dry hop), brew-day logging with
  actual efficiency, ABV and attenuation.

## Development

```bash
conda activate brewing_calculator
pytest
ruff check .
```
