# Testing Strategy

**High Level Explanation:** This document explains why the tests exist and what they're actually protecting, not just that tests exist. The real risk here isn't the program crashing, crashes are obvious and get fixed immediately. The real risk is the program running fine while quietly giving a wrong answer: flagging the wrong student, missing a real gap, or showing an unfair confidence level, none of which would show up as an error message. Testing is how we catch that kind of silent, convincing-looking mistake before a human reviewer ever sees it and trusts it.

**Low Level Explanation:** Tests are split into two tiers. Tier 1 is granular and checks that individual pieces of logic (cleaning, feature math, the detection rules themselves) do exactly what they're supposed to, including at their exact boundary conditions. Tier 2 is system-level and checks that the whole pipeline still behaves sensibly end to end, including a seed-based regression check so a silent change in behavior gets caught even if every individual piece still passes its own test. Both tiers were conceptualized here, in writing, before being implemented, in the same spirit as test-driven development: decide what "correct" means first, then write code that has to satisfy it.

## This Already Happened, Not Just In Theory

Writing the Tier 2 edge-case tests (an institution with zero care interactions
logged, a student missing from a table entirely) surfaced two real crashes in
`src/features.py` and `src/signals.py`: both silently relied on a pandas
behavior where an empty input produces a DataFrame missing its `student_id`
column entirely, which then crashed the merge and groupby steps downstream.
Neither bug showed up on the bundled 700-student dataset, because that
dataset never happens to be empty. Both are now fixed with an explicit
empty-input guard, and both fixes are covered by a test that fails if the
bug ever comes back. This is the argument for this whole document made
concrete: the bundled dataset passing every check was never proof the code
was correct, only that it hadn't yet been asked a question it couldn't answer.

## Why This Matters for This Specific Product

Untested code is a risk in any project, but the shape of the risk here is specific. This tool's entire value proposition is that its flags can be trusted enough to act on, `docs/evaluation_logic.md` spends a whole document on what a wrong flag costs a student or a staff member. A bug in the co-occurrence rule that lets a single noisy source flag a student defeats the exact design decision that document defends. A bug in the stale-referral threshold that fires one week early or late quietly changes what "stale" means without anyone deciding it should. Tests are what keep the code honest to the decisions already made and documented elsewhere in this repository, rather than letting the code drift away from them unnoticed.

## Tier 1: The Test Suite (`tests/test_pipeline.py`)

Granular, one behavior per test, designed to fail loudly and specifically if a single piece of logic breaks.

**Data integrity**
- No duplicate primary keys survive cleaning.
- Every foreign key (`student_id` in any table) resolves to a real row in `students.csv`.
- Numeric fields stay in valid ranges after cleaning (attendance between 0 and 1, no negative counts).
- Office names are fully canonicalized, no raw casing variants leak through.

**Cleaning logic**
- An attendance value above 1.0 actually gets capped, not left as-is or dropped.
- A negative login count becomes missing, not silently zeroed, zeroing it would claim "no logins" when the truth is "the ETL was wrong."
- Duplicate interaction rows are actually removed, not just counted.
- The data-quality report's counts match what was actually changed, the report itself is tested, not just trusted.

**Feature engineering**
- The baseline-versus-recent relative change calculation is correct against a known, hand-computed input.
- A student with insufficient survey responses is marked `insufficient_data`, never silently imputed a value.
- A student with a zero baseline doesn't crash the pipeline or produce a nonsense relative-change number.

**Signal detection, the most important tier**
- Exactly one declining source never produces a student flag, the co-occurrence rule is tested at its boundary, not just its obvious middle.
- Exactly two declining sources produces a flag; confidence is Medium unless peer interaction also corroborates, in which case it's High.
- Three or more declining sources always produces a High confidence flag.
- A continuity gap fires exactly at its stated week threshold, not one week early or late, boundary conditions are where off-by-one bugs actually live.
- An unowned handoff always flags, regardless of how recently it was logged.
- The multi-office signal requires genuinely distinct offices, two touches at the same office never trigger it.

**Output contract**
- Every flagged row, on both outputs, has a non-empty reason, a leading signal, and a confidence value drawn only from the allowed set.

## Tier 2: General / System Tests (`tests/test_system.py`)

Checks that the whole pipeline still makes sense, not just that its parts do.

- **End-to-end smoke run.** Generate data, run the full pipeline, confirm it exits cleanly and produces non-empty, correctly-shaped output files. Catches integration breaks that unit tests, by design, can't see.
- **Seed-based regression check.** With `random.seed(42)` fixed, the pipeline should produce the same flag counts every run. If that number ever silently drifts, something in the logic changed and a human needs to look at why, this is a tripwire, not a correctness proof.
- **Edge cases a normal run never exercises.** An empty dataset shouldn't crash the pipeline. A student missing from one table entirely (say, no belonging-survey rows at all) should be handled gracefully, not crash or silently vanish from the output. A dataset where every student is identical should produce zero flags, not an error.

## What Would Be Needed to Scale This to Real Institutional Demand

- **Continuous integration**, running the full suite automatically on every change, rather than manually as done here. At this sprint's scale, remembering to run `python3 tests/test_pipeline.py` is fine. At production scale, a missed manual run is how a regression ships.
- **Property-based or randomized-seed testing**, instead of one fixed seed. A fixed seed proves the code is deterministic; it does not prove the code is correct across the wide space of realistic data it will eventually see. Generating many random synthetic datasets and checking invariants (never fewer than 2 sources on a flag, confidence always from the allowed set) would catch bugs a single fixed run can't.
- **A real regression suite built from actual pilot outcomes**, once available, replacing the current self-consistency check (which is explicitly circular, see `docs/evaluation_logic.md`) with something that checks behavior against real, human-reviewed cases instead of against the same synthetic archetypes the detectors were designed around.
- **Load and performance testing** once data volume grows toward real institutional scale (tens of thousands of students across many terms), this prototype has never been tested past 700 students and there's no evidence yet that the current per-student-loop approach in `signals.py` would perform acceptably at 100x that size.
- **Mutation testing**, deliberately introducing small bugs into the detection logic and confirming the test suite actually catches them. A test suite that passes isn't the same thing as a test suite that would catch a real regression, this is how you'd find out which one you actually have.
