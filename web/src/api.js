// The app talks to a JSON API. On the Mac that is ../api.py over HTTP. In the static build (GitHub Pages) there is
// no server, so the same requests go to a web worker running the app's Python in the browser (see pyworker.js).

/* global __STATIC__ */

async function httpRequest(method, path, body, signal) {
  const res = await fetch(path, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* no JSON body */
  }
  if (!res.ok) throw new Error((data && data.error) || `Request failed (${res.status})`);
  return data;
}

let worker;
let nextId = 1;
const pending = new Map();

function workerRequest(method, path, body, signal) {
  if (!worker) {
    // Relative to the page, so it works under a sub-path like /HBCalc/.
    worker = new Worker("pyworker.js");
    worker.onmessage = ({ data }) => {
      const wait = pending.get(data.id);
      if (!wait) return; // the caller gave up (aborted)
      pending.delete(data.id);
      if (data.status >= 400) wait.reject(new Error((data.data && data.data.error) || `Request failed (${data.status})`));
      else wait.resolve(data.data);
    };
  }
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException("Aborted", "AbortError"));
    const id = nextId++;
    pending.set(id, { resolve, reject });
    signal?.addEventListener("abort", () => {
      pending.delete(id);
      reject(new DOMException("Aborted", "AbortError"));
    });
    const base = new URL(".", window.location.href).href;
    worker.postMessage({ id, method, path, base, body: body !== undefined ? JSON.stringify(body) : null });
  });
}

const request = typeof __STATIC__ !== "undefined" && __STATIC__ ? workerRequest : httpRequest;

export const api = {
  get: (path, signal) => request("GET", path, undefined, signal),
  post: (path, body, signal) => request("POST", path, body ?? {}, signal),
  put: (path, body) => request("PUT", path, body),
  del: (path) => request("DELETE", path),
};
