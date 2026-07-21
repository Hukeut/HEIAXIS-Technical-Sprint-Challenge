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

Every response is self-explanatory on purpose, the same principle behind
every CSV this project produces: a caller should never have to go read a
separate document to understand what a field or a confidence level means.
List endpoints return a description of what the endpoint is, a plain-English
definition of every field in each row, and the confidence scale (or gap type
list, where relevant) actually used, alongside the data itself.
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

STUDENT_FLAG_CONFIDENCE_SCALE = {
    "High": "Three or more of the four sources declined together, or exactly "
            "two declined and peer interaction frequency also corroborates "
            "the trend.",
    "Medium": "Exactly two of the four sources declined, without peer "
              "corroboration. There is no Low tier here: fewer than two "
              "declining sources never produces a flag at all.",
}

GAP_CONFIDENCE_SCALE = {
    "High": "Four or more weeks elapsed since the gap first appeared (an "
            "unowned handoff is High once it is 2+ weeks old).",
    "Medium": "Two to three weeks elapsed.",
    "Low": "Fewer than two weeks elapsed.",
}

GAP_TYPE_DESCRIPTIONS = {
    "stale_open_referral": "A referral has been open for 3 or more weeks "
                            "with no recorded resolution.",
    "unanswered_outreach_no_escalation": "An outreach attempt went "
                                          "unanswered for 2 or more weeks, "
                                          "with no later contact of any "
                                          "kind recorded since.",
    "unowned_handoff": "A warm handoff was logged with no staff member "
                        "named as the owner, flagged regardless of how "
                        "recently it happened.",
    "uncoordinated_multi_office": "A student has concurrently active, "
                                   "unresolved cases in two or more "
                                   "offices, with no sign either office is "
                                   "aware of the other.",
}

FLAGGED_STUDENT_FIELDS = {
    "student_id": "Synthetic student identifier.",
    "flag_type": "Always 'student_disconnection_risk' on this endpoint.",
    "confidence": "High or Medium, see confidence_scale below.",
    "n_sources_declined": "How many of the four independent sources "
                           "declined relative to this student's own "
                           "early-term baseline (never fewer than 2, or "
                           "the row would not be flagged at all).",
    "leading_signal": "The single source with the steepest decline.",
    "leading_signal_change": "Relative change for the leading signal "
                              "(negative = decline, e.g. -0.38 = 38% down).",
    "reason": "Plain-language explanation of every declining source "
              "behind this flag.",
}

CONTINUITY_GAP_FIELDS = {
    "gap_type": "Which of the four gap patterns this row is, see "
                "gap_types below.",
    "student_id": "Synthetic student identifier.",
    "office": "Office (or offices, for uncoordinated_multi_office) "
              "involved.",
    "interaction_id": "The care_interactions.csv row(s) this gap traces "
                       "back to.",
    "weeks_elapsed": "How many weeks since the gap first appeared.",
    "confidence": "High, Medium, or Low, see confidence_scale below.",
    "leading_signal": "One-line summary of what was found.",
    "reason": "Plain-language explanation of what was left unresolved "
              "and for how long.",
}

OFFICE_CASELOAD_FIELDS = {
    "office": "Office name.",
    "open_cases": "Count of currently active/open cases for that office.",
    "staff_count": "Number of staff assigned to that office.",
    "cases_per_staff": "open_cases divided by staff_count, null when "
                        "staff_count is zero rather than a division error.",
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


def _envelope(description, results, fields=None, extra=None, filters_applied=None):
    """Wrap a list of results in a consistent, self-explanatory response.

    Every list endpoint returns the same shape: what this data is, what
    each field means, how many rows there are, any filters that were
    applied, and the rows themselves. The goal is that a caller never has
    to leave the response to understand what they are looking at.

    Args:
        description: One or two sentences explaining what this endpoint
            returns.
        results: The list of row dicts, already JSON-safe.
        fields: Optional dict of field name -> plain-English description.
        extra: Optional dict of additional context to merge in, e.g.
            confidence_scale or gap_types.
        filters_applied: Optional dict describing any query filters that
            were applied to produce this result set.

    Returns:
        A dict ready to pass to jsonify.
    """
    body = {
        "description": description,
        "count": len(results),
    }
    if fields is not None:
        body["fields"] = fields
    if extra:
        body.update(extra)
    body["filters_applied"] = filters_applied or {}
    body["results"] = results
    return body


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


@app.route("/")
def index():
    """A self-documenting directory of every endpoint, so hitting the bare
    root URL explains the API instead of returning an unhelpful 404."""
    return jsonify({
        "description": "Read-only JSON API in front of the HEIAXIS Early "
                        "Signal Intelligence prototype's output. See "
                        "docs/api.md for the full reference.",
        "endpoints": {
            "GET /health": "Basic status check, and whether output/ has "
                            "been generated yet.",
            "GET /students/flagged": "Students flagged for attention, "
                                      "optional ?confidence= filter.",
            "GET /students/flagged/<student_id>": "A single flagged "
                                                   "student's detail.",
            "GET /continuity-gaps": "Institutional care-continuity gaps, "
                                     "optional ?gap_type= filter.",
            "GET /office-caseload": "Bonus office caseload rollup, not "
                                     "one of the two required outputs.",
            "GET /data-quality-report": "The cleaning report from the "
                                         "last pipeline.py run.",
        },
    })


@app.route("/health")
def health():
    output_exists = os.path.isdir(OUTPUT_DIR) and os.path.exists(FLAGGED_STUDENTS_PATH)
    return jsonify({
        "status": "ok",
        "output_available": output_exists,
        "hint": None if output_exists else "run `python3 src/pipeline.py` first",
    })


@app.route("/students/flagged")
def students_flagged():
    df = _load_csv(FLAGGED_STUDENTS_PATH)
    if df is None:
        return _missing_output_response("flagged_students.csv")

    filters_applied = {}
    confidence = request.args.get("confidence")
    if confidence is not None:
        if confidence not in VALID_CONFIDENCE:
            return jsonify({
                "error": f"invalid confidence value: {confidence!r}",
                "valid_values": sorted(VALID_CONFIDENCE),
            }), 400
        df = df[df["confidence"] == confidence]
        filters_applied["confidence"] = confidence

    return jsonify(_envelope(
        description="Students flagged for attention because at least two "
                     "independent sources (attendance, LMS activity, "
                     "participation, self-reported belonging) have "
                     "declined relative to that student's own early-term "
                     "baseline. This is a rule-based result, not a model "
                     "score, see reason on each row for exactly why.",
        results=_records(df),
        fields=FLAGGED_STUDENT_FIELDS,
        extra={"confidence_scale": STUDENT_FLAG_CONFIDENCE_SCALE},
        filters_applied=filters_applied,
    ))


@app.route("/students/flagged/<student_id>")
def student_flagged_detail(student_id):
    df = _load_csv(FLAGGED_STUDENTS_PATH)
    if df is None:
        return _missing_output_response("flagged_students.csv")

    match = df[df["student_id"] == student_id]
    if len(match) == 0:
        return jsonify({
            "error": f"student {student_id!r} is not currently flagged",
            "hint": "this endpoint only returns a result for students "
                    "who are actually flagged, an absent student is not "
                    "an error in the underlying data",
        }), 404

    return jsonify({
        "description": "A single flagged student's detail, see "
                        "confidence_scale for what each confidence level "
                        "means.",
        "fields": FLAGGED_STUDENT_FIELDS,
        "confidence_scale": STUDENT_FLAG_CONFIDENCE_SCALE,
        "result": _records(match)[0],
    })


@app.route("/continuity-gaps")
def continuity_gaps():
    df = _load_csv(CONTINUITY_GAPS_PATH)
    if df is None:
        return _missing_output_response("continuity_gaps.csv")

    filters_applied = {}
    gap_type = request.args.get("gap_type")
    if gap_type is not None:
        if gap_type not in VALID_GAP_TYPES:
            return jsonify({
                "error": f"invalid gap_type value: {gap_type!r}",
                "valid_values": sorted(VALID_GAP_TYPES),
            }), 400
        df = df[df["gap_type"] == gap_type]
        filters_applied["gap_type"] = gap_type

    return jsonify(_envelope(
        description="Institutional care-continuity gaps: cases where the "
                     "institution's own handling of a case, not the "
                     "student's behavior, is the signal. See gap_types "
                     "below for what each gap_type means.",
        results=_records(df),
        fields=CONTINUITY_GAP_FIELDS,
        extra={
            "confidence_scale": GAP_CONFIDENCE_SCALE,
            "gap_types": GAP_TYPE_DESCRIPTIONS,
        },
        filters_applied=filters_applied,
    ))


@app.route("/office-caseload")
def office_caseload():
    df = _load_csv(OFFICE_CASELOAD_PATH)
    if df is None:
        return _missing_output_response("office_caseload_summary.csv")

    return jsonify(_envelope(
        description="Bonus context, not one of the two required ranked "
                     "outputs: open cases per office against staff "
                     "headcount, useful for reading a continuity gap as "
                     "a capacity problem rather than an implied "
                     "accusation against one person.",
        results=_records(df),
        fields=OFFICE_CASELOAD_FIELDS,
    ))


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

    return jsonify({
        "description": "What the cleaning step in pipeline.py found and "
                        "corrected on the last run, e.g. attendance "
                        "values capped, negative logins nulled, "
                        "duplicate rows removed. Nothing in this "
                        "prototype is corrected silently, every change "
                        "is counted here.",
        "report": report,
    })


if __name__ == "__main__":
    app.run(debug=True)
