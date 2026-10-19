# React front end

The React version of the calculator. It does no brewing maths: it sends the recipe to `../api.py`
(a small Starlette server over the same `brewcalc/` code the Streamlit app uses) and shows what comes back.
Recipes and brew logs are the same `brewing.db` the Streamlit version uses.

## Running it

From the project folder, double-click `run_react.command` (or run `./run_react.command`) and open
http://localhost:8000. The built app is in `web/dist/`, so Node isn't needed just to run it.

## Changing the front end

Source is in `web/src/` (plain JSX, no TypeScript). It is bundled with esbuild:

```bash
cd web
npm install        # once: react, react-dom, esbuild
npm run build      # writes web/dist/
npm run watch      # rebuilds on every save (reload the browser to see changes)
```

Commit `web/dist/` after building so the app runs without Node.

## What's where

| Path | What it is |
|---|---|
| `src/App.jsx` | Page shell, sidebar, recipe and log loading, saving |
| `src/pages/Calculator.jsx` | Calculator page (stats box, system specs, grain, hops, yeast, mash) |
| `src/pages/BrewDay.jsx` | Brew day log, plan and actual-vs-planned |
| `src/pages/Ingredients.jsx` | Searchable, sortable reference tables |
| `src/components.jsx` | Number box, searchable drop-down, metric tile |
| `src/styles.css` | All styling (banner colors are at the top) |
| `build.mjs` | The esbuild script |

The banner font (Rubik Microbe) is loaded from Google Fonts, so it needs internet; offline it falls back to a serif.
