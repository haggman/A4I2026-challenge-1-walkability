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
};

let chatMessages = [];
let selectedPersona = "";

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

function askBody(prefill, questions, instance = "ask") {
  const personas = [...new Set(questions.map((q) => q.who))];
  if (!selectedPersona || !personas.includes(selectedPersona)) selectedPersona = personas[0] || "";
  const starters = questions.filter((q) => q.who === selectedPersona);
  if (!chatMessages.length) {
    chatMessages.push({
      role: "assistant",
      text: instance === "map"
        ? "Ask about heat, older residents, households without cars, trees, shade, or water-truck deployment. The demo backend will find locations in the available snapshot and highlight them on the map."
        : "Welcome to the Brooklyn Heat planning assistant. The demo backend can return locations from the available snapshot. The AI planning agent is not connected yet.",
    });
  }
  return `
    <section class="chat-shell" aria-label="Chat with the heat planning assistant">
      <div class="chat-toolbar">
        <label for="chat-persona-${instance}">I am planning as</label>
        <select id="chat-persona-${instance}">${personas.map((who) =>
          `<option value="${esc(who)}" ${who === selectedPersona ? "selected" : ""}>${esc(who)}</option>`).join("")}</select>
        <span class="chat-availability"><span aria-hidden="true"></span>Demo data</span>
      </div>
      <div class="chat-starters" aria-label="Suggested questions">
        ${starters.map((q) => `<button type="button" class="chat-starter" data-prompt="${esc(q.ask)}">${esc(q.ask)}</button>`).join("")}
      </div>
      <div class="chat-transcript" id="chat-transcript-${instance}" role="log" aria-live="polite" aria-label="Conversation"></div>
      <form class="chat-composer" id="ask-form-${instance}">
        <label class="sr-only" for="ask-input-${instance}">Your message</label>
        <textarea id="ask-input-${instance}" rows="2" placeholder="Ask about heat response, interventions, equity, or history…">${esc(prefill || "")}</textarea>
        <button type="submit" class="chat-send" id="ask-send-${instance}">Send</button>
      </form>
      ${instance === "map" ? "" : `<p class="chat-footnote">Responses use deterministic demo logic over the local snapshot; the AI planning agent is not connected.</p>`}
    </div>`;
}

function wireAsk(root, questions, instance = "ask", onMapQuestion = null) {
  const transcript = root.querySelector(`#chat-transcript-${instance}`);
  const input = root.querySelector(`#ask-input-${instance}`);
  const form = root.querySelector(`#ask-form-${instance}`);
  const send = root.querySelector(`#ask-send-${instance}`);
  if (!transcript || !input || !form || !send) return;

  const renderMessages = () => {
    transcript.innerHTML = chatMessages.map((message) => `
      <div class="chat-message ${message.role}${message.error ? " error" : ""}">
        <span class="chat-message-label">${message.role === "user" ? esc(message.persona || "You") : "Assistant"}</span>
        <div>${esc(message.text)}</div>
      </div>`).join("");
    transcript.scrollTop = transcript.scrollHeight;
  };

  root.querySelector(`#chat-persona-${instance}`).addEventListener("change", (event) => {
    selectedPersona = event.target.value;
    root.querySelector(".chat-starters").innerHTML = questions
      .filter((q) => q.who === selectedPersona)
      .map((q) => `<button type="button" class="chat-starter" data-prompt="${esc(q.ask)}">${esc(q.ask)}</button>`).join("");
  });
  root.querySelector(".chat-starters").addEventListener("click", (event) => {
    const button = event.target.closest("[data-prompt]");
    if (!button) return;
    input.value = button.dataset.prompt;
    input.focus();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message || send.disabled) return;

    chatMessages.push({ role: "user", persona: selectedPersona, text: message });
    input.value = "";
    send.disabled = true;
    send.textContent = "Sending…";
    chatMessages.push({ role: "assistant", text: "Searching the backend snapshot…" });
    renderMessages();
    try {
      const response = await api.ask(message, selectedPersona);
      const body = await response.json().catch(() => ({}));
      chatMessages.pop();
      if (!response.ok) {
        chatMessages.push({
          role: "assistant",
          text: body.detail || `The request failed (HTTP ${response.status}).`,
          error: true,
        });
      } else {
        let text = `${body.mode === "demo" ? "DEMO · " : ""}${body.reply || "The backend returned a response."}`;
        if (onMapQuestion) {
          const result = onMapQuestion(body.locations || []);
          if (!result.ok) throw new Error(result.message);
          if (result.count) {
            text += `\n\nMapped ${result.count} returned location${result.count === 1 ? "" : "s"}.`;
          }
        }
        if (body.locations?.length) {
          text += "\n\n" + body.locations.map((location) =>
            `#${location.rank ?? ""} ${location.label}: ${location.lat.toFixed(4)}, ${location.lon.toFixed(4)}`
            + (typeof location.value === "number" ? ` · ${location.value.toFixed(1)} ${location.unit || ""}` : "")
          ).join("\n");
        }
        if (body.caveats?.length) text += `\n\n${body.caveats.join(" ")}`;
        chatMessages.push({ role: "assistant", text });
      }
    } catch (error) {
      chatMessages.pop();
      chatMessages.push({
        role: "assistant",
        text: `Could not reach the portal API: ${error.message}`,
        error: true,
      });
    } finally {
      send.disabled = false;
      send.textContent = "Send";
      input.focus();
      renderMessages();
    }
  });
  renderMessages();
}

export function mountMapChat(root, questions, onMapQuestion) {
  root.innerHTML = askBody("", questions, "map");
  wireAsk(root, questions, "map", onMapQuestion);
}

// ---------------------------------------------------------------- public
export async function renderView(root, view, questions, { onShowLayer, prefill } = {}) {
  const mine = questions.filter((q) => q.view === view.id);
  let body = "";
  if (view.id === "history") body = await historyBody();
  if (view.id === "equity") body = await equityBody();
  if (view.id === "ask") body = askBody(prefill, questions, "ask");

  root.classList.toggle("ask-layout", view.id === "ask");
  if (view.id === "ask") {
    root.innerHTML = `
      <div class="ask-context">
        <div class="view-head">
          <h1>${view.icon} ${esc(view.label)}</h1>
          <p>${esc(view.blurb)}</p>
          ${mine.length ? coverageChips(mine) : ""}
        </div>
        ${mine.length ? `<h2>Questions for the planning agent</h2>${questionCards(mine)}` : ""}
      </div>
      <aside class="ask-panel" aria-label="Planning assistant chat">${body}</aside>`;
    wireAsk(root, questions);
    return;
  }

  root.innerHTML = `
    <div class="view-head">
      <h1>${view.icon} ${esc(view.label)}</h1>
      <p>${esc(view.blurb)}</p>
      ${mine.length ? coverageChips(mine) : ""}
    </div>
    ${view.id !== "ask" ? todoBlock(view.id) : ""}
    ${body ? `<div style="max-width:980px;margin-bottom:22px">${body}</div>` : ""}
    ${mine.length && view.id !== "ask" ? `<h2>Questions this view answers</h2>${questionCards(mine)}` : ""}`;

  root.querySelectorAll("[data-layer]").forEach((b) =>
    b.addEventListener("click", () => onShowLayer?.(b.dataset.layer)));
}
