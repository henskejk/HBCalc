// Bundles src/ into dist/ (app.js, app.css, index.html). Usage:
//   npm run build    one-off, minified
//   npm run watch    rebuilds when you save a file
import { context, build } from "esbuild";
import { cpSync, mkdirSync } from "node:fs";

const watch = process.argv.includes("--watch");
mkdirSync("dist", { recursive: true });
cpSync("index.html", "dist/index.html");

const options = {
  entryPoints: { app: "src/main.jsx" },
  bundle: true,
  outdir: "dist",
  jsx: "automatic",
  target: ["es2020"],
  minify: !watch,
  sourcemap: watch,
  define: { "process.env.NODE_ENV": watch ? '"development"' : '"production"' },
  logLevel: "info",
};

if (watch) {
  const ctx = await context(options);
  await ctx.watch();
  console.log("Watching src/ for changes…");
} else {
  await build(options);
}
