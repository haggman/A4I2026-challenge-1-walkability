---
name: pitch-story
description: Produces the submission package for A4I Challenge 1, a short pitch deck, a rehearsed demo script, and a screen-recorded pitch video, mapped to the judging rubric (Impact 30, Technical 30, Rigor 25, Craft 15, +10 range). Use when outlining slides, scripting or timing the demo, writing the limitations or decisions slide, or checking that every judge question is answered in the deck or video.
---

# Pitch & story: judges score the submission, not a conversation

Judges review **repo + Skills project link + deck + pitch video** after the event, with no Q&A.
Anything not in the deck or the video counts as unanswered. Submission portal:
https://portal.angelhack.com/a4i-console (confirm deadline with your facilitator).

## Deck (front-loaded; assume you're cut off after slide 4)

1. **The decision**: city, track, scenario in one sentence, and who's asking. ("Dana, city
   manager's office, 3:40pm Tuesday, 102 °F Thursday, council at 9.")
2. **The answer**: the Placement Recommendation, as a map plus 3 sites, each with offset,
   top driver in °F, and who lives there.
3. **How it works**: architecture (one diagram): ADK + Gemini, BQML `ML.EXPLAIN_PREDICT` called
   by a tool we built, MCP Toolbox, BigQuery, deployed on Cloud Run / Agent Runtime.
   Say "offset, not temperature" here.
4. **Why you can trust it**: spatial-holdout MAE vs. predict-zero baseline, the leakage
   we avoided, validation passed (n of n checks).
5. **Equity audit**: the table and one sentence with ratios.
6. **Limitations**: one line each (see `/placement-recommendation`).
7. **Decisions & next steps**: interface choice + why, data added + license, what we'd do
   with another week.

## Demo script (≤ 2 minutes, rehearsed twice, timed out loud)

1. Ask the track's central question → ranked sites appear (point to an **unmeasured** site:
   "nobody drove here, but the model predicts it").
2. "Why is site 1 worse than two blocks north?" → drivers in °F.
3. "Draft the council proposal" → one-page artifact.
4. "Did we reach those who need it most?" → audit numbers.
5. (If time) A refusal: "How much cooler after planting trees?" → honest limit.

Record the video as a screen share with one narrator. Run the deployed version, not localhost.
Keep a backup take.

## Rubric → where it's answered

| Dimension (weight) | Judges ask | Our evidence (slide / video timestamp) |
|---|---|---|
| Impact & insight (30) | Would the user act on this? Specific enough? | slide 2, demo step 1 |
| Technical execution (30) | Works? Stack genuinely used? | slide 3, live deployed demo, repo |
| Rigor & judgment (25) | Defensible decisions, validation, bias handling, limits | slides 4–6, DECISIONS.md |
| Craft & communication (15) | Pitch lands, demo works, interface justified | whole video, slide 7 |
| Bonus range (+10) | Breadth that serves the solution | extra data, custom UI, Gemini Enterprise |

Fill the right-hand column before recording. Any empty cell is lost points.

## Credits line (always)

"Data: NOAA & CAPA Strategies Heat Watch (CC0), NOAA GHCN-Daily, US Census ACS. Thanks to the
volunteers who drove the routes."
