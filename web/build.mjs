// Bundles src/ into dist/ (app.js, app.css, index.html). Usage:
//   npm run build           one-off, minified, for the Mac server (talks to ../api.py)  -> web/dist/
//   npm run watch           rebuilds when you save a file
//   npm run build:static    the GitHub Pages version (Python runs in the browser)        -> ../docs/
import { context, build } from "esbuild";
import { cpSync, existsSync, mkdirSync, readdirSync, rmSync, writeFileSync } from "node:fs";

const watch = process.argv.includes("--watch");
const isStatic = process.argv.includes("--static");
const outdir = isStatic ? "../docs" : "dist";
mkdirSync(outdir, { recursive: true });
cpSync("index.html", `${outdir}/index.html`);

const options = {
  entryPoints: { app: "src/main.jsx", ...(isStatic ? { pyworker: "src/pyworker.js" } : {}) },
  bundle: true,
  outdir,
  jsx: "automatic",
  target: ["es2020"],
  minify: !watch,
  sourcemap: watch,
  define: { "process.env.NODE_ENV": watch ? '"development"' : '"production"', __STATIC__: String(isStatic) },
  logLevel: "info",
};

if (isStatic) {
  // The Python code and the reference data the app actually loads, copied next to the page for the worker to fetch.
  const py = `${outdir}/py`;
  rmSync(py, { recursive: true, force: true });
  const files = [
    ...["__init__", "calcs", "db", "recipe", "reference", "service"].map((m) => `brewcalc/${m}.py`),
    ...["grains.csv", "hops_comprehensive.csv", "yeasts_brewunited.csv", "styles.csv", "srm_colors.csv", "example_recipe.json"].map((f) => `data/${f}`),
  ];
  for (const f of files) {
    if (!existsSync(`../${f}`)) throw new Error(`Missing ${f}`);
    mkdirSync(`${py}/${f.split("/")[0]}`, { recursive: true });
    cpSync(`../${f}`, `${py}/${f}`);
  }
  writeFileSync(`${py}/manifest.json`, JSON.stringify({ files }, null, 1));
  writeFileSync(`${outdir}/.nojekyll`, "");
}

if (watch) {
  const ctx = await context(options);
  await ctx.watch();
  console.log("Watching src/ for changes…");
} else {
  await build(options);
}
