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


def load_raw(data_dir):
    return dict(
        students=pd.read_csv(os.path.join(data_dir, "students.csv")),
        staff=pd.read_csv(os.path.join(data_dir, "staff.csv")),
        engagement=pd.read_csv(os.path.join(data_dir, "engagement_weekly.csv")),
        belonging=pd.read_csv(os.path.join(data_dir, "belonging_pulse.csv")),
        care=pd.read_csv(os.path.join(data_dir, "care_interactions.csv")),
        outcomes=pd.read_csv(os.path.join(data_dir, "weekly_outcome.csv")),
        calendar=pd.read_csv(os.path.join(data_dir, "academic_calendar.csv")),
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

    cleaned = dict(students=students, staff=staff, engagement=eng, belonging=bel,
                   care=care, outcomes=outcomes, calendar=calendar)
    return cleaned, report
