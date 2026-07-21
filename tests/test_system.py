"""
Tier 2 general / system tests for the HEIAXIS Early Signal Intelligence prototype.

See docs/testing_strategy.md for the full reasoning. Where tests/test_pipeline.py
(Tier 1) checks individual pieces of logic in isolation, this file checks that
the whole system still behaves sensibly end to end, including a regression
check against the fixed generator seed, and a few edge cases a normal run
against the bundled dataset would never exercise.

Run with:
    cd heiaxis-sprint
    python3 tests/test_system.py

In short: this is Tier 2, checks against the whole system end to end,
a full smoke run from data generation through pipeline output, a
seed-based regression check that fails if flag counts silently drift,
and edge cases a normal run would never hit. Writing these edge-case
tests actually caught two real crashes in features.py and signals.py,
both relied on a pandas quirk where operations on an empty DataFrame
silently drop expected columns; both are now fixed with explicit
empty-input guards.
"""
import os
import sys
import subprocess
import pandas as pd

HERE = os.path.dirname(__file__)
SRC = os.path.join(HERE, "..", "src")
ROOT = os.path.join(HERE, "..")
OUTPUT_DIR = os.path.join(ROOT, "output")
sys.path.insert(0, SRC)

from cleaning import clean_all
from features import build_student_features
from signals import build_student_flags, build_continuity_gaps

# Known-good counts for the bundled dataset, generated with random.seed(42).
# If these ever change, it means the generator or the detection logic
# changed, either intentionally (update this file and explain why in the
# commit) or by accident (this test just caught a real regression).
EXPECTED_STUDENT_FLAG_COUNT = 165
EXPECTED_STUDENT_HIGH_CONFIDENCE = 146
EXPECTED_CONTINUITY_GAP_COUNT = 148


def _run(cmd, cwd):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
    return result


# =====================================================================
# End-to-end smoke run
# =====================================================================

def test_generate_data_runs_cleanly():
    result = _run([sys.executable, "src/generate_data.py"], cwd=ROOT)
    assert result.returncode == 0, f"generate_data.py exited non-zero:\n{result.stderr}"
    for fname in ["students.csv", "staff.csv", "engagement_weekly.csv",
                  "belonging_pulse.csv", "care_interactions.csv",
                  "weekly_outcome.csv", "academic_calendar.csv"]:
        path = os.path.join(ROOT, "data", fname)
        assert os.path.exists(path), f"expected data file missing: {fname}"
        assert os.path.getsize(path) > 0, f"data file is empty: {fname}"


def test_pipeline_runs_cleanly_and_produces_well_formed_output():
    result = _run([sys.executable, "src/pipeline.py"], cwd=ROOT)
    assert result.returncode == 0, f"pipeline.py exited non-zero:\n{result.stderr}"

    flagged_path = os.path.join(OUTPUT_DIR, "flagged_students.csv")
    gaps_path = os.path.join(OUTPUT_DIR, "continuity_gaps.csv")
    assert os.path.exists(flagged_path) and os.path.exists(gaps_path)

    flagged = pd.read_csv(flagged_path)
    gaps = pd.read_csv(gaps_path)
    assert len(flagged) > 0, "expected at least some students to be flagged"
    assert len(gaps) > 0, "expected at least some continuity gaps to be found"
    for col in ["student_id", "reason", "leading_signal", "confidence"]:
        assert col in flagged.columns
    for col in ["gap_type", "reason", "leading_signal", "confidence"]:
        assert col in gaps.columns


def test_test_suite_itself_passes():
    # A smoke test's job includes confirming the rest of the safety net
    # is intact. If Tier 1 is broken, Tier 2 passing alone would be a
    # false sense of security.
    result = _run([sys.executable, "tests/test_pipeline.py"], cwd=ROOT)
    assert result.returncode == 0, f"tests/test_pipeline.py failed:\n{result.stdout}\n{result.stderr}"


# =====================================================================
# Seed-based regression check
# =====================================================================

def test_flag_counts_match_known_seed_42_baseline():
    # Regenerate from scratch to be sure this isn't reading stale output
    # left over from a previous run.
    gen = _run([sys.executable, "src/generate_data.py"], cwd=ROOT)
    assert gen.returncode == 0
    run = _run([sys.executable, "src/pipeline.py"], cwd=ROOT)
    assert run.returncode == 0

    flagged = pd.read_csv(os.path.join(OUTPUT_DIR, "flagged_students.csv"))
    gaps = pd.read_csv(os.path.join(OUTPUT_DIR, "continuity_gaps.csv"))

    assert len(flagged) == EXPECTED_STUDENT_FLAG_COUNT, (
        f"student flag count drifted: expected {EXPECTED_STUDENT_FLAG_COUNT}, "
        f"got {len(flagged)}. If this is an intentional logic change, update "
        f"the expected value in this file and explain why in the commit."
    )
    high_count = int((flagged["confidence"] == "High").sum())
    assert high_count == EXPECTED_STUDENT_HIGH_CONFIDENCE, (
        f"High-confidence student flag count drifted: expected "
        f"{EXPECTED_STUDENT_HIGH_CONFIDENCE}, got {high_count}."
    )
    assert len(gaps) == EXPECTED_CONTINUITY_GAP_COUNT, (
        f"continuity gap count drifted: expected {EXPECTED_CONTINUITY_GAP_COUNT}, "
        f"got {len(gaps)}."
    )


# =====================================================================
# Edge cases a normal run against the bundled dataset never exercises
# =====================================================================

def test_empty_engagement_data_does_not_crash():
    empty_eng = pd.DataFrame(columns=[
        "student_id", "week_number", "attendance_rate", "lms_logins",
        "lms_activity_score", "sessions_missed", "participation_score",
    ])
    empty_bel = pd.DataFrame(columns=[
        "student_id", "week_number", "survey_submitted",
        "belonging_score", "peer_interaction_count",
    ])
    empty_students = pd.DataFrame(columns=["student_id", "program", "class_year"])
    cleaned = {"engagement": empty_eng, "belonging": empty_bel, "students": empty_students}
    features = build_student_features(cleaned)
    assert len(features) == 0
    flags = build_student_flags(features)
    assert len(flags) == 0


def test_empty_care_interactions_does_not_crash():
    empty_care = pd.DataFrame(columns=[
        "interaction_id", "student_id", "week_number", "office",
        "interaction_type", "response_status", "referral_status", "handoff_owner",
    ])
    gaps = build_continuity_gaps(empty_care)
    assert len(gaps) == 0


def test_student_missing_from_belonging_table_is_handled_not_dropped():
    # A student who has engagement data but never appears in the belonging
    # survey table at all (not just "didn't submit some weeks", genuinely
    # absent) should still get a features row, with belonging marked
    # insufficient rather than the student silently vanishing.
    eng_rows = []
    for week in [1, 2, 6, 7]:
        eng_rows.append({
            "student_id": "S_GHOST", "week_number": week,
            "attendance_rate": 0.9, "lms_logins": 10,
            "lms_activity_score": 60.0, "sessions_missed": 0,
            "participation_score": 5.0,
        })
    engagement = pd.DataFrame(eng_rows)
    belonging = pd.DataFrame(columns=[
        "student_id", "week_number", "survey_submitted",
        "belonging_score", "peer_interaction_count",
    ])
    students = pd.DataFrame([{"student_id": "S_GHOST", "program": "Undeclared", "class_year": "Freshman"}])
    cleaned = {"engagement": engagement, "belonging": belonging, "students": students}
    features = build_student_features(cleaned)
    assert "S_GHOST" in set(features["student_id"]), \
        "a student missing from the belonging table entirely should not disappear from features"


def test_all_identical_students_produce_zero_flags():
    # No variance at all across weeks -- relative change is exactly 0
    # everywhere, so nothing should ever cross the decline threshold.
    rows = []
    for sid in ["S1", "S2", "S3"]:
        for week in range(1, 8):
            rows.append({
                "student_id": sid, "week_number": week,
                "attendance_rate": 0.85, "lms_logins": 10,
                "lms_activity_score": 55.0, "sessions_missed": 0,
                "participation_score": 6.0,
            })
    engagement = pd.DataFrame(rows)
    belonging = pd.DataFrame(columns=[
        "student_id", "week_number", "survey_submitted",
        "belonging_score", "peer_interaction_count",
    ])
    students = pd.DataFrame([{"student_id": s, "program": "Undeclared", "class_year": "Freshman"}
                              for s in ["S1", "S2", "S3"]])
    cleaned = {"engagement": engagement, "belonging": belonging, "students": students}
    features = build_student_features(cleaned)
    flags = build_student_flags(features)
    assert len(flags) == 0, "identical, non-declining students should never be flagged"


if __name__ == "__main__":
    import traceback
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    passed, failed = 0, 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception:
            print(f"ERROR {t.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
