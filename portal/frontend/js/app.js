// App shell: side navigation and a tiny hash router (#/map, #/today, ...).
import { api } from "./api.js";
import { initMapView, showLayer, resizeMap } from "./map.js";
import { renderView } from "./views.js";

const els = {
  nav: document.getElementById("sidenav"),
  mapView: document.getElementById("view-map"),
  generic: document.getElementById("view-generic"),
  status: document.getElementById("data-status"),
};

let views = [], questions = [], mapReady = null, askPrefill = "";

function go(id) { location.hash = `#/${id}`; }

function renderNav(active) {
  els.nav.innerHTML = views.map((v) => {
    const n = questions.filter((q) => q.view === v.id).length;
    return `<a class="nav-item ${v.id === active ? "active" : ""}" href="#/${v.id}" title="${v.label}">
      <span>${v.icon}</span><span class="nav-label">${v.label}</span>
      ${n ? `<span class="nav-count">${n}</span>` : ""}</a>`;
  }).join("");
}

function ensureMap() {
  if (!mapReady) {
    mapReady = initMapView({
      onAsk: (text) => { askPrefill = text; go("ask"); },
      onStatus: (s) => { els.status.textContent = s; },
    }).catch((e) => {
      els.status.textContent = "Data unavailable";
      document.getElementById("legend").innerHTML =
        `<div class="legend-title">Couldn't load map data</div><div class="legend-note">${e.message}</div>`;
    });
  }
  return mapReady;
}

async function route() {
  const id = (location.hash.replace(/^#\//, "") || "map").split("?")[0];
  const view = views.find((v) => v.id === id) || views[0];
  renderNav(view.id);

  if (view.id === "map") {
    els.generic.hidden = true;
    els.mapView.hidden = false;
    await ensureMap();
    resizeMap();
    return;
  }
  els.mapView.hidden = true;
  els.generic.hidden = false;
  await renderView(els.generic, view, questions, {
    prefill: view.id === "ask" ? askPrefill : "",
    onShowLayer: async (layer) => { go("map"); await ensureMap(); showLayer(layer); },
  });
  if (view.id === "ask") askPrefill = "";
}

async function main() {
  ({ views, questions } = await api.personas());
  window.addEventListener("hashchange", route);
  await route();
  // Warm the data cache so the map opens instantly later. (Don't build the map itself
  // while its container is hidden: MapLibre would size it to 0x0.)
  api.cells().catch(() => {});
  api.tracts().catch(() => {});
}

main().catch((e) => { els.status.textContent = `Error: ${e.message}`; });
