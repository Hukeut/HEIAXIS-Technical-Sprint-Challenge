# Working Prototype

**High Level Explanation:** This is a small computer program, not an app with buttons to click. It reads the made-up school data described in the data dictionary, checks it for obvious mistakes and fixes what it safely can, then looks for patterns across the different files. At the end, it produces two lists: one of students who might be worth a staff member's attention, and one of cases where the school itself seems to have dropped the ball, like a request that was opened and never followed up on. Every single item on both lists comes with a plain-English reason attached, so nobody has to just trust the program, they can check the reason for themselves in a few seconds. Think of it less like a doctor giving a diagnosis and more like a smoke detector that also tells you which room it went off in and why, so a person can go check.

**Low Level Explanation:** The prototype is a Python pipeline with four stages: load, clean and validate, engineer features, and detect signals, each in its own file so the logic stays easy to follow and test in isolation. Cleaning fixes or flags bad values (out-of-range attendance, negative login counts), normalizes inconsistent office-name spellings, and removes duplicate records, logging every change to a data-quality report rather than silently altering anything. Feature engineering computes each student's own change over time relative to their own early-term baseline, not compared to other students. Signal detection is two entirely separate, rule-based (not machine-learned) detectors: one flags a student only when decline shows up across at least two independent sources at once, the other flags institutional gaps directly from timestamps and null fields, a referral open too long, an outreach nobody followed up on, a handoff with no name attached. Every output row carries a reason, a leading signal, and a confidence level. No part of this makes a diagnostic or predictive claim; it surfaces patterns for a human to review, nothing more. (Full reasoning behind these choices is in `docs/product_interpretation_memo.md`.)

## What the Prototype Actually Does, Step by Step

1. **Load** (`src/cleaning.py: load_raw`). Reads all seven synthetic CSV files into memory.
2. **Clean and validate** (`src/cleaning.py: clean_all`). Caps out-of-range attendance values, treats negative login counts as missing rather than guessing at a fix, normalizes inconsistent office-name spellings to one canonical set, removes duplicate interaction rows, and checks that every record actually points to a real student. Every fix is counted and written to a data-quality report, nothing is changed silently.
3. **Engineer features** (`src/features.py`). For each student, compares their weeks 1-2 average against their weeks 6-7 average, per source (attendance, LMS activity, participation, self-reported belonging), producing a relative change number rather than a raw score. Missing data (like an unanswered survey week) is never guessed at or filled in; if there isn't enough of it, the feature is marked as insufficient rather than estimated.
4. **Detect signals** (`src/signals.py`). Two independent detectors:
   - **Student attention flag:** only fires when at least two of the four sources show a meaningful decline (15% or more) at the same time, so one noisy data feed can't flag a person on its own.
   - **Continuity gap flag:** fires directly off timestamps and blank fields, a referral still open several weeks after it was logged, an outreach that went unanswered with nothing after it, a handoff with nobody's name on it, or a student with unresolved cases open in two or more offices at once with no sign either office knows about the other.
5. **Produce ranked outputs** (`src/pipeline.py`). Writes both lists to CSV, sorted so the most confident, most concerning items appear first, plus a small bonus table showing case load per office (not one of the two required outputs, but useful context for interpreting the gaps).

## Output A: Students or Cases That May Require Attention

Each row includes: which student, the confidence level, how many sources showed decline, the single leading signal, exactly how much that signal moved, and a plain-English reason listing every source involved. A student is never flagged from a single noisy number alone.

## Output B: Continuity Gaps in the Care System

Each row includes: what kind of gap it is (stale referral, unanswered outreach, unowned handoff, or uncoordinated multi-office case), which student and office, how many weeks the issue has been sitting, a confidence level, and a plain-English reason.

## The Confidence Scale

Three tiers, used consistently across both outputs, meant to tell a reviewer how much weight to put on a flag before they've read anything else:

- **High.** Multiple independent sources agree, or a gap has been sitting untouched for a long time. Worth prioritizing.
- **Medium.** The minimum bar to be flagged at all was met, but only just. Worth a look, not necessarily worth jumping the queue for.
- **Low.** Used only for continuity gaps that are real but recent, an early warning rather than something already stale.

## What This Output Is Not

None of this is a diagnosis, a prediction, or a certainty. A flag means "this pattern matched a rule we can show you," never "this student is at risk" or "this office is failing." The reason field exists specifically so nobody has to take the flag on faith, and the confidence level exists so a reviewer knows how much scrutiny to apply before acting on it.

## Additional Prototype Capabilities Considered for a Larger-Scale System

Left out of this version for a mix of time budget and genuine uncertainty about whether they'd actually help. Split the same way as the data dictionary, some are natural next steps, others need real thought before they belong in the product.

**Left out mainly for time. Reasonable next steps.**

- **A feedback loop.** Nothing here learns from a reviewer marking a flag as dismissed or acted on. At scale, dismiss-with-reason data is exactly what should drive threshold retuning over time, but it requires a review interface this prototype doesn't have.
- **Calendar-aware suppression.** `academic_calendar.csv` exists and is available as context, but no flag is currently softened or delayed because it lands during a known high-load week like midterms. Wiring that in is a small, well-scoped next step.
- **A simple, explainable statistical model** (for example, logistic regression with visible coefficients) run alongside the rule-based student detector, purely to check whether the added complexity earns its keep, not to replace the transparent rules outright.
- **Streaming or near-real-time detection**, instead of the current batch run over a full 7-week snapshot. A real system would need to flag a stalling case within days, not at the end of a term.

**Left out because the value is genuinely unclear, not just because of time.**

- **A single blended "risk score"** combining the student and institutional signals into one number. Considered and deliberately rejected, not just deferred, because collapsing two very different kinds of signal into one score is exactly the false-certainty problem this design is trying to avoid. This one likely shouldn't be added even at scale.
- **A borderline "watch" tier below Medium confidence**, for cases that almost met the bar. Tempting for completeness, but untested here: it might catch real near-misses, or it might just add noise a reviewer has to sift through. Would need real usage data to know which.
- **Automatic escalation** (the system reassigning or re-routing a stalled case on its own, rather than only flagging it for a human). Interesting long-term, but directly in tension with the "human review" step the architecture note treats as non-negotiable, so this would need careful design, not just more engineering time.
