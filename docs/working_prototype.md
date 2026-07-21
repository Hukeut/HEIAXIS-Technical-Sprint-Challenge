# Working Prototype

**High Level Explanation:** This document walks through what the code actually does when you run it, step by step, in plain language. In short: it reads made-up school data, cleans up the messy parts, checks each student against their own earlier behavior instead of comparing them to everyone else, and produces two lists, students who might need someone to check in on them, and cases the school itself seems to have dropped, like a request for help that never got a follow-up. Every single item on both lists comes with a plain-English reason and a confidence level, so nothing shows up as an unexplained flag with no way to check it.

**Low Level Explanation:** `src/pipeline.py` is the single entry point. It loads the seven synthetic CSVs, cleans and validates them (`src/cleaning.py`), computes baseline-relative features per student (`src/features.py`), runs both rule-based detectors (`src/signals.py`), and writes four files to `output/`. Nothing here is a trained model, every output field traces back to specific, checkable field values and thresholds.

## What Happens, Step by Step

Running `python3 src/pipeline.py` does the following, in order:

1. **Load.** `cleaning.load_raw` reads all seven CSVs from `data/` into memory, unchanged.
2. **Clean and validate.** `cleaning.clean_all` fixes or flags every data-quality issue deliberately baked into the synthetic data: attendance values above 1.0 get capped, negative login counts become missing rather than zeroed, office names get canonicalized, duplicate care-interaction rows get dropped, and rows referencing an unknown student get removed. Every single one of these actions is counted, not just performed silently, and printed as a data-quality report before anything else happens.
3. **Engineer features.** `features.build_student_features` computes, for every student, how their attendance, LMS activity, participation, and self-reported belonging in weeks 6-7 compare to their own weeks 1-2, as a relative percentage change. This is computed against each student's own baseline, not a schoolwide average, which is the single most important design decision in the prototype (see `docs/product_interpretation_memo.md`).
4. **Detect signals.** `signals.build_student_flags` and `signals.build_continuity_gaps` run independently over the engineered features and the cleaned care-interaction data, producing the two required outputs.
5. **Roll up office context.** `signals.build_office_caseload_summary` produces a bonus, non-required table showing open cases per staff member per office, useful context for interpreting a continuity gap.
6. **Write and report.** All three tables are written to `output/` as CSVs, the data-quality report is written alongside them as a text file, and a summary of both required outputs prints to the console.

## Output A: Students Flagged for Attention

A row appears in `flagged_students.csv` only when a student's own behavior has declined across at least two of four independent sources (attendance, LMS activity, class participation, self-reported belonging), relative to that same student's own early-term baseline. A single declining source is never enough on its own, this co-occurrence requirement is what stops one noisy data feed from flagging a real person by itself. Each row carries: `confidence`, `n_sources_declined`, `leading_signal` (the single steepest-declining source), `leading_signal_change`, and a `reason` string spelling out every declining source in plain language, for example, "class participation down 38% vs. own early-term baseline; attendance down 26%...".

## Output B: Care-Continuity Gaps

A row appears in `continuity_gaps.csv` when the institution's own handling of a case, not the student's behavior, is the signal: a referral left open past a threshold with no recorded resolution, an outreach attempt that went unanswered with no later contact of any kind, a warm handoff logged with no named owner, or a student with concurrently active, unresolved cases in two or more offices with no sign either office is aware of the other. Each row carries `gap_type`, `confidence`, `weeks_elapsed`, and a `reason` explaining exactly what was left unresolved and for how long.

## The Confidence Scale, Defined

Confidence is not a probability or a model output, it's a direct readout of how much independent evidence supports a given flag, defined explicitly per detector so the word means something concrete rather than a vague sense of certainty:

- **Student flags:** High confidence means three or more sources declined together, or exactly two declined and peer-interaction frequency also corroborates the trend. Medium confidence means exactly two sources declined without that corroboration. There is no Low confidence tier here, because fewer than two declining sources never produces a flag at all.
- **Continuity gaps:** confidence scales with how long a gap has gone unresolved, High at four or more weeks elapsed, Medium at two to three weeks, Low below that, except an unowned handoff, which is always at least Medium regardless of how recently it was logged, since there being no accountable owner is itself the concerning fact, not just its age.

## This Is Not a Diagnostic Tool

Every flag in this prototype is a prompt for a human to look closer, not a conclusion. Nothing here should be read as a clinical or psychological assessment of any student, and nothing here proves that the specific thresholds used (a 15% relative decline, a 3-week-stale referral) are the *right* thresholds for a real institution, those are placeholders that would need to be set collaboratively with an institution's own care staff against their actual tolerance for false positives and actual capacity to respond. See `docs/evaluation_logic.md` for the full reasoning behind this caution, and `docs/product_interpretation_memo.md` for what this prototype does and does not claim to demonstrate.

## Additional Prototype Capabilities Considered for a Larger-Scale System

**Left out mainly for time and scope. Reasonable next additions at scale.**

- **A review interface**, even a simple one, instead of reading ranked CSVs directly. Left out per the brief's own instruction not to spend time on UI, but a real deployment would need some kind of queue a reviewer can act against, not a flat file.
- **Trend visualization per student**, showing the actual week-by-week trajectory behind a flag rather than only the baseline-versus-recent summary numbers. Would make a flag faster to sanity-check at a glance, left out here because the underlying numbers are already fully available in the reason string.
- **Configurable thresholds**, exposing `MIN_RELATIVE_DECLINE` and the continuity-gap week thresholds as settings rather than hardcoded constants, so an institution could tune sensitivity against its own capacity without a code change. Left out here since there's no real institution yet to tune against.

**Explicitly rejected, not just deferred. These would work against what this product is trying to be.**

- **A single blended risk score combining both outputs into one number.** This was considered and rejected outright, not merely postponed. Collapsing a student's own behavioral decline and a separate, institutional case-handling failure into one number would hide which of two completely different problems is actually present, exactly the "black-box conclusion from messy signals" this product exists to avoid. Keeping the two outputs separate is treated as a permanent design decision, not a limitation of this prototype's scope.
- **Automatically suppressing or auto-resolving flags without human review.** Considered and rejected for the same reason a fully automated action stage was rejected in `docs/architecture.md`, removing the human from the loop removes the exact judgment this product depends on, regardless of how much larger the dataset gets.
