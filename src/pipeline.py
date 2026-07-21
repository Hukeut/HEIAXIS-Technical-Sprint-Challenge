"""
HEIAXIS Early Signal Intelligence -- prototype pipeline entry point.

Run:
    python3 src/pipeline.py

Loads the synthetic dataset from ../data, cleans and validates it,
builds features, runs both detectors, and writes ranked outputs to
../output/. Prints a data-quality report and a summary to the console.

In short: this is the single entry point that ties every other module
together, load, clean, engineer, detect, write, print, in that order.
"""
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from cleaning import load_raw, clean_all
from features import build_student_features
from signals import build_student_flags, build_continuity_gaps, build_office_caseload_summary

HERE = os.path.dirname(__file__)
DATA_DIR = os.path.join(HERE, "..", "data")
OUTPUT_DIR = os.path.join(HERE, "..", "output")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70)
    print("HEIAXIS Early Signal Intelligence -- prototype run")
    print("=" * 70)

    raw = load_raw(DATA_DIR)
    cleaned, report = clean_all(raw)

    print("\n--- Data quality report ---")
    for k, v in report.items():
        print(f"  {k}: {v}")

    features = build_student_features(cleaned)
    student_flags = build_student_flags(features)
    continuity_gaps = build_continuity_gaps(cleaned["care"])
    office_summary = build_office_caseload_summary(cleaned["care"], cleaned["staff"])

    student_flags.to_csv(os.path.join(OUTPUT_DIR, "flagged_students.csv"), index=False)
    continuity_gaps.to_csv(os.path.join(OUTPUT_DIR, "continuity_gaps.csv"), index=False)
    office_summary.to_csv(os.path.join(OUTPUT_DIR, "office_caseload_summary.csv"), index=False)

    with open(os.path.join(OUTPUT_DIR, "data_quality_report.txt"), "w") as f:
        for k, v in report.items():
            f.write(f"{k}: {v}\n")

    n_students = len(cleaned["students"])
    print(f"\n--- Output A: Students flagged for attention "
          f"({len(student_flags)} of {n_students}, {len(student_flags)/n_students:.1%}) ---")
    if len(student_flags):
        print(student_flags.head(10).to_string(index=False))

    print(f"\n--- Output B: Care-continuity gaps ({len(continuity_gaps)} found) ---")
    if len(continuity_gaps):
        by_type = continuity_gaps["gap_type"].value_counts()
        print(by_type.to_string())
        print()
        print(continuity_gaps.head(10)[["gap_type", "student_id", "office", "confidence",
                                          "weeks_elapsed", "leading_signal"]].to_string(index=False))

    print("\n--- Office caseload context (bonus, not one of the two required outputs) ---")
    print(office_summary.to_string(index=False))

    print(f"\nWrote outputs to {os.path.abspath(OUTPUT_DIR)}/")


if __name__ == "__main__":
    main()
