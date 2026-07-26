# Code Walkthrough

A plain explanation of what each file in `src/` actually does, in the order they run. This covers the core pipeline only, not the tests or the API, see `docs/testing_strategy.md` and `docs/api.md` for those.

## generate_data.py

This is where the fake data comes from. There are no real students anywhere in this project, so this script invents 700 of them, spread across a 7-week term, along with a staff roster of 19 people split across five offices.

Each student is secretly given one of six hidden "storylines" (the code calls them archetypes): most are just stable and fine, some slowly disconnect over the term, some have their support case dropped by the school, some dip early and recover, some drop a course partway through, and a few look concerning at a glance but are actually just quiet by nature the whole time. That storyline is never saved anywhere the detection code can see, it only shapes what values get generated for that student in every table below.

On top of that, the script deliberately makes the data messy on purpose: some attendance numbers are impossibly high, a few login counts are negative, office names are spelled inconsistently across rows, and a handful of interaction records are duplicated. That messiness isn't a mistake, it's there so the next script actually has something real to clean up.

## cleaning.py

This is where all of that messiness gets fixed, and every fix gets counted. Attendance numbers over 100% get capped. Negative login counts get turned into "missing" instead of zero, because a negative number is clearly a bad reading, not proof the student logged in zero times. Office names get standardized so "Counseling", "counseling", and "Counseling Center" all become one thing. Duplicate interaction records get removed. Nothing here happens silently, every single correction is added to a report that gets printed and saved, so it's always possible to see exactly what was changed and why.

## features.py

This is where each student's recent behavior gets compared to their own earlier behavior. Specifically, it compares each student's first two weeks of the term to their last two weeks, for attendance, online activity, class participation, and how connected they say they feel. The key idea here: a student is only compared to themselves, never to other students. That's what stops a student who's simply quieter than average from getting flagged just for being who they are, since what matters is whether they changed, not where they started. If a student didn't answer enough surveys to make a fair comparison, that gets marked clearly instead of guessing at a number.

## signals.py

This is where the actual flagging happens, and it's plain rules, not AI. Two separate things get checked:

First, whether a student's own behavior has declined. This only triggers if at least two different things are getting worse at the same time (attendance and participation, for example), never just one on its own, since one slipping number by itself is too easy to get wrong. If three or more things are declining, or two are declining and their peer interactions are also down, that's treated as a stronger signal than just two declining alone.

Second, whether the school itself has dropped the ball on a case. This has nothing to do with the student's behavior. It looks for a help request that's been open for weeks with no resolution, an outreach message that got no response and nothing after it, or a handoff between staff where nobody's name ever got attached as the owner. A case being handled by two different offices at once, with neither seeming aware of the other, also counts.

Every single flag produced by either check comes with a plain-English reason and a confidence level, so nothing is a mystery number with no explanation attached.

## pipeline.py

This is the script that actually runs everything above, in order: load the data, clean it, compare each student to their own baseline, run both flagging checks, and write the results out. It also prints a short data-quality summary and a preview of both result lists to the screen, then saves everything as files so they can be opened and reviewed afterward.

## self_consistency_check.py (optional)

A small, separate script that checks whether the flagging logic tends to catch the same students the data generator secretly meant to be concerning. It's explicitly not proof the system actually works on real students, since the same person designed both the fake data and the rules that read it, agreeing with yourself isn't the same as being right. It exists purely as an honest sanity check, not a claim of validation.
