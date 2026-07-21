"""
Read-only JSON API for the HEIAXIS Early Signal Intelligence prototype.

See docs/api.md for the full design reasoning, what this does and does not
solve, and the endpoint reference.

Run with:
    cd heiaxis-sprint
    python3 src/pipeline.py    # generate output/ first, if not already done
    python3 src/api.py

In short: this serves whatever is currently sitting in output/, written by
the last pipeline.py run. It computes nothing new and never re-runs the
pipeline itself, it is purely a presentation layer in front of results that
already exist. No authentication, pagination, or deployment concerns are
solved here, see docs/api.md for why.
"""
import os

import pandas as pd
from flask import Flask, jsonify, request

HERE = os.path.dirname(__file__)
OUTPUT_DIR = os.path.join(HERE, "..", "output")

FLAGGED_STUDENTS_PATH = os.path.join(OUTPUT_DIR, "flagged_students.csv")
CONTINUITY_GAPS_PATH = os.path.join(OUTPUT_DIR, "continuity_gaps.csv")
OFFICE_CASELOAD_PATH = os.path.join(OUTPUT_DIR, "office_caseload_summary.csv")
DATA_QUALITY_REPORT_PATH = os.path.join(OUTPUT_DIR, "data_quality_report.txt")

VALID_CONFIDENCE = {"High", "Medium", "Low"}
VALID_GAP_TYPES = {
    "stale_open_referral",
    "unanswered_outreach_no_escalation",
    "unowned_handoff",
    "uncoordinated_multi_office",
}

app = Flask(__name__)


def _load_csv(path):
    """Load a CSV written by pipeline.py, or return None if it isn't there.

    Args:
        path: Absolute path to the CSV file.

    Returns:
        A pandas DataFrame, or None if the file does not exist.
    """
    if not os.path.exists(path):
        return None
    return pd.read_csv(path)


def _records(df):
    """Convert a DataFrame to a JSON-safe list of dicts.

    NaN values (e.g. cases_per_staff when a staff_count is zero) are not
    valid JSON on their own, so they are converted to None first.

    Args:
        df: A pandas DataFrame.

    Returns:
        A list of plain dicts, safe to pass to jsonify.
    """
    return df.astype(object).where(pd.notnull(df), None).to_dict(orient="records")


def _missing_output_response(filename):
    """Build the standard 503 response for a missing output file.

    Args:
        filename: The expected file name, used in the error message.

    Returns:
        A (response, status_code) tuple for Flask to return directly.
    """
    return jsonify({
        "error": f"{filename} not found in output/",
        "hint": "run `python3 src/pipeline.py` first to generate output/",
    }), 503


@app.route("/health")
def health():
    output_exists = os.path.isdir(OUTPUT_DIR) and os.path.exists(FLAGGED_STUDENTS_PATH)
    return jsonify({
        "status": "ok",
        "output_available": output_exists,
    })


@app.route("/students/flagged")
def students_flagged():
    df = _load_csv(FLAGGED_STUDENTS_PATH)
    if df is None:
        return _missing_output_response("flagged_students.csv")

    confidence = request.args.get("confidence")
    if confidence is not None:
        if confidence not in VALID_CONFIDENCE:
            return jsonify({
                "error": f"invalid confidence value: {confidence!r}",
                "valid_values": sorted(VALID_CONFIDENCE),
            }), 400
        df = df[df["confidence"] == confidence]

    return jsonify(_records(df))


@app.route("/students/flagged/<student_id>")
def student_flagged_detail(student_id):
    df = _load_csv(FLAGGED_STUDENTS_PATH)
    if df is None:
        return _missing_output_response("flagged_students.csv")

    match = df[df["student_id"] == student_id]
    if len(match) == 0:
        return jsonify({
            "error": f"student {student_id!r} is not currently flagged",
        }), 404

    return jsonify(_records(match)[0])


@app.route("/continuity-gaps")
def continuity_gaps():
    df = _load_csv(CONTINUITY_GAPS_PATH)
    if df is None:
        return _missing_output_response("continuity_gaps.csv")

    gap_type = request.args.get("gap_type")
    if gap_type is not None:
        if gap_type not in VALID_GAP_TYPES:
            return jsonify({
                "error": f"invalid gap_type value: {gap_type!r}",
                "valid_values": sorted(VALID_GAP_TYPES),
            }), 400
        df = df[df["gap_type"] == gap_type]

    return jsonify(_records(df))


@app.route("/office-caseload")
def office_caseload():
    df = _load_csv(OFFICE_CASELOAD_PATH)
    if df is None:
        return _missing_output_response("office_caseload_summary.csv")

    return jsonify(_records(df))


@app.route("/data-quality-report")
def data_quality_report():
    if not os.path.exists(DATA_QUALITY_REPORT_PATH):
        return _missing_output_response("data_quality_report.txt")

    report = {}
    with open(DATA_QUALITY_REPORT_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            report[key.strip()] = value.strip()

    return jsonify(report)


if __name__ == "__main__":
    app.run(debug=True)
