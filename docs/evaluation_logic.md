# Evaluation Logic

**High Level Explanation:** This document answers one honest question: how would we actually know if this is any good, and how do we make sure we're not fooling ourselves, or anyone reading this, into thinking it's more proven than it actually is? Building something that runs is the easy part, this prototype already does that. It has only ever been tested against data we made up ourselves, so right now the honest answer to "does it work" is: not yet proven, only plausible. This document is the real plan for finding out, not a claim that it already works.

**Low Level Explanation:** Six separate concerns, each handled on its own rather than blended together: how usefulness would actually get tested against real data, since no trustworthy label exists yet to score accuracy against; how to avoid mistaking a correlation the detectors surface for an actual cause; how to guard against the specific self-deception risk of having generated both the synthetic data and the detection logic that reads it; what a wrong flag actually costs, for both a student and a staff member, in either direction; what would be measured on an ongoing basis to know if the tool is helping; and what would need to be true of a real institution before any of this should be trusted with real students. Together these turn the brief's caution against overclaiming into something concrete enough to actually check, rather than a principle stated in the abstract.

## How I would test whether the signal is useful

Not with accuracy metrics against a proxy label, there isn't a trustworthy one
in this prototype, and manufacturing one would be circular. Instead, a staged
real-world validation:

1. **Shadow mode.** Run the detectors against real (properly authorized)
   institutional data for a full term without surfacing anything to staff.
   Have reviewers who know the actual context independently assess a sample of
   flagged and unflagged cases and judge whether the flagged group looks
   meaningfully different to someone with real information the model doesn't have.
2. **Human-in-the-loop pilot.** Surface flags to a small group of staff who
   already log outcomes, and track whether the flag *changed what they did*
   (see Metrics below). Usefulness here is behavioral, not statistical.
3. **Retrospective check.** Once outcomes are available weeks or months later,
   check whether flagged cases were disproportionately represented among
   students who needed higher-intensity intervention, or among cases staff
   later agree should have been caught sooner. Noisy and after-the-fact, but
   it's real signal instead of self-generated signal.

## Avoiding correlation/causation confusion

The detectors never claim causation, and the output text is written to make
that hard to misread: "attendance down 26% vs. own early-term baseline," not
"this student is disengaging because of X." A stale referral doesn't mean an
office is failing a student for a reason related to the student, it might
mean the office is understaffed, the referral was miscategorized, or the
student resolved things another way and nobody updated the record. This is
exactly why `office_caseload_summary.csv` sits alongside the continuity-gap
flags: a reviewer sees "this office is running 9.5 open cases per staff
member" next to a stale-case flag, so the obvious alternate explanation
(capacity, not neglect) is visible rather than implied by omission.

## Avoiding fooling myself, given I generated the data and wrote the detectors

Three things, in decreasing order of how much I trust them:

1. The archetype-generation logic (`generate_data.py`) was written before the
   detection thresholds (`signals.py`), and includes a `noisy_false_flag_bait`
   archetype specifically designed to break a naive absolute-threshold
   approach. I had to design against a failure mode, not just toward a
   success case.
2. `src/self_consistency_check.py` is explicitly labeled as circular and is
   never presented as validation anywhere in this submission, it checks
   whether my code does what I intended, not whether that intention is correct
   for the real world.
3. The most honest thing I can say: I do not know whether the 15%-decline /
   3-week-stale thresholds are the *right* thresholds. "Right" can only be
   defined by a real institution's tolerance for false positives given its
   actual staff capacity, and that number doesn't exist yet. I'm treating this
   as an open question for the walkthrough, not a solved one.

## What false positives and false negatives mean here, for both sides

**Student-attention flag.**
A false positive means a staff member spends time reaching out to a student
who didn't need it, mildly costly in staff time, but also a real cost to the
student: an intrusive check-in can feel like surveillance, especially for
students who are simply quiet by nature rather than declining (the group this
design is specifically meant to protect via relative-to-self scoring). A false
negative means a genuinely declining student isn't flagged, a missed early
opportunity, though survivable if the surrounding process is otherwise healthy
(i.e., a human eventually notices some other way). It stops being survivable
if the institution comes to rely on the flag as the *only* mechanism, which is
itself a risk worth naming.

**Continuity-gap flag.**
A false positive puts an implicit "you dropped this" signal in front of an
office for a case that was actually fine, closed elsewhere, resolved
informally, or miscategorized. The cost here is trust: in the tool, and possibly
in staff feeling monitored by a system tracking their case handling. A false
negative means a genuinely stalled case stays invisible, the exact failure
mode HEIAXIS states it exists to prevent, and therefore the more expensive
failure to accept in this product. That asymmetry is part of why the
continuity-gap thresholds (2-3 weeks) are tighter and more sensitive than I
might choose for a lower-stakes use case.

## Metrics I would track

- **Flag-to-action rate:** % of flags resulting in a recorded staff action
  within N days. Most directly tests HEIAXIS's own thesis, does a flag
  actually change what happens next.
- **Time-to-first-touch after a flag**, compared to time-to-first-touch for
  cases that reached the same status without a flag.
- **Reviewer agreement rate:** % of flags a human reviewer would
  independently judge as meriting attention (ongoing sampled review).
- **Stale-case trend:** weeks-open for referrals and handoffs, before versus
  after the tool is introduced, broken out by office.
- **Flag volume versus staff capacity:** are High-confidence flags per week
  within what a team can realistically act on. This prototype's own run
  flagged 165 of 700 students (23.6%), 146 of them at High confidence,
  a concrete illustration that even a conservative, rule-based detector can
  outrun review capacity on its own.
- **Override/dismiss rate and stated reason:** if staff can mark a flag "not
  relevant," the reasons given become the real-world false-positive signal
  over time, and a mechanism for retuning thresholds against reality instead
  of against synthetic data.

## What I would need from a real institution before trusting this

Real, longitudinal, multi-source data with actual join keys across office
systems, not a clean synthetic schema; a definition, from the institution's
own care staff, of what should actually trigger action (my thresholds are
placeholders, not recommendations); a real picture of current staff capacity
per office so flag volume can be capacity-aware from day one rather than only
accuracy-aware; historical outcome data with enough time lag to check
retrospective usefulness; and early, explicit involvement from whoever owns
FERPA compliance and data governance, ideally before a working prototype
exists rather than after, so access boundaries are a design constraint
rather than a retrofit.

## Open Questions Not Yet Addressed Here

Raised in review and worth naming rather than quietly ignoring: this document
does not yet cover whether flag rates or false-positive rates could land
unevenly across student subgroups once real (and likely more identifying)
data is involved; whether a flagged student is ever informed or has any way
to contest a flag; or how to distinguish "the flag caused a staff action"
from "the action actually improved the outcome," which would need some kind
of comparison group, not just a behavioral count. None of these are solved
in this version. They're listed here so the gap is visible rather than
implied to not exist.
