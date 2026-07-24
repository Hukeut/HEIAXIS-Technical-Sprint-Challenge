"""
Cleaning & validation for the HEIAXIS Early Signal Intelligence prototype.

Loads the raw synthetic CSVs and returns cleaned DataFrames plus a
data-quality report (dict of counts) describing what was found and how
it was handled. Nothing is silently dropped or altered without being
counted in the report -- the report is printed by pipeline.py and is
part of the "clean and validate" requirement, not an afterthought.

In short: this module is where every deliberate imperfection injected
by generate_data.py gets caught and accounted for. Out-of-range
attendance values are capped rather than left as garbage. Negative
login counts become missing, not silently zeroed, since a negative
reading is a bad ETL value, not evidence of zero activity. Office
names are canonicalized through a lookup table. Duplicate care
interaction rows are dropped. Every one of these actions is counted in
the report this module returns, nothing is silently altered.

Baseline Audit addition (Week 1): the same philosophy extends to
service_interactions.csv and action_plans.csv. Department names and
status values are normalized the same way office names already are.
Rows naming a department that isn't one of the five known ones become
"Unknown" and are counted, rather than passed through unrecognized.
An impossible date_closed (before date_opened) is treated as missing,
the same reasoning as negative login counts. Completion percentages
outside 0-100 are capped, the same reasoning as capped attendance
rates. A completion_status of "completed" that disagrees with its own
completion_percentage is not corrected either way, since there's no
way to know which field is wrong, it is only counted and reported.
"""
import os
import pandas as pd
import numpy as np

TERM_START = pd.Timestamp("2026-02-02")

CANONICAL_OFFICES = {
    "counseling": "Counseling",
    "counseling center": "Counseling",
    "academic advising": "Academic Advising",
    "acad. advising": "Academic Advising",
    "financial aid": "Financial Aid",
    "finaid": "Financial Aid",
    "dean of students": "Dean of Students",
    "dos": "Dean of Students",
    "residential life": "Residential Life",
    "reslife": "Residential Life",
}


def normalize_office(raw):
    if pd.isna(raw):
        return "Unknown"
    key = str(raw).strip().lower()
    return CANONICAL_OFFICES.get(key, str(raw).strip())


def normalize_department(raw):
    """Normalize a department name to one of the five known department
    names, or "Unknown" if it's missing or not recognized at all.

    Unlike normalize_office, an unrecognized non-null value is not
    passed through unchanged, it becomes "Unknown" and is counted.
    Baseline Audit's messiness deliberately injects department names
    ("IT Helpdesk", "Unknown Dept") that aren't a casing variant of a
    real department, they're a different department entirely, which is
    a distinct data-quality issue worth reporting on its own.

    Args:
        raw: The raw department (or office) value from a source row.

    Returns:
        One of the five canonical department names, or "Unknown".
    """
    if pd.isna(raw):
        return "Unknown"
    key = str(raw).strip().lower()
    return CANONICAL_OFFICES.get(key, "Unknown")


def normalize_status(raw):
    """Normalize a status value by stripping whitespace and casing.

    Args:
        raw: The raw status value from a source row.

    Returns:
        The lowercased, stripped status string, or "Unknown" if missing.
    """
    if pd.isna(raw):
        return "Unknown"
    return str(raw).strip().lower()


def load_raw(data_dir):
    return dict(
        students=pd.read_csv(os.path.join(data_dir, "students.csv")),
        staff=pd.read_csv(os.path.join(data_dir, "staff.csv")),
        engagement=pd.read_csv(os.path.join(data_dir, "engagement_weekly.csv")),
        belonging=pd.read_csv(os.path.join(data_dir, "belonging_pulse.csv")),
        care=pd.read_csv(os.path.join(data_dir, "care_interactions.csv")),
        outcomes=pd.read_csv(os.path.join(data_dir, "weekly_outcome.csv")),
        calendar=pd.read_csv(os.path.join(data_dir, "academic_calendar.csv")),
        departments=pd.read_csv(os.path.join(data_dir, "departments.csv")),
        service_interactions=pd.read_csv(os.path.join(data_dir, "service_interactions.csv")),
        action_plans=pd.read_csv(os.path.join(data_dir, "action_plans.csv")),
    )


def clean_all(raw):
    report = {}
    students = raw["students"].copy()
    staff = raw["staff"].copy()
    calendar = raw["calendar"].copy()
    known_students = set(students["student_id"])

    eng = raw["engagement"].copy()

    bad_attendance = eng["attendance_rate"] > 1.0
    report["engagement.attendance_over_1_capped_to_1"] = int(bad_attendance.sum())
    eng.loc[bad_attendance, "attendance_rate"] = 1.0

    neg_logins = eng["lms_logins"] < 0
    report["engagement.negative_logins_treated_as_missing"] = int(neg_logins.sum())
    eng.loc[neg_logins, "lms_logins"] = np.nan

    unknown = ~eng["student_id"].isin(known_students)
    report["engagement.rows_dropped_unknown_student"] = int(unknown.sum())
    eng = eng[~unknown].reset_index(drop=True)

    bel = raw["belonging"].copy()
    bel["survey_submitted"] = bel["survey_submitted"].astype(bool)
    bel["belonging_score"] = pd.to_numeric(bel["belonging_score"], errors="coerce")
    bel["peer_interaction_count"] = pd.to_numeric(bel["peer_interaction_count"], errors="coerce")

    inconsistent = bel["survey_submitted"] & bel["belonging_score"].isna()
    report["belonging.marked_submitted_but_score_missing"] = int(inconsistent.sum())

    unknown = ~bel["student_id"].isin(known_students)
    report["belonging.rows_dropped_unknown_student"] = int(unknown.sum())
    bel = bel[~unknown].reset_index(drop=True)

    care = raw["care"].copy()
    care["office_raw"] = care["office"]
    care["office"] = care["office"].apply(normalize_office)
    report["care.office_names_normalized"] = int((care["office_raw"] != care["office"]).sum())

    before = len(care)
    dedupe_cols = ["student_id", "date", "office", "interaction_type",
                   "response_status", "referral_status"]
    care = care.drop_duplicates(subset=dedupe_cols, keep="first")
    report["care.duplicate_rows_removed"] = before - len(care)

    care["handoff_owner"] = care["handoff_owner"].fillna("").astype(str).str.strip()
    care["date"] = pd.to_datetime(care["date"])
    care["week_number"] = ((care["date"] - TERM_START).dt.days // 7) + 1

    unknown = ~care["student_id"].isin(known_students)
    report["care.rows_dropped_unknown_student"] = int(unknown.sum())
    care = care[~unknown].reset_index(drop=True)

    unknown_owner = (care["handoff_owner"] != "") & (~care["handoff_owner"].isin(staff["staff_id"]))
    report["care.handoff_owner_not_in_staff_roster"] = int(unknown_owner.sum())

    outcomes = raw["outcomes"].copy()
    unknown = ~outcomes["student_id"].isin(known_students)
    report["outcomes.rows_dropped_unknown_student"] = int(unknown.sum())
    outcomes = outcomes[~unknown].reset_index(drop=True)

    # --- Baseline Audit additions (Week 1) --------------------------------
    departments = raw["departments"].copy()

    si = raw["service_interactions"].copy()

    si["department_raw"] = si["department"]
    si["department"] = si["department"].apply(normalize_department)
    report["service_interactions.department_names_normalized"] = int(
        (si["department_raw"] != si["department"]).sum())
    report["service_interactions.rows_with_unrecognized_department"] = int(
        (si["department"] == "Unknown").sum())

    si["status_raw"] = si["status"]
    si["status"] = si["status"].apply(normalize_status)
    report["service_interactions.status_values_normalized"] = int(
        (si["status_raw"] != si["status"]).sum())

    before = len(si)
    dedupe_cols = ["workflow_id", "student_id", "date_opened", "department",
                   "interaction_type", "status"]
    si = si.drop_duplicates(subset=dedupe_cols, keep="first")
    report["service_interactions.duplicate_rows_removed"] = before - len(si)

    si["assigned_owner"] = si["assigned_owner"].fillna("").astype(str).str.strip()
    report["service_interactions.rows_missing_owner"] = int((si["assigned_owner"] == "").sum())

    unknown_owner = (si["assigned_owner"] != "") & (~si["assigned_owner"].isin(staff["staff_id"]))
    report["service_interactions.owner_not_in_staff_roster"] = int(unknown_owner.sum())

    si["date_opened"] = pd.to_datetime(si["date_opened"], errors="coerce")
    si["date_closed"] = pd.to_datetime(si["date_closed"], errors="coerce")

    bad_order = si["date_closed"].notna() & (si["date_closed"] < si["date_opened"])
    report["service_interactions.date_closed_before_date_opened_treated_as_missing"] = int(bad_order.sum())
    si.loc[bad_order, "date_closed"] = pd.NaT

    unknown = ~si["student_id"].isin(known_students)
    report["service_interactions.rows_dropped_unknown_student"] = int(unknown.sum())
    si = si[~unknown].reset_index(drop=True)

    ap = raw["action_plans"].copy()

    ap["department_raw"] = ap["department"]
    ap["department"] = ap["department"].apply(normalize_department)
    report["action_plans.department_names_normalized"] = int(
        (ap["department_raw"] != ap["department"]).sum())

    unknown = ~ap["student_id"].isin(known_students)
    report["action_plans.rows_dropped_unknown_student"] = int(unknown.sum())
    ap = ap[~unknown].reset_index(drop=True)

    ap["date_created"] = pd.to_datetime(ap["date_created"], errors="coerce")
    ap["target_completion_date"] = pd.to_datetime(ap["target_completion_date"], errors="coerce")
    ap["actual_completion_date"] = pd.to_datetime(ap["actual_completion_date"], errors="coerce")

    out_of_range = (ap["completion_percentage"] < 0) | (ap["completion_percentage"] > 100)
    report["action_plans.completion_percentage_out_of_range_capped"] = int(out_of_range.sum())
    ap["completion_percentage"] = ap["completion_percentage"].clip(lower=0, upper=100)

    inconsistent = (ap["completion_status"] == "completed") & (ap["completion_percentage"] != 100)
    report["action_plans.completion_status_inconsistent_with_percentage"] = int(inconsistent.sum())

    cleaned = dict(students=students, staff=staff, engagement=eng, belonging=bel,
                   care=care, outcomes=outcomes, calendar=calendar,
                   departments=departments, service_interactions=si, action_plans=ap)
    return cleaned, report
