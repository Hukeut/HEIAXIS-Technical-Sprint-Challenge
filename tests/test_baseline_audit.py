"""
Week 1 test suite for the HEIAXIS Baseline Audit sprint.

Covers the three new tables (departments.csv, service_interactions.csv,
action_plans.csv) and the four Week 1 analysis outputs (department
bottleneck summary, broadened continuity gaps, action-plan summary,
student review list), kept in its own file rather than mixed into
tests/test_pipeline.py so the original Early Signal Intelligence test
suite stays untouched. See docs/testing_strategy.md and
docs/baseline_audit_data_model.md for the reasoning this builds on.

Run with:
    cd heiaxis-sprint
    python3 tests/test_baseline_audit.py

In short: hand-built boundary-condition tests for the new detectors
(exactly at a threshold, missing owner, overdue vs. merely incomplete,
two vs. one department), plus checks against the actual generated
dataset for cleaning and normalization. Deliberately does not cover a
Baseline Audit API, none exists yet, that's Week 2 scope.
"""
import os
import sys
import pandas as pd

HERE = os.path.dirname(__file__)
SRC = os.path.join(HERE, "..", "src")
DATA_DIR = os.path.join(HERE, "..", "data")
sys.path.insert(0, SRC)

from cleaning import load_raw, clean_all, normalize_department, normalize_status
from signals import (
    build_department_bottleneck_summary, build_baseline_continuity_gaps,
    build_action_plan_summary, build_student_review_list,
    _confidence_from_days, _priority_from_risk_factors,
    ANALYSIS_AS_OF, MIN_DAYS_OPEN_FOR_STALE_REFERRAL, MEDIUM_DELAY_DAYS, HIGH_DELAY_DAYS,
)

_CACHE = {}


def _setup():
    if "result" not in _CACHE:
        raw = load_raw(DATA_DIR)
        cleaned, report = clean_all(raw)
        bottleneck = build_department_bottleneck_summary(
            cleaned["service_interactions"], cleaned["departments"])
        gaps = build_baseline_continuity_gaps(
            cleaned["service_interactions"], cleaned["action_plans"], bottleneck)
        ap_summary = build_action_plan_summary(cleaned["action_plans"])
        review = build_student_review_list(gaps)
        _CACHE["result"] = (cleaned, report, bottleneck, gaps, ap_summary, review)
    return _CACHE["result"]


SI_COLUMNS = ["interaction_id", "workflow_id", "student_id", "date_opened", "date_closed",
              "department", "service_category", "interaction_type", "status",
              "source_priority", "assigned_owner", "referral_source", "referred_to_department"]

AP_COLUMNS = ["plan_id", "student_id", "department", "date_created", "target_completion_date",
              "actual_completion_date", "completion_status", "completion_percentage"]


def _si_row(**overrides):
    row = {
        "interaction_id": "SI00001", "workflow_id": "WF00001", "student_id": "S0001",
        "date_opened": pd.Timestamp("2026-02-05"), "date_closed": pd.NaT,
        "department": "Counseling", "service_category": "academic",
        "interaction_type": "referral", "status": "open", "source_priority": "medium",
        "assigned_owner": "ST001", "referral_source": "", "referred_to_department": "",
    }
    row.update(overrides)
    return row


def _ap_row(**overrides):
    row = {
        "plan_id": "AP0001", "student_id": "S0001", "department": "Counseling",
        "date_created": pd.Timestamp("2026-02-05"),
        "target_completion_date": pd.Timestamp("2026-02-19"),
        "actual_completion_date": pd.NaT,
        "completion_status": "incomplete", "completion_percentage": 30,
    }
    row.update(overrides)
    return row


def _departments(staff_counts=None):
    staff_counts = staff_counts or {"Counseling": 4, "Academic Advising": 6, "Financial Aid": 3,
                                     "Dean of Students": 2, "Residential Life": 3}
    return pd.DataFrame([
        {"department_id": f"DPT{i+1:02d}", "department_name": name, "staff_count": n,
         "service_area": "x"}
        for i, (name, n) in enumerate(staff_counts.items())
    ])


# =====================================================================
# Normalization (cleaning.py additions)
# =====================================================================

def test_normalize_department_handles_known_variants():
    assert normalize_department("counseling") == "Counseling"
    assert normalize_department("Counseling Center") == "Counseling"
    assert normalize_department("DOS") == "Dean of Students"
    assert normalize_department("reslife") == "Residential Life"


def test_normalize_department_returns_unknown_for_unrecognized():
    # Unlike normalize_office, an unrecognized non-null value becomes
    # "Unknown" here rather than passing through unchanged, since these
    # are genuinely different departments, not casing variants of a
    # known one.
    assert normalize_department("IT Helpdesk") == "Unknown"
    assert normalize_department(None) == "Unknown"


def test_normalize_status_strips_and_lowercases():
    assert normalize_status("Open") == "open"
    assert normalize_status("CLOSED") == "closed"
    assert normalize_status("closed ") == "closed"


def test_normalize_status_missing_returns_unknown():
    assert normalize_status(None) == "Unknown"


# =====================================================================
# Cleaning against the real generated dataset
# =====================================================================

def test_service_interactions_unknown_student_rows_are_dropped():
    cleaned, report, *_ = _setup()
    assert report["service_interactions.rows_dropped_unknown_student"] > 0
    known_students = set(cleaned["students"]["student_id"])
    assert cleaned["service_interactions"]["student_id"].isin(known_students).all()


def test_service_interactions_unrecognized_department_becomes_unknown():
    cleaned, report, *_ = _setup()
    assert report["service_interactions.rows_with_unrecognized_department"] > 0
    si = cleaned["service_interactions"]
    known = {"Counseling", "Academic Advising", "Financial Aid", "Dean of Students",
             "Residential Life", "Unknown"}
    assert set(si["department"].unique()).issubset(known)


def test_service_interactions_no_duplicate_rows_remain():
    cleaned, report, *_ = _setup()
    si = cleaned["service_interactions"]
    dedupe_cols = ["workflow_id", "student_id", "date_opened", "department",
                   "interaction_type", "status"]
    assert not si.duplicated(subset=dedupe_cols).any()


def test_service_interactions_no_invalid_date_order_remains():
    cleaned, *_ = _setup()
    si = cleaned["service_interactions"]
    has_close = si["date_closed"].notna()
    assert not (has_close & (si["date_closed"] < si["date_opened"])).any()


def test_action_plans_completion_percentage_within_valid_range():
    cleaned, report, *_ = _setup()
    assert report["action_plans.completion_percentage_out_of_range_capped"] > 0
    ap = cleaned["action_plans"]
    assert (ap["completion_percentage"] >= 0).all()
    assert (ap["completion_percentage"] <= 100).all()


# =====================================================================
# Confidence and priority (hand-built, boundary conditions)
# =====================================================================

def test_confidence_from_days_boundaries():
    assert _confidence_from_days(HIGH_DELAY_DAYS) == "High"
    assert _confidence_from_days(HIGH_DELAY_DAYS - 1) == "Medium"
    assert _confidence_from_days(MEDIUM_DELAY_DAYS) == "Medium"
    assert _confidence_from_days(MEDIUM_DELAY_DAYS - 1) == "Low"


def test_priority_from_risk_factors_counts_do_not_weight():
    assert _priority_from_risk_factors(False, False, False) == "Low"
    assert _priority_from_risk_factors(True, False, False) == "Medium"
    assert _priority_from_risk_factors(True, True, False) == "Medium"
    assert _priority_from_risk_factors(True, True, True) == "High"
    assert _priority_from_risk_factors(True, True, True, True) == "High"


def test_confidence_and_priority_are_computed_independently():
    # A long-elapsed, otherwise-clean gap: confidence should read High
    # (the pattern has held a long time), but priority should NOT
    # automatically follow, since none of priority's own risk factors
    # (missing owner, cross-department, overdue plan, department
    # pressure) are true here.
    high_confidence = _confidence_from_days(60)
    low_risk_priority = _priority_from_risk_factors(False, False, False)
    assert high_confidence == "High"
    assert low_risk_priority == "Low"
    assert high_confidence != low_risk_priority

    # The reverse: a very recent gap (Low confidence) that already has
    # every structural risk factor present should still read High
    # priority, proving the two are not just the same number relabeled.
    low_confidence = _confidence_from_days(1)
    high_risk_priority = _priority_from_risk_factors(True, True, True)
    assert low_confidence == "Low"
    assert high_risk_priority == "High"


# =====================================================================
# Department bottleneck summary (hand-built)
# =====================================================================

def test_bottleneck_summary_detects_overdue_case():
    departments = _departments({"Counseling": 2})
    si = pd.DataFrame([
        _si_row(department="Counseling", status="open",
                date_opened=ANALYSIS_AS_OF - pd.Timedelta(days=30)),
    ])
    summary = build_department_bottleneck_summary(si, departments)
    row = summary[summary["department"] == "Counseling"].iloc[0]
    assert row["overdue_cases"] == 1
    assert row["open_cases"] == 1


def test_bottleneck_summary_not_overdue_just_under_threshold():
    departments = _departments({"Counseling": 2})
    si = pd.DataFrame([
        _si_row(department="Counseling", status="open",
                date_opened=ANALYSIS_AS_OF - pd.Timedelta(days=21)),
    ])
    summary = build_department_bottleneck_summary(si, departments)
    row = summary[summary["department"] == "Counseling"].iloc[0]
    assert row["overdue_cases"] == 0


def test_bottleneck_summary_days_to_close_null_when_nothing_closed():
    departments = _departments({"Counseling": 2})
    si = pd.DataFrame([_si_row(department="Counseling", status="open")])
    summary = build_department_bottleneck_summary(si, departments)
    row = summary[summary["department"] == "Counseling"].iloc[0]
    assert pd.isna(row["avg_days_to_close"])
    assert pd.isna(row["median_days_to_close"])


def test_bottleneck_summary_cases_per_staff_null_when_staff_zero():
    departments = _departments({"Counseling": 0})
    si = pd.DataFrame([_si_row(department="Counseling", status="open")])
    summary = build_department_bottleneck_summary(si, departments)
    row = summary[summary["department"] == "Counseling"].iloc[0]
    assert pd.isna(row["cases_per_staff"])


def test_bottleneck_summary_empty_input_stable_shape():
    departments = _departments()
    empty_si = pd.DataFrame(columns=SI_COLUMNS)
    summary = build_department_bottleneck_summary(empty_si, departments)
    assert len(summary) == len(departments)
    assert (summary["open_cases"] == 0).all()


# =====================================================================
# Broadened continuity gaps (hand-built, boundary conditions)
# =====================================================================

def _empty_bottleneck():
    return pd.DataFrame(columns=["department", "open_cases", "avg_days_to_close",
                                  "median_days_to_close", "overdue_cases",
                                  "unresolved_referrals", "staff_count", "cases_per_staff"])


def test_stale_referral_fires_exactly_at_threshold_not_before():
    at_threshold = pd.DataFrame([_si_row(
        interaction_type="referral", status="open",
        date_opened=ANALYSIS_AS_OF - pd.Timedelta(days=MIN_DAYS_OPEN_FOR_STALE_REFERRAL))])
    gaps = build_baseline_continuity_gaps(at_threshold, pd.DataFrame(columns=AP_COLUMNS), _empty_bottleneck())
    assert (gaps["gap_type"] == "stale_open_referral").any()

    just_short = pd.DataFrame([_si_row(
        interaction_type="referral", status="open",
        date_opened=ANALYSIS_AS_OF - pd.Timedelta(days=MIN_DAYS_OPEN_FOR_STALE_REFERRAL - 1))])
    gaps = build_baseline_continuity_gaps(just_short, pd.DataFrame(columns=AP_COLUMNS), _empty_bottleneck())
    assert not (gaps["gap_type"] == "stale_open_referral").any()


def test_closed_referral_never_flags_as_stale():
    si = pd.DataFrame([_si_row(
        interaction_type="referral", status="closed",
        date_opened=ANALYSIS_AS_OF - pd.Timedelta(days=90))])
    gaps = build_baseline_continuity_gaps(si, pd.DataFrame(columns=AP_COLUMNS), _empty_bottleneck())
    assert not (gaps["gap_type"] == "stale_open_referral").any()


def test_unowned_workflow_step_flags_open_row_with_no_owner():
    si = pd.DataFrame([_si_row(interaction_type="handoff", status="open", assigned_owner="")])
    gaps = build_baseline_continuity_gaps(si, pd.DataFrame(columns=AP_COLUMNS), _empty_bottleneck())
    assert (gaps["gap_type"] == "unowned_workflow_step").any()


def test_unowned_workflow_step_excludes_closed_rows():
    # A closed interaction with no owner isn't an active gap, the work
    # is already done regardless of who's on record for it.
    si = pd.DataFrame([_si_row(interaction_type="handoff", status="closed", assigned_owner="")])
    gaps = build_baseline_continuity_gaps(si, pd.DataFrame(columns=AP_COLUMNS), _empty_bottleneck())
    assert not (gaps["gap_type"] == "unowned_workflow_step").any()


def test_owned_open_row_never_flags_as_unowned():
    si = pd.DataFrame([_si_row(interaction_type="handoff", status="open", assigned_owner="ST001")])
    gaps = build_baseline_continuity_gaps(si, pd.DataFrame(columns=AP_COLUMNS), _empty_bottleneck())
    assert not (gaps["gap_type"] == "unowned_workflow_step").any()


def test_no_later_follow_up_requires_no_later_interaction():
    old_date = ANALYSIS_AS_OF - pd.Timedelta(days=20)
    no_follow_up = pd.DataFrame([_si_row(
        interaction_id="SI00001", interaction_type="check_in", status="open",
        date_opened=old_date)])
    gaps = build_baseline_continuity_gaps(no_follow_up, pd.DataFrame(columns=AP_COLUMNS), _empty_bottleneck())
    assert (gaps["gap_type"] == "no_later_follow_up").any()

    # The later row uses a type outside the followable set (check_in,
    # referral), so it doesn't become a no-follow-up candidate in its
    # own right, only its presence as "something happened after" matters
    # for the first row's check.
    with_follow_up = pd.DataFrame([
        _si_row(interaction_id="SI00001", interaction_type="check_in", status="open",
                date_opened=old_date),
        _si_row(interaction_id="SI00002", interaction_type="staff_note", status="closed",
                date_opened=old_date + pd.Timedelta(days=3)),
    ])
    gaps = build_baseline_continuity_gaps(with_follow_up, pd.DataFrame(columns=AP_COLUMNS), _empty_bottleneck())
    assert not (gaps["gap_type"] == "no_later_follow_up").any()


def test_overdue_action_plan_detected_with_high_confidence():
    ap = pd.DataFrame([_ap_row(
        completion_status="incomplete",
        target_completion_date=ANALYSIS_AS_OF - pd.Timedelta(days=5),
        actual_completion_date=pd.NaT,
    )])
    gaps = build_baseline_continuity_gaps(pd.DataFrame(columns=SI_COLUMNS), ap, _empty_bottleneck())
    row = gaps[gaps["gap_type"] == "incomplete_or_overdue_action_plan"].iloc[0]
    assert row["confidence"] == "High"


def test_incomplete_but_not_yet_overdue_plan_gets_medium_confidence():
    ap = pd.DataFrame([_ap_row(
        completion_status="incomplete",
        target_completion_date=ANALYSIS_AS_OF + pd.Timedelta(days=10),
        actual_completion_date=pd.NaT,
    )])
    gaps = build_baseline_continuity_gaps(pd.DataFrame(columns=SI_COLUMNS), ap, _empty_bottleneck())
    row = gaps[gaps["gap_type"] == "incomplete_or_overdue_action_plan"].iloc[0]
    assert row["confidence"] == "Medium"


def test_completed_plan_never_flags():
    ap = pd.DataFrame([_ap_row(
        completion_status="completed", completion_percentage=100,
        actual_completion_date=ANALYSIS_AS_OF - pd.Timedelta(days=1),
    )])
    gaps = build_baseline_continuity_gaps(pd.DataFrame(columns=SI_COLUMNS), ap, _empty_bottleneck())
    assert not (gaps["gap_type"] == "incomplete_or_overdue_action_plan").any()


def test_uncoordinated_multi_department_requires_two_distinct_departments():
    single_dept = pd.DataFrame([
        _si_row(interaction_id="SI00001", department="Counseling", status="open"),
        _si_row(interaction_id="SI00002", department="Counseling", status="open"),
    ])
    gaps = build_baseline_continuity_gaps(single_dept, pd.DataFrame(columns=AP_COLUMNS), _empty_bottleneck())
    assert not (gaps["gap_type"] == "uncoordinated_multi_department").any()

    two_depts = pd.DataFrame([
        _si_row(interaction_id="SI00001", department="Counseling", status="open"),
        _si_row(interaction_id="SI00002", department="Financial Aid", status="open"),
    ])
    gaps = build_baseline_continuity_gaps(two_depts, pd.DataFrame(columns=AP_COLUMNS), _empty_bottleneck())
    assert (gaps["gap_type"] == "uncoordinated_multi_department").any()


def test_uncoordinated_multi_department_excludes_unknown_department():
    # A student active in one real department plus one "Unknown" row
    # should not count as spanning two departments, "Unknown" isn't a
    # real second department to be uncoordinated across.
    si = pd.DataFrame([
        _si_row(interaction_id="SI00001", department="Counseling", status="open"),
        _si_row(interaction_id="SI00002", department="Unknown", status="open"),
    ])
    gaps = build_baseline_continuity_gaps(si, pd.DataFrame(columns=AP_COLUMNS), _empty_bottleneck())
    assert not (gaps["gap_type"] == "uncoordinated_multi_department").any()


def test_baseline_gaps_empty_input_stable_shape():
    gaps = build_baseline_continuity_gaps(
        pd.DataFrame(columns=SI_COLUMNS), pd.DataFrame(columns=AP_COLUMNS), _empty_bottleneck())
    assert len(gaps) == 0
    assert list(gaps.columns) == ["gap_type", "student_id", "workflow_id", "department",
                                   "days_elapsed", "confidence", "priority",
                                   "leading_signal", "reason", "evidence"]


# =====================================================================
# Action-plan summary (hand-built)
# =====================================================================

def test_action_plan_summary_overdue_not_mutually_exclusive_with_incomplete():
    ap = pd.DataFrame([_ap_row(
        completion_status="incomplete", completion_percentage=10,
        target_completion_date=ANALYSIS_AS_OF - pd.Timedelta(days=5),
        actual_completion_date=pd.NaT,
    )])
    summary = build_action_plan_summary(ap)
    assert summary.iloc[0]["incomplete"] == 1
    assert summary.iloc[0]["overdue"] == 1


def test_action_plan_summary_empty_input():
    summary = build_action_plan_summary(pd.DataFrame(columns=AP_COLUMNS))
    row = summary.iloc[0]
    assert row["total_plans"] == 0
    assert pd.isna(row["average_completion_percentage"])


# =====================================================================
# Student review list (hand-built)
# =====================================================================

def test_student_review_list_one_row_per_student_not_per_gap():
    si = pd.DataFrame([
        _si_row(interaction_id="SI00001", student_id="S0001", department="Counseling",
                interaction_type="referral", status="open",
                date_opened=ANALYSIS_AS_OF - pd.Timedelta(days=MIN_DAYS_OPEN_FOR_STALE_REFERRAL)),
        _si_row(interaction_id="SI00002", student_id="S0001", department="Financial Aid",
                interaction_type="handoff", status="open", assigned_owner=""),
    ])
    gaps = build_baseline_continuity_gaps(si, pd.DataFrame(columns=AP_COLUMNS), _empty_bottleneck())
    assert gaps["student_id"].eq("S0001").sum() >= 2

    review = build_student_review_list(gaps)
    assert len(review[review["student_id"] == "S0001"]) == 1


def test_student_review_list_departments_involved_is_union():
    si = pd.DataFrame([
        _si_row(interaction_id="SI00001", student_id="S0001", department="Counseling",
                interaction_type="referral", status="open",
                date_opened=ANALYSIS_AS_OF - pd.Timedelta(days=MIN_DAYS_OPEN_FOR_STALE_REFERRAL)),
        _si_row(interaction_id="SI00002", student_id="S0001", department="Financial Aid",
                interaction_type="handoff", status="open", assigned_owner=""),
    ])
    gaps = build_baseline_continuity_gaps(si, pd.DataFrame(columns=AP_COLUMNS), _empty_bottleneck())
    review = build_student_review_list(gaps)
    row = review[review["student_id"] == "S0001"].iloc[0]
    assert "Counseling" in row["departments_involved"]
    assert "Financial Aid" in row["departments_involved"]


def test_student_review_list_leading_issue_is_most_urgent():
    # One gap with every risk factor present (severe delay, missing
    # owner, and department under pressure, via a non-empty bottleneck
    # naming Counseling), one with none of them, same student. The
    # student's single row should reflect the more urgent of the two.
    si = pd.DataFrame([
        _si_row(interaction_id="SI00001", student_id="S0001", department="Counseling",
                interaction_type="handoff", status="open", assigned_owner="",
                date_opened=ANALYSIS_AS_OF - pd.Timedelta(days=60)),
        _si_row(interaction_id="SI00002", student_id="S0001", department="Counseling",
                interaction_type="handoff", status="open", assigned_owner="ST001",
                date_opened=ANALYSIS_AS_OF - pd.Timedelta(days=1)),
    ])
    bottleneck = pd.DataFrame([{
        "department": "Counseling", "open_cases": 10, "avg_days_to_close": 5.0,
        "median_days_to_close": 5.0, "overdue_cases": 2, "unresolved_referrals": 1,
        "staff_count": 1, "cases_per_staff": 10.0,
    }])
    gaps = build_baseline_continuity_gaps(si, pd.DataFrame(columns=AP_COLUMNS), bottleneck)
    review = build_student_review_list(gaps)
    row = review[review["student_id"] == "S0001"].iloc[0]
    assert row["priority"] == "High"
    assert row["leading_issue"] == "unowned_workflow_step"


def test_student_review_list_empty_input():
    review = build_student_review_list(pd.DataFrame(columns=[
        "gap_type", "student_id", "workflow_id", "department", "days_elapsed",
        "confidence", "priority", "leading_signal", "reason", "evidence"]))
    assert len(review) == 0


# =====================================================================
# Integration: the real generated dataset, end to end
# =====================================================================

def test_all_four_outputs_produce_rows_on_real_data():
    _, _, bottleneck, gaps, ap_summary, review = _setup()
    assert len(bottleneck) == 5
    assert len(gaps) > 0
    assert ap_summary.iloc[0]["total_plans"] > 0
    assert len(review) > 0
    assert len(review) == gaps["student_id"].nunique()


def test_confidence_and_priority_distributions_differ_on_real_data():
    # If confidence and priority were accidentally the same calculation,
    # their value counts would be identical. On real data they should
    # not be.
    _, _, _, gaps, _, _ = _setup()
    conf_counts = gaps["confidence"].value_counts().to_dict()
    prio_counts = gaps["priority"].value_counts().to_dict()
    assert conf_counts != prio_counts


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
