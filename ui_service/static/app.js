// Heat Planner UI (heat-ui). Draws what the backend's VizSpec says; never computes data itself.
// POST /api/plan -> FinalResponse { status, intent, narrative, citations, viz_spec }.

const $ = (sel) => document.querySelector(sel);
const NS = "http://www.w3.org/2000/svg";
const el = (tag, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  setAttrs(n, attrs);
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) n.append(kid);
  return n;
};
const sv = (tag, attrs = {}, ...kids) => {
  const n = document.createElementNS(NS, tag);
  setAttrs(n, attrs);
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) n.append(kid);
  return n;
};
function setAttrs(n, attrs) {
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.setAttribute("class", v);
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
}

const state = {
  cfg: null,
  city: null,
  layer: "predicted_offset_f",
  tracts: null,
  resp: null,          // last FinalResponse with a non-empty VizSpec
  viz: null,
  selected: 1,         // site rank shown on the map card and Sites page
  count: 3,
  showCompare: false,
  highlight: true,
  showRace: false,
  busy: false,
  map: null,
};

// ------------------------------------------------------------------ helpers

async function getJSON(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) { /* not json */ }
    throw new Error(detail);
  }
  return res.json();
}

const fmtF = (v, d = 2) => (v === null || v === undefined || Number.isNaN(v) ? "—" : `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(d)}°F`);
const fmtPct = (v, d = 0) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(d)}%`);
const fmtNum = (v) => (v === null || v === undefined ? "—" : Number(v).toLocaleString());
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

// Minimal, safe markdown: escape first, then a small set of formatting, then citation chips.
function md(src, citations = []) {
  const inline = (s) => esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  const lines = (src || "").replace(/\r/g, "").split("\n");
  const out = [];
  let list = null, para = [];
  const flushPara = () => { if (para.length) { out.push(`<p>${inline(para.join(" "))}</p>`); para = []; } };
  const flushList = () => { if (list) { out.push(`</${list}>`); list = null; } };
  for (const line of lines) {
    const h = /^(#{1,3})\s+(.*)$/.exec(line);
    const ul = /^\s*[-*]\s+(.*)$/.exec(line);
    const ol = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    if (h) { flushPara(); flushList(); out.push(`<h${h[1].length + 1}>${inline(h[2])}</h${h[1].length + 1}>`); }
    else if (ul || ol) {
      flushPara();
      const kind = ul ? "ul" : "ol";
      if (list !== kind) { flushList(); out.push(`<${kind}>`); list = kind; }
      out.push(`<li>${inline((ul || ol)[1])}</li>`);
    } else if (!line.trim()) { flushPara(); flushList(); }
    else { flushList(); para.push(line.trim()); }
  }
  flushPara(); flushList();
  return cite(out.join(""), citations);
}

function cite(html, citations = []) {
  const by = Object.fromEntries(citations.map((c) => [c.provenance_id, c]));
  return html.replace(/\[(P\d+)\]/g, (_, id) => {
    const c = by[id];
    const title = c ? `${c.mcp_tool_name || c.tool_name} · ${c.sql_object}` : "Source";
    return `<sup class="cite" title="${esc(title)}">${id}</sup>`;
  });
}

const funded = () => (state.viz?.ranked_table || []).filter((r) => r.funded);
const runnerUps = () => (state.viz?.ranked_table || []).filter((r) => !r.funded);
const detail = (rank) => (state.viz?.site_details || []).find((d) => d.rank === rank);
const bars = (rank) => (state.viz?.driver_bars || []).find((b) => b.rank === rank);
const row = (rank) => (state.viz?.ranked_table || []).find((r) => r.rank === rank);
const nameOf = (r) => r?.neighborhood || `Tract ${r?.geo_id}`;

// ------------------------------------------------------------------ pages

const PAGES = ["ask", "sites", "audit", "proposal"];
function route() {
  const page = PAGES.includes(location.hash.slice(1)) ? location.hash.slice(1) : "ask";
  PAGES.forEach((p) => { $(`#page-${p}`).hidden = p !== page; });
  document.querySelectorAll(".pages a").forEach((a) => {
    if (a.dataset.page === page) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  renderPage(page);
  if (page !== "ask") window.scrollTo(0, 0);
}
function go(page) { if (location.hash !== `#${page}`) location.hash = page; else route(); }
function renderPage(page) {
  if (page === "sites") renderSites();
  else if (page === "audit") renderAudit();
  else if (page === "proposal") renderProposal();
}

function needSites(host, what) {
  host.replaceChildren(el("div", { class: "card empty-state" },
    el("h2", { text: `No ${what} yet` }),
    el("p", { text: `Ask the planner where ${state.count} cooling centers should go, and this page fills in from the answer.` }),
    el("button", { type: "button", class: "primary", text: `Where should ${state.count} centers go?`, disabled: state.busy,
      onclick: () => send(defaultQuestion()) })));
}
const defaultQuestion = () => `We can fund ${state.count} permanent cooling centers in ${state.cfg.city} this summer. Where should they go?`;

// ------------------------------------------------------------------ map

const RAMPS = {
  heat: ["#1A2D3E", "#2B3242", "#5A3832", "#9A3412", "#EA580C", "#FDBA74"],
  cool: ["#1A2D3E", "#1B3A5C", "#1D4E89", "#2563EB", "#60A5FA", "#BFDBFE"],
};
const LAYERS = {
  predicted_offset_f: { title: "predicted heat offset by tract", sub: "How much hotter each tract runs than the city average on the campaign day", ramp: "heat", fmt: (v) => fmtF(v, 1), lo: "Cooler", hi: "Hotter than city average" },
  no_vehicle_rate: { title: "households without a car", sub: "Share of households in each tract with no vehicle (ACS)", ramp: "cool", fmt: (v) => fmtPct(v), lo: "Fewer", hi: "More households without a car" },
  share_65_plus: { title: "residents aged 65+", sub: "Share of each tract’s residents aged 65 and older (ACS 2020 5-year)", ramp: "cool", fmt: (v) => fmtPct(v), lo: "Fewer", hi: "More residents 65+" },
};

function makeScale(features, key) {
  const vals = features.map((f) => f.properties[key]).filter((v) => typeof v === "number").sort((a, b) => a - b);
  if (!vals.length) return { color: () => "#1A2530", min: null, max: null, ramp: RAMPS.heat };
  const q = (p) => vals[Math.min(vals.length - 1, Math.floor(p * vals.length))];
  const breaks = [q(1 / 6), q(2 / 6), q(3 / 6), q(4 / 6), q(5 / 6)];
  const ramp = RAMPS[LAYERS[key].ramp];
  return { color: (v) => (typeof v !== "number" ? "#1A2530" : ramp[breaks.filter((b) => v >= b).length]), min: vals[0], max: vals[vals.length - 1], ramp };
}

class SvgMap {
  constructor(host) {
    this.svg = sv("svg", { role: "group", "aria-label": "Tract map" });
    this.gTracts = sv("g"); this.gReach = sv("g"); this.gPins = sv("g");
    this.svg.append(this.gTracts, this.gReach, this.gPins);
    host.append(this.svg);
    this.zoom = 1;
  }
  project(lon, lat) { return [(lon - this.minLon) * this.kx * 1000, (this.maxLat - lat) * 1000]; }
  setTracts(fc, onClick) {
    const all = [];
    fc.features.forEach((f) => (f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates)
      .forEach((p) => p.forEach((ring) => ring.forEach((pt) => all.push(pt)))));
    this.minLon = Math.min(...all.map((p) => p[0])); const maxLon = Math.max(...all.map((p) => p[0]));
    this.minLat = Math.min(...all.map((p) => p[1])); this.maxLat = Math.max(...all.map((p) => p[1]));
    this.kx = Math.cos(((this.minLat + this.maxLat) / 2) * Math.PI / 180);
    this.w = (maxLon - this.minLon) * this.kx * 1000; this.h = (this.maxLat - this.minLat) * 1000;
    this.unit = this.h;
    this.applyZoom();
    this.svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    this.paths = fc.features.map((f) => {
      const polys = f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates;
      const d = polys.map((p) => p.map((ring) => "M" + ring.map(([lon, lat]) => this.project(lon, lat).map((n) => n.toFixed(2)).join(",")).join("L") + "Z").join("")).join("");
      const path = sv("path", { d, class: "tract", "fill-rule": "evenodd", onclick: () => onClick(f) });
      return { f, path };
    });
    this.gTracts.replaceChildren(...this.paths.map((p) => p.path));
  }
  applyZoom() {
    const pad = Math.max(this.w, this.h) * 0.03;
    const W = (this.w + 2 * pad) / this.zoom, H = (this.h + 2 * pad) / this.zoom;
    const cx = this.cx ?? this.w / 2, cy = this.cy ?? this.h / 2;
    this.svg.setAttribute("viewBox", `${cx - W / 2} ${cy - H / 2} ${W} ${H}`);
  }
  zoomBy(f) { this.zoom = Math.min(6, Math.max(1, this.zoom * f)); if (this.zoom === 1) { this.cx = this.cy = undefined; } this.applyZoom(); }
  style(colorFor) { (this.paths || []).forEach(({ f, path }) => path.setAttribute("fill", colorFor(f))); }
  setSites(fc, selected, onPick) {
    this.gReach.replaceChildren(); this.gPins.replaceChildren();
    if (!fc || this.minLon === undefined) return;
    const r = this.unit / 32;
    for (const f of fc.features) {
      const p = f.properties;
      if (p.feature_type === "catchment") {
        const ring = f.geometry.coordinates[0];
        const d = "M" + ring.map(([lon, lat]) => this.project(lon, lat).map((n) => n.toFixed(2)).join(",")).join("L") + "Z";
        this.gReach.append(sv("path", { d, class: "reach" }));
      }
    }
    for (const f of fc.features) {
      const p = f.properties;
      if (p.feature_type !== "recommended_site" && p.feature_type !== "runner_up_site") continue;
      const [x, y] = this.project(...f.geometry.coordinates);
      const runner = p.feature_type === "runner_up_site";
      const on = p.rank === selected;
      const g = sv("g", { class: `pin${runner ? " runner" : ""}`, tabindex: "0", role: "button",
        "aria-label": `${runner ? "Passed-over site" : "Site"} ${p.rank}, ${p.label}`,
        onclick: () => onPick(p.rank), onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(p.rank); } } },
      sv("circle", { class: "face", cx: x, cy: y, r: on ? r * 1.3 : r }),
      sv("text", { x, y, "font-size": r * 1.1, text: String(p.rank) }));
      if (on) g.classList.add("on");
      this.gPins.append(g);
    }
  }
}

const DARK_STYLE = [
  { elementType: "geometry", stylers: [{ color: "#0E1A24" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#A8B6C4" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#0B1620" }] },
  { featureType: "road", elementType: "geometry", stylers: [{ color: "#22364A" }] },
  { featureType: "road.highway", elementType: "geometry", stylers: [{ color: "#3A5168" }] },
  { featureType: "water", elementType: "geometry", stylers: [{ color: "#0B2540" }] },
  { featureType: "poi", stylers: [{ visibility: "off" }] },
  { featureType: "transit", stylers: [{ visibility: "off" }] },
];

class GoogleMap {
  constructor(host) {
    this.map = new google.maps.Map(host, {
      center: { lat: 33.749, lng: -84.388 }, zoom: 11, styles: DARK_STYLE,
      mapTypeControl: false, streetViewControl: false, fullscreenControl: true, clickableIcons: false,
    });
    this.overlays = [];
  }
  setTracts(fc, onClick) {
    this.map.data.forEach((f) => this.map.data.remove(f));
    this.map.data.addGeoJson(fc);
    this.map.data.addListener("click", (e) => {
      const props = {}; e.feature.forEachProperty((v, k) => { props[k] = v; });
      onClick({ properties: props, latLng: e.latLng });
    });
  }
  style(colorFor) {
    this.map.data.setStyle((feature) => {
      const props = {}; feature.forEachProperty((v, k) => { props[k] = v; });
      return { fillColor: colorFor({ properties: props }), fillOpacity: 0.72, strokeColor: "#070F16", strokeWeight: 0.6 };
    });
  }
  setSites(fc, selected, onPick) {
    this.overlays.forEach((o) => o.setMap(null)); this.overlays = [];
    if (!fc) return;
    for (const f of fc.features) {
      const p = f.properties;
      if (p.feature_type === "catchment") {
        this.overlays.push(new google.maps.Polygon({
          map: this.map, paths: f.geometry.coordinates[0].map(([lng, lat]) => ({ lat, lng })), clickable: false,
          strokeColor: "#FDBA74", strokeOpacity: 0.85, strokeWeight: 1.5, fillColor: "#FB923C", fillOpacity: 0.1,
        }));
      } else if (p.feature_type === "recommended_site" || p.feature_type === "runner_up_site") {
        const runner = p.feature_type === "runner_up_site";
        const [lng, lat] = f.geometry.coordinates;
        const m = new google.maps.Marker({
          map: this.map, position: { lat, lng }, title: `${runner ? "Passed over" : "Site"} ${p.rank}`,
          label: { text: String(p.rank), color: runner ? "#CBD5E1" : "#0B1620", fontWeight: "700" },
          icon: { path: google.maps.SymbolPath.CIRCLE, scale: p.rank === selected ? 15 : 12,
            fillColor: runner ? "#334155" : "#F8FAFC", fillOpacity: 1,
            strokeColor: p.rank === selected ? "#FB923C" : "#0B1620", strokeWeight: p.rank === selected ? 4 : 2 },
        });
        m.addListener("click", () => onPick(p.rank));
        this.overlays.push(m);
      }
    }
  }
}

function loadGoogleMaps(key) {
  return new Promise((resolve, reject) => {
    window.__mapsReady = resolve;
    const s = document.createElement("script");
    s.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&v=weekly&callback=__mapsReady`;
    s.async = true; s.onerror = () => reject(new Error("Google Maps failed to load"));
    document.head.append(s);
    setTimeout(() => reject(new Error("Google Maps timed out")), 10000);
  });
}

function renderLayer() {
  const L = LAYERS[state.layer];
  $("#mapTitle").textContent = `${state.city} · ${L.title}`;
  $("#mapSub").textContent = L.sub;
  document.querySelectorAll(".seg button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.layer === state.layer)));
  if (!state.tracts || !state.map) return;
  state.scale = makeScale(state.tracts.features, state.layer);
  state.map.style((f) => state.scale.color(f.properties[state.layer]));
  $("#legend").replaceChildren(
    el("span", { text: L.lo }),
    el("span", { class: "ramp", "aria-hidden": "true" }, state.scale.ramp.map((c) => el("span", { style: `background:${c}` }))),
    el("span", { text: L.hi }),
  );
}

function renderMapSites() {
  if (!state.map) return;
  state.map.setSites(state.viz?.map_geojson, state.selected, pickSite);
}

function pickSite(rank) {
  state.selected = rank;
  renderMapSites(); renderSiteCard();
  document.querySelectorAll(".sitelist button").forEach((b) => b.setAttribute("aria-pressed", String(+b.dataset.rank === rank)));
  if (!$("#page-sites").hidden) renderSites();
}

function showTract(f) {
  const p = f.properties;
  const card = $("#tractCard");
  card.replaceChildren(
    el("h2", { text: `Tract ${p.geo_id}` }),
    el("dl", {},
      el("dt", { text: "Heat offset" }), el("dd", { text: fmtF(p.predicted_offset_f) }),
      el("dt", { text: "No car" }), el("dd", { text: fmtPct(p.no_vehicle_rate, 1) }),
      el("dt", { text: "Poverty" }), el("dd", { text: fmtPct(p.poverty_rate, 1) }),
      el("dt", { text: "Age 65+" }), el("dd", { text: fmtPct(p.share_65_plus, 1) }),
      el("dt", { text: "Population" }), el("dd", { text: fmtNum(p.population) })),
    el("div", { class: "row" },
      el("button", { type: "button", class: "primary", text: "Ask why", onclick: () => {
        card.hidden = true;
        send(`Why does tract ${p.geo_id} run ${p.predicted_offset_f >= 0 ? "hotter" : "cooler"} than the city average?`);
      } }),
      el("button", { type: "button", text: "Close", onclick: () => { card.hidden = true; } })),
  );
  card.hidden = false;
}

function renderSiteCard() {
  const card = $("#siteCard");
  const r = row(state.selected);
  if (!r) { card.hidden = true; return; }
  const b = bars(r.rank)?.bars || [];
  const max = Math.max(0.01, ...b.map((x) => Math.abs(x.attribution_f)));
  card.replaceChildren(
    el("div", { class: "sc-id" },
      el("span", { class: "num big-num", text: String(r.rank) }),
      el("div", {},
        el("strong", { text: nameOf(r) }),
        el("small", { class: r.funded ? "ok" : "muted", text: `${r.funded ? "FUNDED" : "PASSED OVER"} · Tract ${r.geo_id}` }))),
    el("div", { class: "sc-off" },
      el("div", { class: "big", text: fmtF(r.predicted_offset_f, 2) }),
      el("small", { text: "vs. city average" })),
    el("ul", { class: "drivers compact", "aria-label": "Top drivers from EXPLAIN_PREDICT" },
      b.slice(0, 4).map((x) => el("li", {},
        el("span", { text: x.label }),
        el("span", { class: "bar", "aria-hidden": "true" },
          el("span", { style: `width:${Math.round((Math.abs(x.attribution_f) / max) * 100)}%;background:${x.effect === "adds_heat" ? "var(--heat)" : "var(--cool)"}` })),
        el("span", { class: "val", text: fmtF(x.attribution_f) })))),
    el("a", { class: "more", href: "#sites", text: "Full breakdown →" }),
  );
  card.hidden = false;
}

function renderPips() {
  $("#count").textContent = state.count;
  $("#dec").disabled = state.count <= 1 || state.busy; $("#inc").disabled = state.count >= 5 || state.busy;
  $("#countPips").replaceChildren(...[1, 2, 3, 4, 5].map((i) => el("span", { class: i <= state.count ? "on" : "" })));
}

// ------------------------------------------------------------------ chat

const TOOL_LABELS = {
  rank_sites_pool: "BQML grid · ranked candidates",
  explain_point: "BQML · EXPLAIN_PREDICT",
  vulnerable_population: "MCP Toolbox · who lives nearby",
  site_hot_days: "7 yrs station history · hot days",
  city_heat_days_by_year: "7 yrs station history",
  tract_profile: "MCP Toolbox · ACS tracts",
  equity_audit: "Audit of our own output",
  city_baseline: "Atlanta baseline",
  hottest_measured_cells: "Heat Watch cells",
  hottest_predicted_cells: "BQML grid",
};

function addMessage(kind, who, ...content) {
  const node = el("div", { class: `msg ${kind}` }, who ? el("div", { class: "who", text: who }) : null, ...content);
  $("#messages").append(node);
  node.scrollIntoView({ block: "end", behavior: reduced() ? "auto" : "smooth" });
  return node;
}

function traceFor(resp) {
  const steps = [{ tool: "read_question", what: `what is being asked · ${resp.intent?.intent_type || "?"}` }]
    .concat((resp.citations || []).map((c) => ({ tool: c.mcp_tool_name || c.tool_name, what: TOOL_LABELS[c.mcp_tool_name] || c.sql_object, ms: c.latency_ms })));
  if (resp.verification) steps.push({ tool: "verify_numbers", what: resp.verification.passed ? "every number checked against the data" : "fell back to a template", ok: resp.verification.passed });
  const list = el("ol", { class: "trace-list" });
  const play = () => {
    list.replaceChildren(...steps.map((s) => el("li", {},
      el("span", { class: "spin", "aria-hidden": "true" }),
      el("code", { class: "tool", text: s.tool }),
      el("span", { class: "what", text: s.what }),
      el("span", { class: "state", text: "running" }))));
    [...list.children].forEach((li, i) => setTimeout(() => {
      li.firstChild.replaceWith(el("span", { class: `tick${steps[i].ok === false ? " warn" : ""}`, "aria-hidden": "true", text: steps[i].ok === false ? "!" : "✓" }));
      li.querySelector(".state").textContent = "done";
    }, reduced() ? 0 : 160 * (i + 1)));
  };
  play();
  return el("div", { class: "trace" },
    el("div", { class: "trace-head" }, el("span", { text: "Agent trace" }),
      el("button", { type: "button", class: "ghost small", text: "↻ Replay", onclick: play })),
    list);
}

function siteList() {
  return el("div", { class: "sitelist", role: "group", "aria-label": "Recommended sites" },
    funded().map((r) => el("button", { type: "button", "data-rank": r.rank, "aria-pressed": String(r.rank === state.selected),
      onclick: () => pickSite(r.rank) },
      el("span", { class: "num", text: String(r.rank) }),
      el("strong", { text: nameOf(r) }),
      el("span", { class: "off", text: fmtF(r.predicted_offset_f) }),
      el("span", { class: "reach", text: r.residents_reached ? `${fmtNum(r.residents_reached)} reached` : "" }))));
}

function setBusy(b) {
  state.busy = b;
  $("#askBtn").disabled = b; $("#askInput").disabled = b;
  document.querySelectorAll("[data-busy]").forEach((x) => { x.disabled = b; });
  renderPips();
}

async function send(text, { page } = {}) {
  text = (text || "").trim();
  if (!text || state.busy) return;
  addMessage("user", `Planner · ${new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`, el("div", { class: "bubble", text }));
  $("#askInput").value = "";
  setBusy(true);
  const thinking = addMessage("agent", "Heat Planner agent", el("div", { class: "thinking" }, el("span", { class: "spin", "aria-hidden": "true" }), "Working on it"));
  const message = state.city !== state.cfg.city ? `[City selected: ${state.city}] ${text}` : text;
  try {
    const resp = await getJSON("/api/plan", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.cfg.sessionId, message }),
    });
    thinking.remove();
    onResponse(resp);
    if (page && resp.status === "ok") go(page);
  } catch (e) {
    thinking.remove();
    addMessage("agent error", "Heat Planner agent", el("div", { class: "body", text: `Couldn’t reach the agent (${e.message}).` }));
  } finally {
    setBusy(false);
  }
}

function onResponse(resp) {
  const ok = resp.status === "ok";
  if (ok && resp.viz_spec && resp.viz_spec.primary_view !== "empty") {
    state.resp = resp; state.viz = resp.viz_spec;
    if (!row(state.selected)?.funded) state.selected = funded()[0]?.rank || 1;
    state.count = funded().length || state.count;
    state.showCompare = resp.intent?.intent_type === "compare_sites";
    renderMapSites(); renderSiteCard(); renderPips(); renderSuggestions();
  }
  if (!ok) {
    const label = resp.status === "needs_clarification" ? "Heat Planner agent · needs one detail" : "Heat Planner agent · declined to guess";
    addMessage(`agent refusal`, label, el("div", { class: "body", html: true }),
      state.city !== state.cfg.city ? el("button", { type: "button", class: "primary", text: `Switch back to ${state.cfg.city}`, onclick: () => pickCity(state.cfg.city) }) : null)
      .querySelector(".body").innerHTML = md(resp.narrative || resp.intent?.refusal_explanation || "I can’t answer that from the data I have.");
    return;
  }
  const body = el("div", { class: "body" });
  body.innerHTML = md(resp.narrative, resp.citations);
  const intent = resp.intent?.intent_type;
  const extras = [];
  if (["site_selection", "demographics", "generic_data"].includes(intent) && funded().length) {
    extras.push(siteList(), el("p", { class: "fine", text: "Offset = how much hotter than Atlanta’s average on the campaign day, not a forecast. “Nearby” is straight-line distance." }));
  }
  const follow = el("div", { class: "follow" },
    runnerUps().length ? el("button", { type: "button", "data-busy": "", text: `Why not site ${runnerUps()[0].rank}?`, onclick: () => send(`Why not site ${runnerUps()[0].rank}?`, { page: "sites" }) }) : null,
    el("button", { type: "button", text: "Run the equity audit", onclick: () => go("audit") }),
    el("button", { type: "button", "data-busy": "", class: "primary", text: "Draft the council proposal", onclick: () => draftProposal() }));
  addMessage("agent", "Heat Planner agent", traceFor(resp), body, ...extras, follow);
  if (resp.viz_spec?.mock) $("#mockBanner").hidden = false;
}

function draftProposal() {
  send(`Draft the council proposal for these ${funded().length || state.count} sites, with the equity audit.`, { page: "proposal" });
}

function renderSuggestions() {
  const first = funded()[0];
  const qs = [
    `How often does ${state.cfg.city} reach 95°F?`,
    first ? `Who lives within 800 m of site 1?` : null,
    first ? null : defaultQuestion(),
  ].filter(Boolean);
  $("#suggest").replaceChildren(...qs.map((q) => el("button", { type: "button", "data-busy": "", text: q, onclick: () => send(q) })));
}

// ------------------------------------------------------------------ Sites page

function wrapLabel(text, max) {
  const lines = [];
  for (const w of text.split(" ")) {
    const last = lines[lines.length - 1];
    if (last && (last + " " + w).length <= max) lines[lines.length - 1] = last + " " + w; else lines.push(w);
  }
  return lines.slice(0, 2);
}

function waterfall(b) {
  const items = b.bars.map((x) => ({ label: x.label, v: x.attribution_f }));
  const sum = items.reduce((a, x) => a + x.v, 0);
  if (b.site_offset_f !== null && Math.abs(b.site_offset_f - sum) >= 0.005) items.push({ label: "Other features", v: b.site_offset_f - sum, other: true });
  const W = 760, H = 310, top = 34, base = 250, left = 10;
  let acc = 0;
  const steps = items.map((x) => { const s = { ...x, from: acc, to: acc + x.v }; acc += x.v; return s; });
  const total = { label: "Site offset", from: 0, to: b.site_offset_f ?? acc, total: true };
  const all = [...steps, total];
  const hi = Math.max(0.01, ...all.map((s) => Math.max(s.from, s.to))), lo = Math.min(0, ...all.map((s) => Math.min(s.from, s.to)));
  const y = (v) => top + (hi - v) / (hi - lo) * (base - top);
  const slot = (W - left * 2) / all.length, bw = Math.min(110, slot * 0.68);
  const g = all.map((s, i) => {
    const x = left + i * slot + (slot - bw) / 2;
    const y1 = y(Math.max(s.from, s.to)), y2 = y(Math.min(s.from, s.to));
    const cls = s.total ? "wf total" : s.v < 0 ? "wf cool" : s.other ? "wf other" : "wf heat";
    const v = s.total ? s.to : s.v;
    return sv("g", {},
      sv("rect", { class: cls, x, y: y1, width: bw, height: Math.max(2, y2 - y1), rx: 4 }),
      sv("text", { class: "wf-val", x: x + bw / 2, y: y1 - 8, text: fmtF(v) }),
      sv("text", { class: "wf-lab", x: x + bw / 2, y: base + 22 }, ...wrapLabel(s.label, 14).map((t, k) => sv("tspan", { x: x + bw / 2, dy: k ? 17 : 0, text: t }))),
      i < all.length - 1 && !s.total ? sv("line", { class: "wf-link", x1: x + bw, x2: x + slot, y1: y(s.to), y2: y(s.to) }) : null);
  });
  return sv("svg", { class: "waterfall", viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": `Feature contributions stacking to ${fmtF(total.to)}: ` + items.map((s) => `${s.label} ${fmtF(s.v)}`).join(", ") },
  sv("line", { class: "wf-base", x1: 0, x2: W, y1: y(0), y2: y(0) }), g);
}

function renderSites() {
  const host = $("#sitesBody");
  const picker = $("#sitePicker");
  if (!state.viz) { picker.replaceChildren(); needSites(host, "sites"); return; }
  picker.replaceChildren(...funded().map((r) => el("button", { type: "button", "aria-pressed": String(r.rank === state.selected), onclick: () => pickSite(r.rank) },
    el("span", { class: "num", text: String(r.rank) }), nameOf(r))));
  const r = row(state.selected), d = detail(state.selected), b = bars(state.selected);
  if (!r || !d) { host.replaceChildren(el("p", { class: "empty", text: "Pick a site." })); return; }
  const ru = runnerUps()[0];
  const cmp = state.viz.comparison;
  host.replaceChildren(
    el("div", { class: "sites-grid" },
      el("div", { class: "card" },
        el("div", { class: "card-head" },
          el("h2", { text: d.title }),
          el("div", { class: "big-off" }, el("span", { class: "big", text: fmtF(r.predicted_offset_f) }), el("small", { text: "vs. city average" }))),
        b ? el("div", { class: "wf-scroll" }, waterfall(b)) : el("p", { class: "empty", text: "No attributions returned for this site." }),
        el("div", { class: "wf-key" },
          el("span", { class: "k heat", text: "Adds heat" }), el("span", { class: "k cool", text: "Reduces heat" }),
          el("span", { class: "k total", text: "Site offset" }),
          el("span", { class: "fine", text: "From ML.EXPLAIN_PREDICT on offset_model_v1" })),
        d.diagnosis ? el("div", { class: "diag" },
          el("span", { class: "diag-icon", "aria-hidden": "true", text: "⌕" }),
          el("div", {}, el("small", { text: "DIAGNOSIS · DOMINANT DRIVER" }), el("strong", { text: b?.dominant_driver || "" }), el("p", { text: d.diagnosis }))) : null),
      el("div", { class: "side" },
        el("div", { class: "stat-grid" },
          stat("≥95°F days / summer", d.hot_days_ge_95 !== null ? d.hot_days_ge_95.toFixed(0) : "—", d.city_hot_days_ge_95 !== null ? `city ${d.city_hot_days_ge_95.toFixed(0)}` : null),
          stat("Residents nearby", fmtNum(d.residents_nearby), d.radius_m ? `within ${fmtNum(d.radius_m)} m` : null),
          stat("Est. annual cost", d.cost_label, "needs finance"),
          stat("Location", `${d.lat.toFixed(4)}, ${d.lon.toFixed(4)}`, `Tract ${d.geo_id}`, true)),
        el("div", { class: "card" },
          el("h3", { text: `Who lives here vs. ${state.cfg.city}` }),
          d.who_lives_here.map((c) => el("div", { class: "cmp" },
            el("div", { class: "cmp-label", text: c.label }),
            cmpLine("Site", c.site_value, "var(--heat)"), cmpLine("City", c.city_value, "#7C8DA0")))),
        el("div", { class: "links" },
          d.maps_url ? el("a", { href: d.maps_url, target: "_blank", rel: "noopener", text: "Open in Google Maps" }) : null,
          d.walking_url ? el("a", { href: d.walking_url, target: "_blank", rel: "noopener", text: "Walking directions" }) : null))),
    ru ? el("div", { class: "card whynot" },
      el("div", {},
        el("h2", { text: `Why not site ${ru.rank}?` }),
        el("p", { text: ru.passed_over_reason || `${nameOf(ru)} ranked ${ru.rank}th. Each pick must reach people the earlier picks missed.` })),
      el("button", { type: "button", class: "outline", "aria-expanded": String(state.showCompare), text: state.showCompare ? "Hide comparison" : `Compare with site ${ru.rank}`,
        onclick: () => { state.showCompare = !state.showCompare; renderSites(); } }),
      state.showCompare && cmp ? el("table", { class: "cmp-table" },
        el("thead", {}, el("tr", {}, el("th", { text: "" }), el("th", { text: `Site ${cmp.funded_rank} (funded)` }), el("th", { text: `Site ${cmp.runner_up_rank}` }), el("th", { text: "Difference" }))),
        el("tbody", {}, cmp.rows.map((x) => el("tr", {}, el("th", { text: x.label }), el("td", { text: x.funded }), el("td", { text: x.runner_up }), el("td", { text: x.delta ?? "—" }))))) : null) : null,
    el("p", { class: "footchips" }, ["Offsets: one campaign day", "Reach: straight-line", "Costs: placeholders", "Predicts exposure, not health outcomes"].map((t) => el("span", { text: t }))),
  );
}

function stat(label, value, note, small) {
  return el("div", { class: "stat" }, el("small", { text: label }), el("strong", { class: small ? "smallval" : "", text: value }), note ? el("span", { text: note }) : null);
}
function cmpLine(label, v, color) {
  return el("div", { class: "line" }, el("span", { text: label }),
    el("span", { class: "bar", "aria-hidden": "true" }, el("span", { style: `width:${Math.round(Math.min(1, v) * 100)}%;background:${color}` })),
    el("span", { class: "val", text: fmtPct(v, 1) }));
}

// ------------------------------------------------------------------ Audit page

function scatter(sc) {
  const W = 560, H = 420, L = 44, R = 12, T = 12, B = 40;
  const xs = sc.points.map((p) => p.predicted_offset_f);
  const span = (Math.max(...xs) - Math.min(...xs)) || 1;
  const x0 = Math.min(...xs) - span * 0.06, x1 = Math.max(...xs) + span * 0.06;
  const x = (v) => L + (v - x0) / (x1 - x0) * (W - L - R);
  const y = (v) => T + 30 + (1 - v) * (H - T - B - 44);
  const sx = x(sc.offset_split_f), sy = y(sc.vulnerability_split);
  const dots = [], marks = [];
  for (const p of sc.points) {
    if (p.site_rank && state.highlight) {
      marks.push(sv("g", { class: `sdot ${p.funded ? "funded" : "runner"}` },
        sv("circle", { cx: x(p.predicted_offset_f), cy: y(p.vulnerability), r: 13 }),
        sv("text", { x: x(p.predicted_offset_f), y: y(p.vulnerability), text: String(p.site_rank) })));
    } else {
      dots.push(sv("circle", { class: "tdot", cx: x(p.predicted_offset_f), cy: y(p.vulnerability), r: 4 }));
    }
  }
  return sv("svg", { class: "scatter", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Each census tract by predicted heat offset and vulnerability; our sites are numbered" },
    sv("rect", { class: "plot", x: L, y: T, width: W - L - R, height: H - T - B }),
    sv("rect", { class: "quad", x: sx, y: T, width: W - R - sx, height: sy - T }),
    sv("line", { class: "split", x1: sx, x2: sx, y1: T, y2: H - B }), sv("line", { class: "split", x1: L, x2: W - R, y1: sy, y2: sy }),
    sv("text", { class: "qlab", x: L + 8, y: T + 18, text: "Vulnerable, cooler" }),
    sv("text", { class: "qlab hot", x: W - R - 8, y: T + 18, "text-anchor": "end", text: "Hot + vulnerable" }),
    sv("text", { class: "qlab", x: W - R - 8, y: H - B - 10, "text-anchor": "end", text: "Hot, lower need" }),
    sv("text", { class: "axis", x: (L + W - R) / 2, y: H - 10, "text-anchor": "middle", text: "Predicted heat offset →" }),
    sv("text", { class: "axis", x: 14, y: (T + H - B) / 2, "text-anchor": "middle", transform: `rotate(-90 14 ${(T + H - B) / 2})`, text: "Vulnerability (no car, 65+) →" }),
    dots, marks);
}

function renderAudit() {
  const host = $("#auditBody");
  const v = state.viz;
  if (!v || !v.audit_summary) { needSites(host, "audit"); return; }
  const s = v.audit_summary;
  const arrow = (r) => (r.sites_value > r.city_value ? "↑" : r.sites_value < r.city_value ? "↓" : "=");
  const short = { median_income: "Income", poverty_rate: "Poverty", no_vehicle_rate: "No car", share_65_plus: "65+" };
  const ru = runnerUps()[0];
  host.replaceChildren(
    el("div", { class: `verdict${s.measures_toward_need * 2 > s.measures_total ? "" : " note"}` },
      el("div", { class: "score" }, el("span", { class: "n", text: String(s.measures_toward_need) }), el("span", { text: `of ${s.measures_total} measures` })),
      el("div", { class: "vtext" }, el("small", { text: "VERDICT" }), el("strong", { text: s.verdict }),
        s.detail ? el("p", { class: "vdetail", text: s.detail }) : null),
      el("div", { class: "vchips" }, v.audit_table.map((r) => el("span", { class: r.toward_need ? "good" : "", text: `${short[r.measure]} · ${arrow(r)}` })))),
    el("div", { class: "audit-grid" },
      el("div", { class: "card" },
        el("div", { class: "card-head" },
          el("div", {}, el("h2", { text: "Where it’s hot vs. where heat hurts" }), el("p", { class: "sub", text: "Each dot is a census tract" })),
          el("button", { type: "button", class: state.highlight ? "primary small" : "outline small", "aria-pressed": String(state.highlight),
            text: state.highlight ? "Highlight our sites" : "Highlight our sites", onclick: () => { state.highlight = !state.highlight; renderAudit(); } })),
        v.audit_scatter ? scatter(v.audit_scatter) : el("p", { class: "empty", text: "The tract layer isn’t available from the agent API yet, so the scatter can’t be drawn." }),
        el("p", { class: "fine", text: [ru ? `Site ${ru.rank} (dashed) ${ru.passed_over_reason ? "— " + ru.passed_over_reason.charAt(0).toLowerCase() + ru.passed_over_reason.slice(1) : "was passed over."}` : "", v.audit_scatter?.note || ""].filter(Boolean).join(" ") })),
      el("div", { class: "card" },
        el("div", { class: "card-head" },
          el("h2", { text: `Recommended tracts vs. ${state.cfg.city}` }),
          el("div", { class: "key" }, el("span", { text: "Our sites" }), el("span", { class: "city", text: `${state.cfg.city} average` }))),
        v.audit_table.map((r) => {
          const max = Math.max(r.sites_value, r.city_value) || 1;
          return el("div", { class: "metric" },
            el("div", { class: "mhead" }, el("strong", { text: r.label }), el("small", { text: r.higher_means_need ? (r.measure === "no_vehicle_rate" ? "Higher = harder to reach relief" : r.measure === "share_65_plus" ? "Higher = more heat risk" : "Higher = more need") : "Lower = more need" })),
            el("div", { class: "line" }, el("span", { class: "bar", "aria-hidden": "true" }, el("span", { style: `width:${Math.round(r.sites_value / max * 100)}%;background:var(--heat)` })), el("span", { class: "val hot", text: r.display_sites })),
            el("div", { class: "line" }, el("span", { class: "bar", "aria-hidden": "true" }, el("span", { style: `width:${Math.round(r.city_value / max * 100)}%;background:#7C8DA0` })), el("span", { class: "val", text: r.display_city })));
        }),
        el("div", { class: "race" },
          el("button", { type: "button", class: "outline", "aria-expanded": String(state.showRace), text: state.showRace ? "Hide racial composition" : "Show racial composition (audit only)",
            onclick: () => { state.showRace = !state.showRace; renderAudit(); } }),
          state.showRace ? (v.racial_composition.length
            ? el("table", { class: "cmp-table" },
              el("thead", {}, el("tr", {}, el("th", { text: "Group" }), el("th", { text: "Our sites’ tracts" }), el("th", { text: state.cfg.city }))),
              el("tbody", {}, v.racial_composition.map((x) => el("tr", {}, el("th", { text: x.group }), el("td", { text: fmtPct(x.sites_share, 1) }), el("td", { text: fmtPct(x.city_share, 1) })))))
            : el("p", { class: "fine", text: "The agent API didn’t return a racial composition check." })) : null,
          state.showRace ? el("p", { class: "fine", text: "Shown only to audit the output. Race is never a model input or a ranking factor." }) : null))),
    el("div", { class: "actions" },
      el("button", { type: "button", class: "primary", text: "Add audit to council proposal →", onclick: () => go("proposal") }),
      el("button", { type: "button", class: "outline", text: "Back to sites", onclick: () => go("sites") })),
  );
}

// ------------------------------------------------------------------ Proposal page

function proposalText(p) {
  const lines = [`PROPOSAL TO COUNCIL · DRAFT`, p.title, `To: ${p.to}`, `From: ${p.from}`, `Date: ${p.date}`, "",
    "Recommendation", p.recommendation, "", "The sites",
    ...p.sites.map((s) => `${s.rank} · ${s.name} | ${s.location} | ${s.offset} | ≥95°F days ${s.hot_days_ge_95} | nearby ${s.nearby} | ${s.cost}`), "",
    "Why these", p.why_these || "[to be drafted]", "", "What this displaces", p.what_this_displaces || "[to be drafted]", "",
    "Equity check", p.equity_check || "[run the audit]", "", "Limits of this analysis", ...p.limitations.map((l) => `- ${l}`)];
  return lines.join("\n").replace(/\[(P\d+)\]/g, "[$1]");
}

function renderProposal() {
  const host = $("#proposalBody");
  const p = state.viz?.proposal;
  if (!p) { needSites(host, "proposal"); return; }
  const ready = p.checklist.filter((c) => c.done).length / Math.max(1, p.checklist.length);
  const cites = state.resp?.citations || [];
  const prose = (t, fallback) => { const d = el("p"); d.innerHTML = t ? cite(esc(t), cites) : `<span class="ph">${esc(fallback)}</span>`; return d; };
  const copyBtn = el("button", { type: "button", class: "outline", text: "Copy text", onclick: async () => {
    try { await navigator.clipboard.writeText(proposalText(p)); copyBtn.textContent = "Copied"; } catch (_) { copyBtn.textContent = "Copy failed"; }
    setTimeout(() => { copyBtn.textContent = "Copy text"; }, 1600);
  } });
  host.replaceChildren(
    el("div", { class: "pbar" },
      el("div", { class: "pstatus" },
        el("span", { class: "tick", "aria-hidden": "true", text: "✓" }),
        el("strong", { text: p.status_line || "Draft ready · review before sending" }),
        el("span", { class: "progress", "aria-hidden": "true" }, el("span", { style: `width:${Math.round(ready * 100)}%` }))),
      el("div", { class: "actions" },
        el("button", { type: "button", class: "outline", "data-busy": "", text: "Regenerate", onclick: () => draftProposal() }),
        copyBtn,
        el("button", { type: "button", class: "primary", text: "Export PDF", onclick: () => window.print() }))),
    el("div", { class: "proposal-grid" },
      el("article", { class: "paper", id: "proposalDoc" },
        el("p", { class: "kicker", text: "PROPOSAL TO COUNCIL · DRAFT" }),
        el("h1", { text: p.title }),
        el("dl", { class: "memo" }, el("dt", { text: "To" }), el("dd", { text: p.to }), el("dt", { text: "From" }), el("dd", { text: p.from }), el("dt", { text: "Date" }), el("dd", { text: p.date })),
        el("h2", {}, "Recommendation", ...p.source_badges.filter((b) => b !== "EXPLAIN_PREDICT").map((b) => el("span", { class: `badge b-${b.replace(/\W+/g, "").toLowerCase()}`, text: b }))),
        el("p", { text: p.recommendation }),
        el("h2", { text: `The ${p.sites.length === 3 ? "three" : p.sites.length} sites` }),
        el("table", {},
          el("thead", {}, el("tr", {}, ["Site", "Location", "Offset", "≥95°F days", "Nearby (no car · 65+)", "Est. cost / yr"].map((h) => el("th", { text: h })))),
          el("tbody", {}, p.sites.map((s) => el("tr", {},
            el("td", { text: `${s.rank} · ${s.name}` }), el("td", { class: "mono", text: s.location }), el("td", { class: "hot", text: s.offset }),
            el("td", { text: s.hot_days_ge_95 }), el("td", { text: s.nearby }), el("td", { text: s.cost }))))),
        el("h2", {}, `Why these ${p.sites.length === 3 ? "three" : ""}`.trim(), el("span", { class: "badge b-explain", text: "EXPLAIN_PREDICT" })),
        prose(p.why_these, "[Top drivers per site from the model, one sentence each. Ask the agent to draft the proposal.]"),
        el("h2", { text: "What this displaces" }),
        prose(p.what_this_displaces, "[Which site ranked next, why it wasn’t chosen, and what share of the budget line these use.]"),
        el("div", { class: "equity" }, el("h2", {}, "Equity check", el("span", { class: "badge b-audit", text: "Audit" })),
          prose(p.equity_check, "[Run the equity audit.]")),
        el("h2", { text: "Limits of this analysis" }),
        el("ul", {}, p.limitations.map((l) => el("li", { text: l })))),
      el("aside", { class: "pside" },
        el("div", { class: "card" },
          el("h2", { text: "Ready for council?" }),
          el("ul", { class: "check" }, p.checklist.map((c) => el("li", { class: c.done ? "done" : "" },
            el("span", { class: "cbox", "aria-hidden": "true", text: c.done ? "✓" : "" }),
            el("div", {}, el("span", { text: c.label }), el("small", { text: c.note || (c.done ? "done" : "needs a person") })))))),
        el("div", { class: "card" },
          el("h2", { text: "Human in the loop" }),
          el("p", { class: "sub", text: "The agent drafts; a planner reviews, edits and signs. Nothing goes to council without a person’s name on it." })))),
  );
}

// ------------------------------------------------------------------ city

function buildCityMenu() {
  const item = (name, note, loaded) => el("button", { type: "button", "aria-current": String(state.city === name), onclick: () => pickCity(name) },
    el("span", { class: `pip${loaded ? " on" : ""}`, "aria-hidden": "true" }), el("span", {}, name, el("small", { text: note })));
  $("#cityMenu").replaceChildren(
    el("h2", { text: "Loaded" }), item(state.cfg.city, "Ready", true),
    el("h2", { text: "Available, not loaded" }), ...state.cfg.availableCities.map((c) => item(c.name, c.note, false)),
    el("p", { class: "menu-note", text: "Offsets are relative to each city’s own average, so every city needs its own data load and model check." }));
}
function toggleCityMenu(open) {
  const btn = $("#cityBtn");
  const isOpen = open ?? btn.getAttribute("aria-expanded") !== "true";
  btn.setAttribute("aria-expanded", String(isOpen));
  $("#cityMenu").hidden = !isOpen;
  if (isOpen) $("#cityMenu button")?.focus();
}
function pickCity(name) {
  state.city = name;
  $("#cityName").textContent = name;
  toggleCityMenu(false); buildCityMenu();
  const loaded = name === state.cfg.city;
  const overlay = $("#mapOverlay");
  overlay.hidden = loaded;
  if (!loaded) overlay.replaceChildren(el("div", {}, el("strong", { text: `No data loaded for ${name}` }),
    el("span", { text: "The agent won’t predict here until this city’s readings are loaded and the model is checked." })));
  renderLayer();
}

// ------------------------------------------------------------------ boot

async function init() {
  try { state.cfg = await getJSON("/api/config"); } catch (e) {
    $("#statusText").textContent = "Server unreachable"; $("#statusDot").className = "dot down"; return;
  }
  state.city = state.cfg.city;
  $("#cityName").textContent = state.city;
  $("#mockBanner").hidden = !state.cfg.mock;
  $("#statusText").textContent = state.cfg.mock ? "Mock agent · samples" : "Agent live · Cloud Run";
  $("#statusDot").className = `dot ${state.cfg.mock ? "mock" : "live"}`;
  document.title = `Heat Planner: ${state.city}`;
  buildCityMenu(); renderSuggestions(); renderPips();
  addMessage("agent", "Heat Planner agent", el("div", { class: "body" },
    el("p", { text: `Ask where ${state.city}’s cooling centers should go, ask about a street, or click a tract on the map.` })));

  const host = $("#map");
  try { state.tracts = await getJSON("/api/tracts"); } catch (e) {
    host.replaceChildren(el("p", { class: "empty", style: "padding:24px", text: `The tract map isn’t available: ${e.message}` }));
  }
  if (state.cfg.mapsKey) {
    try { await loadGoogleMaps(state.cfg.mapsKey); state.map = new GoogleMap(host); $("#mapSource").textContent = "Base map: Google Maps · Tracts: Census TIGER/Line"; }
    catch (_) { state.map = null; }
  }
  if (!state.map && state.tracts) { state.map = new SvgMap(host); $("#zoomCtl").hidden = false; }
  if (state.map && state.tracts) state.map.setTracts(state.tracts, showTract);
  renderLayer();
  route();
}

$("#askForm").addEventListener("submit", (e) => { e.preventDefault(); send($("#askInput").value); });
document.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => { state.layer = b.dataset.layer; renderLayer(); }));
$("#dec").addEventListener("click", () => { state.count = Math.max(1, state.count - 1); renderPips(); send(defaultQuestion()); });
$("#inc").addEventListener("click", () => { state.count = Math.min(5, state.count + 1); renderPips(); send(defaultQuestion()); });
$("#zoomIn").addEventListener("click", () => state.map?.zoomBy?.(1.4));
$("#zoomOut").addEventListener("click", () => state.map?.zoomBy?.(1 / 1.4));
$("#cityBtn").addEventListener("click", () => toggleCityMenu());
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#cityMenu").hidden) { toggleCityMenu(false); $("#cityBtn").focus(); } });
document.addEventListener("click", (e) => { if (!e.target.closest(".city")) toggleCityMenu(false); });
window.addEventListener("hashchange", route);

init();
