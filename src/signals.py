
import pandas as pd
import numpy as np

MIN_RELATIVE_DECLINE = 0.15  # 15% relative drop from own baseline
N_WEEKS = 7  # last week present in this synthetic term but of course these two can be changed if needed

DECLINE_SOURCES = {
    "attendance_rate_rel_change": "attendance",
    "lms_activity_score_rel_change": "LMS activity",
    "participation_score_rel_change": "class participation",
    "belonging_score_rel_change": "self-reported belonging",
}

MIN_WEEKS_OPEN_FOR_STALE_REFERRAL = 3
MIN_WEEKS_SINCE_UNANSWERED_OUTREACH = 2



def _score_student_row(row):
    return {}


def build_student_flags(features):
    return


def _confidence_from_weeks(weeks_elapsed):
    return


def build_continuity_gaps(care, current_week=N_WEEKS):
        return

def _is_active(row):
        return


def build_office_caseload_summary(care, staff, current_week=N_WEEKS):
    return
