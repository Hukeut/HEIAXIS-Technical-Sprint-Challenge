# API

**High Level Explanation:** Right now, the only way to see this prototype's results is to open a CSV file or read a terminal printout after running a script. This document describes a small web API that sits on top of the existing pipeline and lets that same information be reached over the web instead, so it could actually be shown in a dashboard, queried by another system, or filtered without opening a spreadsheet. It doesn't change how any student is scored or flagged, it just changes how the results already being produced can be reached.

**Low Level Explanation:** A Flask application, `src/api.py`, that reads the CSV files already written to `output/` by `src/pipeline.py` and serves them as JSON over a handful of read-only endpoints. It computes nothing new, the detection logic in `src/signals.py` is untouched, this is purely a presentation layer in front of output that already exists. No authentication, pagination, or deployment concerns are solved here, those are named explicitly below as things intentionally left out of this prototype's scope.

## Framework Choice

**Options considered:**
- A. Python's built-in `http.server`, zero new dependencies at all.
- B. FastAPI, with automatic interactive documentation (a browsable `/docs` page) generated for free.
- C. Flask, a small, widely known framework with minimal boilerplate for a handful of read-only routes.

**Chosen Answer:** Option A stays fully true to the project's "only pandas and numpy" dependency footprint, but it means hand-writing routing and JSON serialization for no real benefit, more code for less capability. Option B's automatic docs page is genuinely useful, but it's more machinery than six read-only endpoints reading from CSVs actually need, and it pulls in a heavier dependency set (`fastapi` plus an ASGI server) than this scope calls for. C adds exactly one new dependency, is well understood by almost any Python developer picking this project up later, and is a proportionate amount of new surface area for what this API actually needs to do.

**Low Level Explanation:** `flask` is added to `requirements.txt` as the project's third dependency, alongside `pandas` and `numpy`. The app itself stays a single file, `src/api.py`, with no application factory pattern, blueprints, or database layer, none of which this scope needs.

## What the API Serves, and What It Doesn't

**Options considered:**
- A. Trigger the full pipeline on every request, always returning freshly computed results.
- B. Keep results in memory inside the API process, recomputed only when the process restarts.
- C. Read whatever is currently sitting in `output/`, exactly as written by the last `pipeline.py` run, on every request.

**Chosen Answer:** Option A would make the API slow (a full run regenerates and reprocesses 700 students' worth of data on every single request) and conflates two genuinely separate concerns, computing results and serving them, that this project has kept deliberately separate since `pipeline.py` was first written. Option B avoids the slowness but introduces a staleness problem that's invisible to whoever's calling the API, results silently drift from what `output/` actually contains, with no way to tell from the API alone. C keeps the API a thin, honest read layer: it always reflects the same files a human would see if they opened `output/` themselves, no more and no less.

**Low Level Explanation:** Each request re-reads the relevant CSV directly from `output/` using pandas. This means running `python3 src/pipeline.py` again, to regenerate the dataset or pick up a logic change, is still required before the API reflects new results; the API does not re-run the pipeline on its own. If `output/` doesn't exist yet (the pipeline has never been run), affected endpoints return a `503` with a clear message rather than a confusing stack trace.

## Response Format and Presentation

**Options considered:**
- A. JSON endpoints plus one or two server-rendered HTML pages, so results are viewable as formatted tables directly in a browser.
- B. Bare JSON arrays or objects mirroring the CSV columns exactly, nothing else in the response.
- C. Self-explanatory JSON envelopes: every response includes what the endpoint is, what each field means, and (where relevant) the confidence scale or gap-type definitions, alongside the actual data.

**Chosen Answer:** Option A would make this genuinely more useful to look at directly, but it starts drifting toward exactly the "please don't spend time making the UI beautiful" territory the original brief explicitly de-scoped, and it isn't needed for the API's actual purpose, being a layer other systems or a future dashboard can consume. Option B was the original approach, and it works, but it quietly reintroduces the exact problem this whole project is built to avoid: a caller sees a `confidence: "Medium"` or a `gap_type: "unowned_handoff"` with no explanation attached unless they already have `docs/data_dictionary.md` or `docs/working_prototype.md` open next to them. C carries the same explainability principle behind every CSV `reason` column into the API itself, a response should never require a second document to understand.

**Low Level Explanation:** Every endpoint returns `application/json`. List endpoints (`/students/flagged`, `/continuity-gaps`, `/office-caseload`) return an envelope with `description` (what this endpoint is), `fields` (a plain-English definition of every column in each row), `count`, `filters_applied`, and `results` (the actual rows, unchanged from the CSV's field names). Where relevant, the envelope also includes `confidence_scale` and, for continuity gaps, `gap_types`, so the meaning of every value in `results` is defined in the same response, not just its name. The single-student endpoint and the data-quality-report endpoint follow the same pattern at a smaller scale. `GET /` returns a directory of every endpoint with a one-line description, so visiting the bare root URL explains the API instead of returning an unhelpful 404.

## Endpoints Reference

| Method & Path | Description | Query Parameters |
|---|---|---|
| `GET /` | Self-documenting directory of every endpoint below. | none |
| `GET /health` | Basic status check, confirms the API is running and whether `output/` currently exists. | none |
| `GET /students/flagged` | Flagged students, wrapped with field definitions and the confidence scale. | `confidence` (optional, one of `High`/`Medium`/`Low`) |
| `GET /students/flagged/<student_id>` | A single student's flag detail, same field definitions and confidence scale included. Returns `404` if that student isn't currently flagged. | none |
| `GET /continuity-gaps` | Continuity gaps, wrapped with field definitions, the confidence scale, and gap-type definitions. | `gap_type` (optional, one of the four known gap types) |
| `GET /office-caseload` | The bonus office rollup, wrapped with field definitions. | none |
| `GET /data-quality-report` | The cleaning report from the last `pipeline.py` run, with a description of what it represents. | none |

Every list endpoint's `results` array is empty, not an error, when there's simply nothing to report, an empty `continuity_gaps.csv` is a valid, meaningful result (no gaps found), not a failure state. `count` on the envelope reflects the length of `results` after any filter was applied.

## What This Doesn't Solve

No authentication or authorization of any kind, anyone who can reach this API can see every flagged student and every gap. That's acceptable for a local prototype running against synthetic data, and not acceptable for anything touching real student data, `docs/architecture.md`'s Privacy and Access Boundaries stage covers what would actually need to exist first: role-scoped access based on legitimate educational interest, not an open API surface. No pagination, the current dataset (700 students) is small enough that returning full lists in one response is reasonable, but this would need to change well before real institutional scale. No deployment story, this is meant to be run locally (`python3 src/api.py`) alongside the rest of the prototype, not exposed on a network, and definitely not deployed as-is against real data.
