// Web worker for the static (GitHub Pages) version: runs the app's own Python (brewcalc/) in the browser with
// Pyodide and answers the same /api/... requests that api.py answers on the Mac. Recipes and brew logs are kept in
// a SQLite file saved in the browser's own storage (IndexedDB), so they stay on this device and browser.

const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";
importScripts(`${PYODIDE_URL}pyodide.js`);

let pyodide;
let handle;
let started;

const syncFs = (populate) =>
  new Promise((resolve, reject) => pyodide.FS.syncfs(populate, (err) => (err ? reject(err) : resolve())));

async function start(base) {
  pyodide = await loadPyodide({ indexURL: PYODIDE_URL });
  await pyodide.loadPackage("sqlite3");

  // Copy the Python code and reference data (listed in py/manifest.json at build time) into Pyodide's file system.
  const manifest = await (await fetch(`${base}py/manifest.json`)).json();
  await Promise.all(
    manifest.files.map(async (name) => {
      const res = await fetch(`${base}py/${name}`);
      if (!res.ok) throw new Error(`Couldn't load ${name} (${res.status})`);
      const bytes = new Uint8Array(await res.arrayBuffer());
      const dir = `/app/${name}`.split("/").slice(0, -1).join("/");
      pyodide.FS.mkdirTree(dir);
      pyodide.FS.writeFile(`/app/${name}`, bytes);
    }),
  );

  // Saved recipes and logs live in /persist, which is backed by IndexedDB.
  pyodide.FS.mkdir("/persist");
  pyodide.FS.mount(pyodide.FS.filesystems.IDBFS, {}, "/persist");
  await syncFs(true);

  pyodide.runPython(`
import json, sys
sys.path.insert(0, "/app")
from pathlib import Path
from brewcalc import service

_DB = Path("/persist/brewing.db")
_EXAMPLE = Path("/app/data/example_recipe.json")

def run(method, path, body):
    status, data = service.handle(method, path, body, _DB, _EXAMPLE)
    return json.dumps([status, data])
`);
  handle = pyodide.globals.get("run");
}

self.onmessage = async (event) => {
  const { id, method, path, body, base } = event.data;
  try {
    started ??= start(base);
    await started;
    const [status, data] = JSON.parse(handle(method, path, body ?? null));
    // Anything that changed the saved recipes or logs is written back to the browser's storage.
    if (method !== "GET" && (path.startsWith("/api/recipes") || path.startsWith("/api/logs")) && status < 400) await syncFs(false);
    self.postMessage({ id, status, data });
  } catch (e) {
    started = started && handle ? started : undefined; // allow a retry if starting up failed
    self.postMessage({ id, status: 500, data: { error: `The calculator engine failed: ${e.message || e}` } });
  }
};
