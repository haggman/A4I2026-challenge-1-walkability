---
name: frontend-ui
description: Builds the planner-facing interface for the heat agent using React, Next.js, FastAPI, and the Google Maps JS API (@vis.gl/react-google-maps), or choosing between adk web, Gemini Enterprise, and a custom web UI (map + chat) on Cloud Run. It works mock-first against the Placement Recommendation contract. Use when choosing or justifying the interface, building the React/Next.js map and chat UI, wiring the FastAPI backend to the deployed ADK agent API, integrating Google Maps API, or preparing the demo machine.
---

# Front end: the face a council member can read

## Choose deliberately (and write the one-sentence why in DECISIONS.md)

| Option | When it's the right call | Defensible sentence |
|---|---|---|
| `adk web` | You spent the time on rigor instead | "We invested in the model and the audit; the interface is the developer console." |
| **Gemini Enterprise** | User is city staff (internal) and the agent is on Agent Runtime | "Our user is a city employee, not a resident, so we chose an internal-facing interface." |
| **Custom UI (Next.js + React + FastAPI + Google Maps)** | You want the map moment, and have 2 people for ~2 hours | "A council member reads a map, not a chat log." |

Everyone starts on `adk web`. That's not a choice. The choice is whether you finish there.

## Custom UI blueprint (Next.js + React + FastAPI + Google Maps API)

- **Single page layout**: left = conversational chat panel; right = interactive Google Map with
  ranked sites (numbered pins, colour = predicted offset), click a pin → card with drivers
  (°F bars), demographics, one-line why. Optional: a heat layer of `grid_predictions` with
  "unmeasured" cells hatched/outlined, which shows the model filling gaps.
- **Stack (React + Next.js + FastAPI + Google Maps):**
  - **Frontend (Next.js + React):** Next.js (App Router, React 18+, TypeScript, Tailwind CSS)
    using `@vis.gl/react-google-maps` (`<APIProvider>`, `<Map>`, `<AdvancedMarker>`, `<InfoWindow>`).
  - **Backend API (FastAPI):** A lightweight FastAPI service (`frontend/api/main.py`) on Cloud Run
    that proxies requests to the ADK agent (keeping Cloud Run ID-token auth server-side so no GCP
    credentials reach the browser) and serves typed Pydantic endpoints (`/api/chat`,
    `/api/recommendations`, `/api/grid`, `/api/config`). Next.js connects via App Router Route
    Handlers (`app/api/.../route.ts`) or `next.config.mjs` API rewrites to FastAPI.
  - **Map (Google Maps JS API):** Restricted by HTTP referrer and scoped to Maps JavaScript API,
    stored in Secret Manager (`maps-api-key`) and injected at Cloud Run runtime (`MAPS_API_KEY` /
    `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`). **Don't use OpenStreetMap tiles/data**: ODbL share-alike
    conflicts with the challenge's data rules.

### Google Maps API integration (`@vis.gl/react-google-maps`)

1. **Provider & Map setup:** Wrap the map panel in `<APIProvider apiKey={mapsApiKey}>` and render
   `<Map defaultCenter={cityCenter} defaultZoom={12} mapId="heat-planner-map">`.
2. **Ranked site markers:** Map over `recommendation.sites` and render `<AdvancedMarker>` for each
   site `(latitude, longitude)` with a numbered badge styled by `predicted_offset_f` (`+°F` vs.
   city campaign mean). Clicking a marker sets `selectedSite` state to open an `<InfoWindow>` and
   highlight the site's driver breakdown card (`ML.EXPLAIN_PREDICT` attributions in `°F`, ACS
   demographics, and one-line rationale).
3. **Heat offset grid layer:** Load precomputed `grid_predictions` from FastAPI (`GET /api/grid`)
   and render via `google.maps.visualization.HeatmapLayer` or Maps Data layer polygons colored by
   predicted offset, toggling hatched borders on cells with no raw Heat Watch observations.

### FastAPI ↔ ADK Agent integration

- **Session & Run proxy:** FastAPI exposes `POST /api/chat` and proxies to the deployed ADK agent:
  1. `POST /apps/heat_planner/users/{uid}/sessions/{sid}` to ensure a session exists.
  2. `POST /run` (or `/run_sse` for streaming) with `new_message`.
  3. Inspect events for `functionResponse` parts named `rank_candidate_sites` or
     `assemble_placement_recommendation` to extract structured `PlacementRecommendation` JSON
     and return `{ reply, recommendation, sites }` to the React UI.
- **Mock first (`USE_MOCK=true`):** FastAPI and Next.js serve `docs/contracts/sample.json` behind
  the exact same `/api/chat` and `/api/recommendations` contract until the agent is live, then
  flip `USE_MOCK=false`. You're never blocked on the agent lane.

## Demo hardening

- Test on the presenting laptop, in the browser you'll present from, on venue Wi-Fi.
- Pre-warm: open the app and run one question 2 minutes before recording.
- Large fonts, light theme for projectors, no dev tools visible.
- A fallback screenshot of the map with sites, and a pre-recorded clip.
