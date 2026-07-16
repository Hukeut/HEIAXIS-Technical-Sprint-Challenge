
import csv
import random
from datetime import date, timedelta

random.seed(42)

N_STUDENTS = 700
N_WEEKS = 7
START_DATE = date(2026, 2, 2)  #I chose this date but we agree it depends schools and states

PROGRAMS = ["Business", "Psychology", "Computer Science", "Biology",
            "Undeclared", "Engineering", "Sociology"]
CLASS_YEARS = ["Freshman", "Sophomore", "Junior", "Senior"]


OFFICE_VARIANTS = {
    "Counseling": ["Counseling", "counseling", "Counseling Center", "Counseling  "],
    "Academic Advising": ["Academic Advising", "academic advising", "Acad. Advising"],
    "Financial Aid": ["Financial Aid", "financial aid", "FinAid"],
    "Dean of Students": ["Dean of Students", "dean of students", "DOS"],
    "Residential Life": ["Residential Life", "residential life", "ResLife"],
}
CANONICAL_OFFICES = list(OFFICE_VARIANTS.keys())

NOTE_CATEGORIES = ["academic", "wellbeing", "financial", "behavioral", "social"]
INTERACTION_TYPES = ["outreach", "referral", "warm_handoff", "staff_note"]


CALENDAR = {
    1: "term_start",
    2: "regular",
    3: "regular",
    4: "midterms",
    5: "add_drop_deadline_passed",
    6: "regular",
    7: "pre_break_week",
}

ARCHETYPE_WEIGHTS = {
    "stable": 0.52,
    "disconnecting": 0.16,
    "care_gap": 0.13,
    "improving": 0.08,
    "dropped_course": 0.05,
    "noisy_false_flag_bait": 0.06,
}

def main():
    import os
    out_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(out_dir, exist_ok=True)
