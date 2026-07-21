"""
Tier 1 test suite for the HEIAXIS Early Signal Intelligence prototype.

See docs/testing_strategy.md for the full plan and reasoning behind what's
covered here versus in tests/test_system.py (Tier 2).

Run with:
    cd heiaxis-sprint
    python3 -m pytest tests/test_pipeline.py -v
or, without pytest installed:
    python3 tests/test_pipeline.py

Two kinds of tests live in this file: checks against the actual generated
dataset (data integrity, cleaning correctness), and checks against small,
hand-constructed inputs with known expected outputs (feature math, signal
detection boundary conditions). The second kind matters more, it's the only
way to test a boundary condition (like "exactly 2 declining sources") that
the real synthetic dataset might not happen to contain an example of.

In short: this is Tier 1, granular checks on individual pieces of logic
in isolation, including the exact boundary conditions of the detection
rules, for example confirming exactly one declining source never
flags, but two does, and confirming a stale referral fires at exactly
its threshold week and not one week early or late.
"""
import os
import sys
import pandas as pd
import numpy as np

HERE = os.path.dirname(__file__)
SRC = os.path.join(HERE, "..", "src")
sys.path.insert(0, SRC)

from cleaning import load_raw, clean_all, normalize_office
from features import build_student_features, compute_engagement_features, _relative_change
from signals import (
    build_student_flags, build_continuity_gaps, build_office_caseload_summary,
    _score_student_row, MIN_RELATIVE_DECLINE,
    MIN_WEEKS_OPEN_FOR_STALE_REFERRAL, MIN_WEEKS_SINCE_UNANSWERED_OUTREACH,
)

DATA_DIR = os.path.join(HERE, "..", "data")

VALID_CONFIDENCE = {"High", "Medium", "Low"}

_CACHE = {}


def _setup():
    if "result" not in _CACHE:
        raw = load_raw(DATA_DIR)
        cleaned, report = clean_all(raw)
        features = build_student_features(cleaned)
        _CACHE["result"] = (cleaned, report, features)
    return _CACHE["result"]


def test_cleaning_removes_invalid_attendance():
    cleaned, _, _ = _setup()
    eng = cleaned["engagement"]
    assert eng["attendance_rate"].max() <= 1.0, "attendance_rate should be capped at 1.0"
    assert eng["attendance_rate"].min() >= 0.0, "attendance_rate should never be negative"


def test_cleaning_marks_negative_logins_missing_not_zero():
    cleaned, _, _ = _setup()
    eng = cleaned["engagement"]
    non_null_logins = eng["lms_logins"].dropna()
    assert (non_null_logins >= 0).all(), "no negative login counts should remain"
    assert eng["lms_logins"].isna().sum() > 0, \
        "expected at least one negative login value to have been nulled out"


def test_office_names_are_canonicalized():
    cleaned, _, _ = _setup()
    care = cleaned["care"]
    canonical = {"Counseling", "Academic Advising", "Financial Aid",
                 "Dean of Students", "Residential Life", "Unknown"}
    assert set(care["office"].unique()).issubset(canonical), \
        f"unexpected office values leaked through cleaning: {set(care['office'].unique()) - canonical}"


def test_no_duplicate_care_interactions():
    cleaned, _, _ = _setup()
    care = cleaned["care"]
    dupe_cols = ["student_id", "date", "office", "interaction_type",
                 "response_status", "referral_status"]
    assert not care.duplicated(subset=dupe_cols).any(), "duplicate interactions should be removed"


def test_all_student_ids_are_known():
    cleaned, _, _ = _setup()
    known = set(cleaned["students"]["student_id"])
    for name in ["engagement", "belonging", "care", "outcomes"]:
        ids = set(cleaned[name]["student_id"])
        assert ids.issubset(known), f"{name} references student_ids not in students.csv"


def test_data_quality_report_counts_match_actual_changes():
    raw = load_raw(DATA_DIR)
    cleaned, report = clean_all(raw)
    actual_capped = int((raw["engagement"]["attendance_rate"] > 1.0).sum())
    assert report["engagement.attendance_over_1_capped_to_1"] == actual_capped, \
        "data-quality report count doesn't match the number of rows actually capped"
    actual_negative = int((raw["engagement"]["lms_logins"] < 0).sum())
    assert report["engagement.negative_logins_treated_as_missing"] == actual_negative, \
        "data-quality report count doesn't match the number of rows actually nulled"


def test_data_quality_report_has_no_unexpectedly_dropped_rows():
    _, report, _ = _setup()
    for key, value in report.items():
        if key.endswith("_dropped_unknown_student"):
            assert value == 0, f"unexpected orphaned rows: {key} = {value}"


def test_normalize_office_handles_all_known_variants():
    variants = {
        "Counseling": "Counseling", "counseling": "Counseling",
        "Counseling Center": "Counseling", "counseling  ": "Counseling",
        "Academic Advising": "Academic Advising", "acad. advising": "Academic Advising",
        "Financial Aid": "Financial Aid", "finaid": "Financial Aid",
        "Dean of Students": "Dean of Students", "dos": "Dean of Students",
        "Residential Life": "Residential Life", "reslife": "Residential Life",
    }
    for raw, expected in variants.items():
        assert normalize_office(raw) == expected, f"{raw!r} should normalize to {expected!r}"


def test_normalize_office_passes_through_unknown_values():
    assert normalize_office("Some New Office") == "Some New Office"


def test_relative_change_known_values():
    assert abs(_relative_change(10, 8) - (-0.2)) < 1e-9
    assert abs(_relative_change(10, 12) - 0.2) < 1e-9
    assert _relative_change(5, 5) == 0.0


def test_relative_change_zero_baseline_does_not_crash():
    result = _relative_change(0, 5)
    assert pd.isna(result)


def test_relative_change_missing_baseline_returns_nan():
    assert pd.isna(_relative_change(None, 5))
    assert pd.isna(_relative_change(np.nan, 5))


def test_engagement_features_computed_correctly_on_known_input():
    rows = []
    for week, attendance in [(1, 0.9), (2, 0.9), (6, 0.6), (7, 0.6)]:
        rows.append({
            "student_id": "S_TEST", "week_number": week,
            "attendance_rate": attendance, "lms_activity_score": 50.0,
            "participation_score": 5.0,
        })
    eng = pd.DataFrame(rows)
    feats = compute_engagement_features(eng)
    row = feats[feats["student_id"] == "S_TEST"].iloc[0]
    assert abs(row["attendance_rate_rel_change"] - (-1 / 3)) < 1e-6


def _row(attendance=None, lms=None, participation=None, belonging=None, peer=None,
         belonging_status="sufficient"):
    return {
        "student_id": "S_TEST",
        "attendance_rate_rel_change": attendance,
        "lms_activity_score_rel_change": lms,
        "participation_score_rel_change": participation,
        "belonging_score_rel_change": belonging,
        "peer_interaction_rel_change": peer,
        "belonging_data_status": belonging_status,
    }


def test_single_declining_source_never_flags():
    row = _row(attendance=-0.30)
    assert _score_student_row(row) is None


def test_exactly_two_declining_sources_flags_medium_without_peer_corroboration():
    row = _row(attendance=-0.20, lms=-0.20, peer=None)
    result = _score_student_row(row)
    assert result is not None
    assert result["n_sources_declined"] == 2
    assert result["confidence"] == "Medium"


def test_exactly_two_declining_sources_flags_high_with_peer_corroboration():
    row = _row(attendance=-0.20, lms=-0.20, peer=-0.20)
    result = _score_student_row(row)
    assert result is not None
    assert result["confidence"] == "High"


def test_three_or_more_declining_sources_always_high():
    row = _row(attendance=-0.20, lms=-0.20, participation=-0.20, peer=None)
    result = _score_student_row(row)
    assert result["n_sources_declined"] == 3
    assert result["confidence"] == "High"


def test_decline_exactly_at_threshold_counts():
    row = _row(attendance=-MIN_RELATIVE_DECLINE, lms=-MIN_RELATIVE_DECLINE)
    result = _score_student_row(row)
    assert result is not None
    assert result["n_sources_declined"] == 2


def test_decline_just_short_of_threshold_does_not_count():
    row = _row(attendance=-(MIN_RELATIVE_DECLINE - 0.01), lms=-(MIN_RELATIVE_DECLINE - 0.01))
    result = _score_student_row(row)
    assert result is None


def test_no_declining_sources_does_not_flag():
    row = _row(attendance=0.05, lms=0.10)
    assert _score_student_row(row) is None


def test_student_flags_require_two_or_more_sources_on_real_data():
    cleaned, _, features = _setup()
    flags = build_student_flags(features)
    assert (flags["n_sources_declined"] >= 2).all(), \
        "co-occurrence rule violated: a flag exists with fewer than 2 declining sources"


def test_student_flags_have_required_explanation_fields():
    cleaned, _, features = _setup()
    flags = build_student_flags(features)
    for col in ["reason", "leading_signal", "confidence"]:
        assert col in flags.columns, f"missing required explanation column: {col}"
        assert flags[col].notna().all(), f"{col} should never be null on a flagged row"
        assert (flags[col].astype(str).str.len() > 0).all()
    assert set(flags["confidence"].unique()).issubset(VALID_CONFIDENCE)


def _care_row(student_id="S_TEST", week_number=1, office="Counseling",
              interaction_type="referral", response_status="n_a",
              referral_status="n_a", handoff_owner="", interaction_id="C1"):
    return {
        "interaction_id": interaction_id, "student_id": student_id,
        "week_number": week_number, "office": office,
        "interaction_type": interaction_type, "response_status": response_status,
        "referral_status": referral_status, "handoff_owner": handoff_owner,
    }


def test_stale_referral_fires_exactly_at_threshold_not_before():
    current_week = 10
    at_threshold = current_week - MIN_WEEKS_OPEN_FOR_STALE_REFERRAL
    care = pd.DataFrame([_care_row(week_number=at_threshold, referral_status="open")])
    gaps = build_continuity_gaps(care, current_week=current_week)
    assert len(gaps) == 1, "a referral open exactly at the threshold should be flagged"

    just_under = pd.DataFrame([_care_row(
        week_number=at_threshold + 1, referral_status="open")])
    gaps_under = build_continuity_gaps(just_under, current_week=current_week)
    assert len(gaps_under) == 0, "a referral open one week short of the threshold should not be flagged"


def test_closed_referral_never_flags_regardless_of_age():
    care = pd.DataFrame([_care_row(week_number=1, referral_status="closed")])
    gaps = build_continuity_gaps(care, current_week=20)
    assert len(gaps) == 0


def test_unowned_handoff_flags_even_when_very_recent():
    care = pd.DataFrame([_care_row(
        week_number=7, interaction_type="warm_handoff", handoff_owner="")])
    gaps = build_continuity_gaps(care, current_week=7)
    assert len(gaps) == 1
    assert gaps.iloc[0]["gap_type"] == "unowned_handoff"
    assert gaps.iloc[0]["confidence"] == "Medium"


def test_owned_handoff_never_flags():
    care = pd.DataFrame([_care_row(
        week_number=1, interaction_type="warm_handoff", handoff_owner="ST001")])
    gaps = build_continuity_gaps(care, current_week=20)
    assert len(gaps) == 0


def test_unanswered_outreach_requires_no_later_contact():
    care = pd.DataFrame([
        _care_row(week_number=1, interaction_type="outreach",
                   response_status="no_response", interaction_id="C1"),
        _care_row(week_number=3, interaction_type="staff_note", interaction_id="C2"),
    ])
    gaps = build_continuity_gaps(care, current_week=10)
    assert len(gaps) == 0, "a later touch of any kind should count as escalation"


def test_unanswered_outreach_with_no_later_contact_flags():
    care = pd.DataFrame([
        _care_row(week_number=1, interaction_type="outreach", response_status="no_response"),
    ])
    gaps = build_continuity_gaps(care, current_week=10)
    assert len(gaps) == 1
    assert gaps.iloc[0]["gap_type"] == "unanswered_outreach_no_escalation"


def test_multi_office_signal_requires_genuinely_distinct_offices():
    same_office = pd.DataFrame([
        _care_row(student_id="S1", week_number=1, office="Counseling",
                   interaction_type="referral", referral_status="open", interaction_id="C1"),
        _care_row(student_id="S1", week_number=2, office="Counseling",
                   interaction_type="referral", referral_status="open", interaction_id="C2"),
    ])
    gaps = build_continuity_gaps(same_office, current_week=10)
    assert "uncoordinated_multi_office" not in set(gaps["gap_type"]) if len(gaps) else True

    two_offices = pd.DataFrame([
        _care_row(student_id="S2", week_number=1, office="Counseling",
                   interaction_type="referral", referral_status="open", interaction_id="C3"),
        _care_row(student_id="S2", week_number=1, office="Financial Aid",
                   interaction_type="referral", referral_status="open", interaction_id="C4"),
    ])
    gaps2 = build_continuity_gaps(two_offices, current_week=10)
    assert "uncoordinated_multi_office" in set(gaps2["gap_type"])


def test_continuity_gaps_have_required_explanation_fields():
    cleaned, _, _ = _setup()
    gaps = build_continuity_gaps(cleaned["care"])
    for col in ["reason", "leading_signal", "confidence", "gap_type"]:
        assert col in gaps.columns, f"missing required explanation column: {col}"
        assert gaps[col].notna().all(), f"{col} should never be null on a flagged row"
    assert set(gaps["confidence"].unique()).issubset(VALID_CONFIDENCE)


def test_continuity_gap_types_are_known():
    cleaned, _, _ = _setup()
    gaps = build_continuity_gaps(cleaned["care"])
    known_types = {"stale_open_referral", "unanswered_outreach_no_escalation",
                   "unowned_handoff", "uncoordinated_multi_office"}
    assert set(gaps["gap_type"].unique()).issubset(known_types)


def test_office_caseload_summary_has_no_negative_values():
    cleaned, _, _ = _setup()
    summary = build_office_caseload_summary(cleaned["care"], cleaned["staff"])
    assert (summary["open_cases"] >= 0).all()
    assert (summary["staff_count"] >= 0).all()


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
