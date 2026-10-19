// Thin wrapper around fetch for the JSON API in ../api.py.

async function request(method, path, body, signal) {
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

export const api = {
  get: (path, signal) => request("GET", path, undefined, signal),
  post: (path, body, signal) => request("POST", path, body ?? {}, signal),
  put: (path, body) => request("PUT", path, body),
  del: (path) => request("DELETE", path),
};
