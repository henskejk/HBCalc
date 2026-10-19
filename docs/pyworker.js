(()=>{var l="https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";importScripts(`${l}pyodide.js`);var s,p,o,c=e=>new Promise((i,a)=>s.FS.syncfs(e,t=>t?a(t):i()));async function h(e){s=await loadPyodide({indexURL:l}),await s.loadPackage("sqlite3");let i=await(await fetch(`${e}py/manifest.json`)).json();await Promise.all(i.files.map(async a=>{let t=await fetch(`${e}py/${a}`);if(!t.ok)throw new Error(`Couldn't load ${a} (${t.status})`);let n=new Uint8Array(await t.arrayBuffer()),d=`/app/${a}`.split("/").slice(0,-1).join("/");s.FS.mkdirTree(d),s.FS.writeFile(`/app/${a}`,n)})),s.FS.mkdir("/persist"),s.FS.mount(s.FS.filesystems.IDBFS,{},"/persist"),await c(!0),s.runPython(`
import json, sys
sys.path.insert(0, "/app")
from pathlib import Path
from brewcalc import service

_DB = Path("/persist/brewing.db")
_EXAMPLE = Path("/app/data/example_recipe.json")

def run(method, path, body):
    status, data = service.handle(method, path, body, _DB, _EXAMPLE)
    return json.dumps([status, data])
`),p=s.globals.get("run")}self.onmessage=async e=>{let{id:i,method:a,path:t,body:n,base:d}=e.data;try{o??(o=h(d)),await o;let[r,f]=JSON.parse(p(a,t,n??null));a!=="GET"&&(t.startsWith("/api/recipes")||t.startsWith("/api/logs"))&&r<400&&await c(!1),self.postMessage({id:i,status:r,data:f})}catch(r){o=o&&p?o:void 0,self.postMessage({id:i,status:500,data:{error:`The calculator engine failed: ${r.message||r}`}})}};})();
