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

**Low Level Explanation:** Each request re-reads the relevant CSV directly from `output/` using pandas. This means running `python src/pipeline.py` again, to regenerate the dataset or pick up a logic change, is still required before the API reflects new results; the API does not re-run the pipeline on its own. If `output/` doesn't exist yet (the pipeline has never been run), affected endpoints return a `503` with a clear message rather than a confusing stack trace.

## Response Format and Presentation

**Options considered:**
- A. Bare JSON arrays or objects mirroring the CSV columns exactly, nothing else in the response.
- B. Self-explanatory JSON envelopes on every endpoint, including the front page: every response includes what the endpoint is, what each field means, and the confidence scale or gap-type definitions, alongside the actual data.
- C. One plain HTML front page at `GET /`, a big title and the same terminal summary `pipeline.py` already prints, everything else stays JSON with self-explanatory envelopes.

**Chosen Answer:** Option A was the original approach, and it works, but it quietly reintroduces the exact problem this whole project is built to avoid: a caller sees a `confidence: "Medium"` or a `gap_type: "unowned_handoff"` with no explanation attached unless they already have `docs/data_dictionary.md` open next to them. Option B fixed that, but tried to solve it everywhere including the front page, and a JSON directory-of-endpoints as the very first thing someone sees is exactly the kind of "too complicated" first impression this was supposed to avoid, useful to a program, not to a person glancing at a browser. C splits the difference cleanly: the one page a person actually looks at directly is plain and immediate, the numbers, nothing else to parse, and every endpoint meant for programmatic use still explains itself in full.

**Low Level Explanation:** `GET /` returns `text/html`: a large "HEIAXIS" heading followed by a `<pre>` block containing the same report `pipeline.py` prints to the terminal (data-quality report, both outputs' previews, office caseload), rebuilt from whatever is currently in `output/` rather than by re-running the pipeline. Every other endpoint returns `application/json`. List endpoints (`/students/flagged`, `/continuity-gaps`, `/office-caseload`) return an envelope with `description`, `fields` (a plain-English definition of every column), `count`, `filters_applied`, and `results`. Where relevant, the envelope also includes `confidence_scale` and, for continuity gaps, `gap_types`. The single-student, summary, and data-quality-report endpoints follow the same explanatory pattern at a smaller scale.

## Endpoints Reference

| Method & Path | Description | Query Parameters |
|---|---|---|
| `GET /` | HTML front page: a big "HEIAXIS" title plus the same plain-text summary `pipeline.py` prints to the terminal. | none |
| `GET /health` | Basic status check, confirms the API is running and whether `output/` currently exists. | none |
| `GET /summary` | The headline numbers as JSON: flag counts, confidence breakdown, gap counts by type, busiest office, each with a plain-English explanation. | none |
| `GET /students/flagged` | Flagged students, wrapped with field definitions and the confidence scale. | `confidence` (optional, one of `High`/`Medium`/`Low`) |
| `GET /students/flagged/<student_id>` | A single student's flag detail, same field definitions and confidence scale included. Returns `404` if that student isn't currently flagged. | none |
| `GET /continuity-gaps` | Continuity gaps, wrapped with field definitions, the confidence scale, and gap-type definitions. | `gap_type` (optional, one of the four known gap types) |
| `GET /office-caseload` | The bonus office rollup, wrapped with field definitions. | none |
| `GET /data-quality-report` | The cleaning report from the last `pipeline.py` run, with a description of what it represents. | none |

Every list endpoint's `results` array is empty, not an error, when there's simply nothing to report, an empty `continuity_gaps.csv` is a valid, meaningful result (no gaps found), not a failure state. `count` on the envelope reflects the length of `results` after any filter was applied.

## What This Doesn't Solve

No authentication or authorization of any kind, anyone who can reach this API can see every flagged student and every gap. That's acceptable for a local prototype running against synthetic data, and not acceptable for anything touching real student data, `docs/architecture.md`'s Privacy and Access Boundaries stage covers what would actually need to exist first: role-scoped access based on legitimate educational interest, not an open API surface. No pagination, the current dataset (700 students) is small enough that returning full lists in one response is reasonable, but this would need to change well before real institutional scale. No deployment story, this is meant to be run locally (`python src/api.py`) alongside the rest of the prototype, not exposed on a network, and definitely not deployed as-is against real data.
