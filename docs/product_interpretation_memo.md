# Product Interpretation Memo

*Note: this version shows the options considered and why each was chosen, for review purposes. The submission-ready version should likely compress this back toward the brief's 1-2 page target (see README).*

## Problem Interpretation

**Options considered:**
- A. A risk-prediction problem: build a better classifier that scores students by risk of disengagement or dropout.
- B. A data-integration problem: the hardest part is unifying messy multi-source campus data; signal generation is secondary once that's solved.
- C. A coordination/execution problem: the bottleneck is that flags don't turn into owned, tracked action, not that risk goes undetected.

**Chosen Answer:** The brief states this thesis explicitly and unprompted ("institutions do not primarily fail at detecting risk; they fail at executing on it"), which is a strong, deliberate signal about what HEIAXIS wants to differentiate on. Option A is the generic edtech-risk-tool answer and would make this prototype look like every other early-alert product. Option B is a real problem but is infrastructure/plumbing, not the product's core value proposition; it's a precondition for C, not a replacement for it.

**Low Level Explanation:** HEIAXIS isn't a prediction product wearing early-warning clothes (or rather, it shouldn't be). A referral with no closer, a handoff with no owner, an outreach that got no response and no follow-up: these are failures of the system to hold state, not failures of anyone to notice something bad in the moment. A product that only surfaces "this student might be at risk" competes with every existing early-alert tool. A product that also surfaces "this case is stalling, and here specifically is where and why" does something most of those tools don't: it makes the institution's own execution visible to itself.

**High Level Explanation:** Schools already have ways to notice a struggling student. The real problem is what happens after someone notices: a case gets opened and then just... sits there. Nobody's job is to follow up. So instead of building "yet another tool that spots struggling students" (which every competitor already does), we're building something that also watches whether the school itself is dropping the ball on cases it already knows about.

## Defining "Early Signal"

**Options considered:**
- A. A single, unified "risk score" per student blending every data source into one number.
- B. Population-relative anomaly detection: flag students who look statistically different from their peer group.
- C. Two distinct signal types, kept separate: (1) a student's own behavior relative to their own baseline, and (2) the institution's handling of a case (nulls, stale timestamps, unowned handoffs) as the signal itself.

**Chosen Answer:** Option A is exactly the "black-box conclusion" the brief warns against: a single blended score hides which source is actually driving the flag and invites false certainty. Option B conflates being different from peers (which may just mean being an introvert, an off-campus student, etc.) with declining, which is a common and avoidable source of false positives. C keeps the two signal types honest and separately explainable, and it's the only option of the three that treats the institution-as-signal idea as a first-class citizen rather than folding it into a student risk score.

**Low Level Explanation:** Two distinct things, deliberately not collapsed into one score. First, a change in a student's own behavior relative to their own baseline: not "this student looks different from other students," but "this student looks different from how they looked three weeks ago." Second, a change in the institution's own handling of a case (a null field, a stale status) that precedes or substitutes for any human noticing. The second is treated as the primary, more rigorous output here, because it's the one that's actually novel to HEIAXIS's stated thesis, and the one a transparent rule-based approach can answer with real confidence: a null `handoff_owner` field is a fact, not an inference.

**High Level Explanation:** There are two totally different kinds of warning signs, and we kept them separate on purpose. One is about the student: is this person acting differently than they usually do, not compared to other students, but compared to themselves a few weeks ago. The other is about the school's paperwork: has a case been sitting untouched with nobody assigned to it? That second kind doesn't even require knowing anything about the student's behavior: "this form has been open for three weeks with nobody's name on it" is a red flag all by itself.

## Data Selection Rationale

**Options considered:**
- A. Minimal schema: just engagement and outcome, the smallest set that technically satisfies the brief.
- B. Maximal schema: everything interesting that was discussed (ID-crosswalk, case audit log, free-text notes with tagging) built in from the start.
- C. Full multi-source schema matching all four brief-listed categories, plus a small number of cheap, thesis-aligned reference tables (academic calendar, staff roster).

**Chosen Answer:** Option A rejects the brief's own emphasis on multi-source complexity and would make the "data judgment" evaluation trivial to pass but not interesting. Option B blows the time budget on schema and generation complexity before any detection logic gets built, and much of it (ID-crosswalk, audit log) doesn't change what the current detectors can prove; it's realism for its own sake. C adds exactly two tables beyond the minimum, both chosen because they're cheap and directly change what a reviewer can conclude from a flag (calendar context prevents penalizing normal dips; staff roster turns "this office is dropping cases" into a testable capacity question instead of an implied accusation).

**Low Level Explanation:** Five operational tables (students, weekly engagement, belonging pulse, care interactions, weekly outcome) plus two reference tables: an academic calendar and a staff roster. No demographic or identity attributes were modeled; they weren't necessary for the mechanics under test, and a synthetic proxy for a protected characteristic has no place near a risk-flagging exercise, even a fabricated one.

**High Level Explanation:** We made up data for about 700 pretend students over 7 weeks: how often they show up to class, how much they use the school's online system, how connected they say they feel, and a log of the school reaching out to them (emails, meetings, counseling referrals, etc.). We also threw in two small extras: a calendar (so we know which weeks were midterms or breaks; a dip during finals week isn't scary) and a staff list (so we can tell if an office is dropping cases because it's understaffed, not because someone's slacking).

## What This Prototype Demonstrates

**Options considered:**
- A. That a trained model can predict which students are at risk with meaningful accuracy.
- B. That a full end-to-end product experience (UI, notifications, workflow) can be assembled quickly.
- C. That a small number of transparent, auditable rules can surface a genuinely useful shortlist of cases, with every flag traceable to specific field values.

**Chosen Answer:** Option A requires real outcome data to validate against, which doesn't exist for synthetic data without being circular (see evaluation logic doc); claiming otherwise would be the "overclaiming" the brief explicitly warns against. Option B is explicitly de-scoped by the brief itself ("please do not spend time making the UI beautiful"). C is the claim that's actually provable within the time budget and the data available, and it's the claim that matters most given the brief's emphasis on explainability over raw model complexity.

**Low Level Explanation:** That transparent rules, computed against each student's own baseline, requiring agreement across independent sources before a person is flagged, and computed directly from timestamps and null fields for institutional gaps, can surface a useful shortlist without a trained model, with every flag verifiable by a human reviewer in under a minute.

**High Level Explanation:** That you don't need fancy AI to catch this stuff. Simple, clear rules work, and every single flag comes with a plain-English reason a person can check for themselves in under a minute. Nothing here is a mystery black box.

## What This Prototype Does Not Demonstrate

**Options considered:**
- A. Stay silent on limitations and let the reviewer infer them from what was and wasn't built.
- B. Over-qualify extensively, to the point of undercutting confidence in the work itself.
- C. State explicit disclaimers: not a validated clinical/predictive tool, not proof the chosen thresholds are correct, not evidence of generalization beyond the synthetic patterns built in.

**Chosen Answer:** Option A risks the reviewer either overestimating what was proven (bad) or having to do the work of identifying gaps themselves, which reads as the candidate not having thought about it (also bad). Option B is a real failure mode too: the brief wants "clear thinking and disciplined execution," not hedging so heavy it obscures what was actually accomplished. C says exactly what's true, once, clearly, and moves on.

**Low Level Explanation:** This is not a validated clinical or predictive tool. It does not claim to generalize beyond the synthetic patterns built into the data. And it is not evidence that the specific thresholds used are the *right* thresholds for a real institution; those are placeholders that can only be set collaboratively with an institution's own care staff, against their actual tolerance for false positives and actual capacity to respond.

**High Level Explanation:** This is not a medical tool, not a diagnosis, and not proof it would actually work on real students. The specific numbers we picked (like "a 15% drop counts as a warning sign") are just placeholders; a real school would need to tell us what the right numbers actually are for their students.

## Scope Exclusions and Rationale

**Options considered:**
- A. Width over depth: attempt shallow versions of everything in the brief (ML model, UI, full validation suite, all schema extensions).
- B. Cut the institutional-gap detector specifically (the less familiar, more novel half) and focus entirely on student-side scoring, which is the more conventional/expected deliverable.
- C. Depth over width: cut hard on lower-value-per-hour items (ML, UI, formal statistical validation, some schema extensions) and go deep on the two core detectors and their explainability.

**Chosen Answer:** Option A produces a submission where nothing is fully convincing: exactly the outcome the brief warns against by saying "we are not looking for a perfect system." Option B would have been the safer, more conventional choice, but it throws away the part of the brief that's actually differentiated (the execution-failure thesis) in favor of the part every other applicant will also build. C is also the option that most directly answers what's being evaluated, since the brief explicitly frames scope-cutting as a first-class deliverable.

**Low Level Explanation:** No ML or scoring model anywhere (justified directly by the brief's own caution against black-box approaches). No UI, per the brief's explicit invitation not to invest there. No ID-crosswalk simulation and no case audit/escalation log, despite both being interesting (a real ingestion layer would eventually need both). No formal statistical validation, since there's no real ground truth to validate against without being circular; replaced with a clearly-labeled self-consistency check and an honest evaluation-logic writeup on what real validation would require. The weekly outcome field is generated, not predicted; included as a plausible downstream field, not a target variable, so the detectors don't look more validated than they are.

**High Level Explanation:** Given the time we had, we skipped: any actual AI/machine-learning model (kept it to simple rules instead), making it look pretty (it's spreadsheets and text output, no app), matching up messy student ID numbers across different school computer systems, and a detailed history log of every single action taken on a case. We also skipped doing a real scientific accuracy test, because that requires real student data we don't have; testing our own made-up data against our own made-up rules would just be us grading our own homework.
