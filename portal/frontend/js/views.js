// Non-map views. Each is generated from the persona catalogue (/api/personas): the questions
// it will answer, how far the data gets us today, and what's left to build.
import { api } from "./api.js";

export const STATUS = {
  ready: "Ready now",
  needs_model: "Needs model",
  needs_agent: "Needs agent",
  needs_external: "Needs external data",
};

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// What each view still needs built. Names match the tools in the planning sheet.
const TODO = {
  today: {
    title: "To build: dispatch_plan",
    body: "Rank cells by predicted offset × residents 65+ × households without a car, then split them into one zone per truck or team (KMEANS). Show the ranked stops, and the zones on the map.",
  },
  decade: {
    title: "To build: explain_heat and rank_interventions",
    body: "Turn ML.EXPLAIN_PREDICT attributions into “+1.2°F from waterfront distance, −0.4°F from trees”. Rank blocks by the cause a city can change, and compare two blocks side by side.",
  },
  equity: {
    title: "To build: equity_audit",
    body: "Take the recommended cells, look up their tracts, and compare them with the Brooklyn baseline below. Race is used only here, after the fact, never as a model input.",
  },
  history: {
    title: "Next: dangerous days for every block",
    body: "Estimated days per block (city reference high + the block's offset) exist for driven blocks; see the “Estimated days ≥ 95°F” map layer. Unmeasured blocks get them once the model predicts their offset.",
  },
  ask: {
    title: "To build: connect the ADK agent",
    body: "POST /api/ask currently returns 501. Point it at the deployed agent (Agent Runtime or Cloud Run) and stream the reply here.",
  },
};

function coverageChips(questions) {
  const counts = {};
  questions.forEach((q) => { counts[q.status] = (counts[q.status] || 0) + 1; });
  return `<div class="coverage">${Object.keys(STATUS).filter((s) => counts[s])
    .map((s) => `<span class="chip ${s}">${counts[s]} · ${STATUS[s]}</span>`).join("")}</div>`;
}

function questionCards(questions) {
  if (!questions.length) return "";
  return `<div class="cards">${questions.map((q) => `
    <article class="card">
      <div class="card-who">${q.track === "today" ? "⚡ Today" : "🌳 Decade"} #${q.n} · ${esc(q.who)}</div>
      <div class="card-ask">“${esc(q.ask)}”</div>
      <span class="chip ${q.status}">${STATUS[q.status]}</span>
      <div class="card-gap">${esc(q.gap)}</div>
      ${q.layers.length ? `<div class="card-actions">
        <button type="button" class="link-btn" data-layer="${q.layers[0]}">Show on map →</button></div>` : ""}
    </article>`).join("")}</div>`;
}

function todoBlock(id) {
  const t = TODO[id];
  return t ? `<div class="todo"><h3>${t.title}</h3><div class="muted">${t.body}</div></div>` : "";
}

// ---------------------------------------------------------------- view-specific bodies
async function historyBody() {
  const { station, years } = await api.heatDays();
  return `
    <h3>Days per year at or above each threshold</h3>
    <p class="muted">${esc(station)}. Seven years is too short to call a trend.</p>
    <table class="data">
      <thead><tr><th>Year</th><th>≥ 90°F</th><th>≥ 95°F</th><th>≥ 100°F</th><th>Peak</th></tr></thead>
      <tbody>${years.map((y) => `<tr><td>${y.year}</td><td>${y.days_90}</td><td>${y.days_95}</td>
        <td>${y.days_100}</td><td>${y.peak_f.toFixed(0)}°F</td></tr>`).join("")}</tbody>
    </table>`;
}

async function equityBody() {
  const tracts = (await api.tracts()).features.map((f) => f.properties).filter((p) => p.borough === "Brooklyn");
  const pop = tracts.reduce((s, t) => s + (t.total_pop || 0), 0);
  const sum = (k) => tracts.reduce((s, t) => s + (t[k] || 0), 0);
  const wavg = (k) => {
    let num = 0, den = 0;
    tracts.forEach((t) => { if (typeof t[k] === "number" && t.total_pop) { num += t[k] * t.total_pop; den += t.total_pop; } });
    return den ? num / den : null;
  };
  const rows = [
    ["Residents", pop.toLocaleString()],
    ["Aged 65+", `${((sum("pop_65_plus") / pop) * 100).toFixed(1)}%`],
    ["Households without a car", `${((sum("no_cars") / sum("households")) * 100).toFixed(1)}%`],
    ["Poverty rate (population-weighted)", `${(wavg("poverty_rate") * 100).toFixed(1)}%`],
    ["Median income (population-weighted tract median)", `$${Math.round(wavg("median_income")).toLocaleString()}`],
  ];
  return `
    <h3>Brooklyn baseline</h3>
    <p class="muted">${tracts.length} Brooklyn tracts in the grid · ACS 2019 5-year. The audit compares recommended tracts against these.</p>
    <table class="data"><thead><tr><th>Measure</th><th>Brooklyn</th><th>Recommended</th></tr></thead>
      <tbody>${rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td><td class="muted">—</td></tr>`).join("")}</tbody>
    </table>`;
}

function askBody(prefill) {
  return `
    <div class="chat">
      <textarea id="ask-input" placeholder="e.g. We can fund three cooling centers this summer. Where should they go?">${esc(prefill || "")}</textarea>
      <div><button type="button" class="link-btn" id="ask-send">Send</button></div>
      <div id="ask-reply"></div>
    </div>`;
}

function wireAsk(root) {
  const send = root.querySelector("#ask-send");
  if (!send) return;
  send.addEventListener("click", async () => {
    const msg = root.querySelector("#ask-input").value.trim();
    const out = root.querySelector("#ask-reply");
    if (!msg) return;
    out.innerHTML = `<div class="chat-reply muted">Sending…</div>`;
    const r = await api.ask(msg);
    const body = await r.json().catch(() => ({}));
    out.innerHTML = `<div class="chat-reply">${r.ok ? esc(body.reply ?? JSON.stringify(body))
      : `<span class="muted">${esc(body.detail || `HTTP ${r.status}`)}</span>`}</div>`;
  });
}

// ---------------------------------------------------------------- public
export async function renderView(root, view, questions, { onShowLayer, prefill } = {}) {
  const mine = questions.filter((q) => q.view === view.id);
  let body = "";
  if (view.id === "history") body = await historyBody();
  if (view.id === "equity") body = await equityBody();
  if (view.id === "ask") body = askBody(prefill);

  root.innerHTML = `
    <div class="view-head">
      <h1>${view.icon} ${esc(view.label)}</h1>
      <p>${esc(view.blurb)}</p>
      ${mine.length ? coverageChips(mine) : ""}
    </div>
    ${todoBlock(view.id)}
    ${body ? `<div style="max-width:980px;margin-bottom:22px">${body}</div>` : ""}
    ${mine.length ? `<h2>Questions this view answers</h2>${questionCards(mine)}` : ""}`;

  root.querySelectorAll("[data-layer]").forEach((b) =>
    b.addEventListener("click", () => onShowLayer?.(b.dataset.layer)));
  wireAsk(root);
}
