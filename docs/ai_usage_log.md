# AI Usage Log

## Tool used

Claude (Sonnet), used interactively through Anthropic's Cowork mode, for the
entire sprint, this was a deliberately AI-collaborative build, done as a
turn-by-turn conversation rather than a single generated submission.

## Workflow

The work was structured as an explicit back-and-forth, not "describe the
brief, get a finished repo back." At each major decision point, I asked
Claude to lay out the tradeoff and I made the call rather than accepting a
default:

1. **Scope triage.** I asked Claude to identify the actual tension in the
   brief (six substantial deliverables against an 8-12h budget) before any
   building started. Claude proposed weighting the institutional
   continuity-gap detector as the primary, more rigorous output over the
   student-side model, arguing this maps directly to HEIAXIS's stated
   thesis (execution failure, not detection failure). I confirmed that
   framing before anything was built.
2. **Model approach.** Claude recommended pure rule-based logic over any ML
   model, citing the brief's own caution against black-box approaches. I
   pushed back with a nuance, a simple explainable model could in principle
   be more precise, and we settled on rules-only for the build, with a
   simple explainable model named explicitly as a "if I had two more weeks"
   item rather than silently dropped.
3. **Schema design.** Claude proposed an initial 5-table relational schema
   with intentional messiness. I asked for additions beyond the brief's
   minimum; Claude proposed several (cross-office case overlap, academic
   calendar context, staff caseload, ID-crosswalk mismatch, case audit log)
   and ranked them by value-per-hour. I approved building the top three and
   documenting the other two as considered-but-cut.
4. **Co-occurrence rule.** Claude flagged, before writing any detection
   code, that student-side flags could require either single-source or
   multi-source decline, and named the tradeoff (recall vs. defensibility).
   I chose to require co-occurrence across at least two sources.
5. **Threshold tuning.** After the first full pipeline run, Claude reported
   an honest concern, 23.6% of students flagged, mostly at "High"
   confidence, and asked whether to tighten the threshold or document the
   tension. I chose to keep the threshold and document the finding, since
   it's a real and useful observation about flag volume vs. institutional
   capacity, not something to hide.

## What Claude did within each of those decisions

Once a decision was made, Claude wrote the synthetic data generator, the
cleaning/validation logic, the feature engineering, both detectors, the
pipeline orchestration, the test suite, the self-consistency check script,
and all documentation (this file included), then ran the code, inspected
actual output (sample rows, data-quality report counts, flag-rate breakdowns
by seeded archetype) before writing up results, rather than describing
expected behavior without checking it against a real run.

## Where I would push further before trusting this for anything real

Everything in this repo reflects my decisions at each checkpoint above, but
I have not independently re-derived every line of the detection logic
(`src/signals.py`, `src/features.py`) by hand; I reviewed the reasoning and
the run output, not every formula in isolation. Before this logic touched
real student data, I would want a closer line-by-line review of the
threshold math, ideally by someone other than the person (or AI) who wrote
it.
