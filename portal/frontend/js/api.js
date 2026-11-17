// Thin wrappers around the portal API. Each call is cached so views can share data.
const cache = new Map();

async function getJSON(path) {
  if (!cache.has(path)) {
    cache.set(path, fetch(path).then(async (r) => {
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `${path}: HTTP ${r.status}`);
      }
      return r.json();
    }));
  }
  return cache.get(path);
}

export const api = {
  cells: () => getJSON("/api/cells"),
  tracts: () => getJSON("/api/tracts"),
  heatDays: () => getJSON("/api/heat-days"),
  personas: () => getJSON("/api/personas"),
  ask: (message) =>
    fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    }),
};
