"""
Read-only JSON API for the HEIAXIS Early Signal Intelligence prototype.

See docs/api.md for the full design reasoning, what this does and does not
solve, and the endpoint reference.

Run with:
    cd heiaxis-sprint
    python src/pipeline.py    # generate output/ first, if not already done
    python src/api.py

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
from html import escape

import pandas as pd
from flask import Flask, jsonify, request, Response

HERE = os.path.dirname(__file__)
DATA_DIR = os.path.join(HERE, "..", "data")
OUTPUT_DIR = os.path.join(HERE, "..", "output")

STUDENTS_PATH = os.path.join(DATA_DIR, "students.csv")
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
        "hint": "run `python src/pipeline.py` first to generate output/",
    }), 503


def _build_terminal_report():
    """Rebuild the same plain-text summary pipeline.py prints to the
    console, but sourced from whatever is already in output/ instead of
    re-running the pipeline. Returns None if output/ hasn't been
    generated yet.

    Returns:
        The report as a single string, or None if flagged_students.csv
        or continuity_gaps.csv is missing.
    """
    students_df = _load_csv(STUDENTS_PATH)
    flagged_df = _load_csv(FLAGGED_STUDENTS_PATH)
    gaps_df = _load_csv(CONTINUITY_GAPS_PATH)
    office_df = _load_csv(OFFICE_CASELOAD_PATH)

    if flagged_df is None or gaps_df is None:
        return None

    lines = []
    lines.append("=" * 70)
    lines.append("HEIAXIS Early Signal Intelligence -- prototype run")
    lines.append("=" * 70)

    if os.path.exists(DATA_QUALITY_REPORT_PATH):
        lines.append("\n--- Data quality report ---")
        with open(DATA_QUALITY_REPORT_PATH) as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(f"  {line}")

    n_students = len(students_df) if students_df is not None else None
    n_flagged = len(flagged_df)
    if n_students:
        lines.append(f"\n--- Output A: Students flagged for attention "
                      f"({n_flagged} of {n_students}, {n_flagged / n_students:.1%}) ---")
    else:
        lines.append(f"\n--- Output A: Students flagged for attention ({n_flagged} found) ---")
    if n_flagged:
        lines.append(flagged_df.head(10).to_string(index=False))

    n_gaps = len(gaps_df)
    lines.append(f"\n--- Output B: Care-continuity gaps ({n_gaps} found) ---")
    if n_gaps:
        by_type = gaps_df["gap_type"].value_counts()
        lines.append(by_type.to_string())
        lines.append("")
        cols = ["gap_type", "student_id", "office", "confidence", "weeks_elapsed", "leading_signal"]
        lines.append(gaps_df.head(10)[cols].to_string(index=False))

    if office_df is not None and len(office_df):
        lines.append("\n--- Office caseload context (bonus, not one of the two required outputs) ---")
        lines.append(office_df.to_string(index=False))

    lines.append(f"\nReading from {os.path.abspath(OUTPUT_DIR)}/ "
                  "(last written by pipeline.py)")
    return "\n".join(lines)


def _build_office_caseload_text():
    """Rebuild just the office caseload section of the terminal report,
    on its own, without the two required outputs alongside it.

    Returns:
        The office caseload table as a plain-text string, or None if
        office_caseload_summary.csv doesn't exist yet.
    """
    office_df = _load_csv(OFFICE_CASELOAD_PATH)
    if office_df is None or len(office_df) == 0:
        return None

    lines = ["--- Office caseload context (bonus, not one of the two required outputs) ---"]
    lines.append(office_df.to_string(index=False))
    return "\n".join(lines)


def _html_page(body_text):
    """Wrap a plain-text body in the same minimal HEIAXIS page shell used
    by the front page, a big title over a monospace <pre> block.

    Args:
        body_text: The already-built plain-text report to display.

    Returns:
        A Flask Response with mimetype text/html.
    """
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>HEIAXIS</title>
<style>
  body {{ font-family: monospace; background: #111; color: #eee; padding: 2rem; }}
  h1 {{ font-size: 3rem; margin: 0 0 1rem 0; }}
  pre {{ white-space: pre-wrap; font-size: 1rem; }}
</style>
</head>
<body>
<h1>HEIAXIS</h1>
<pre>{escape(body_text)}</pre>
</body>
</html>"""
    return Response(html, mimetype="text/html")


@app.route("/office-caseload/print")
def office_caseload_print():
    """Just the office caseload section, on its own, as a plain HTML page,
    for when the full front page at / is more than you want."""
    text = _build_office_caseload_text()
    if text is None:
        return _html_page("office_caseload_summary.csv not found. "
                           "Run `python src/pipeline.py` first.")
    return _html_page(text)


@app.route("/")
def index():
    """The front page: a big HEIAXIS title and the same plain-text summary
    pipeline.py prints to the terminal, rendered as HTML instead of JSON
    so it's readable straight in a browser. Every other route below still
    returns JSON, for anything that wants to consume this programmatically,
    see docs/api.md for the full endpoint reference."""
    report = _build_terminal_report()
    if report is None:
        return _html_page("output/ has not been generated yet. Run `python src/pipeline.py` first.")
    return _html_page(report)


@app.route("/summary")
def summary():
    """The headline numbers behind both outputs, with a plain-English
    explanation next to each one, the same information pipeline.py prints
    to the terminal, but reachable over the API instead of requiring
    someone to run the script themselves and read the console output."""
    students_df = _load_csv(STUDENTS_PATH)
    flagged_df = _load_csv(FLAGGED_STUDENTS_PATH)
    gaps_df = _load_csv(CONTINUITY_GAPS_PATH)
    office_df = _load_csv(OFFICE_CASELOAD_PATH)

    if flagged_df is None or gaps_df is None:
        return _missing_output_response("flagged_students.csv / continuity_gaps.csv")

    total_students = len(students_df) if students_df is not None else None
    n_flagged = len(flagged_df)
    flagged_pct = round(100 * n_flagged / total_students, 1) if total_students else None
    by_confidence = flagged_df["confidence"].value_counts().to_dict() if n_flagged else {}

    n_gaps = len(gaps_df)
    by_gap_type = gaps_df["gap_type"].value_counts().to_dict() if n_gaps else {}

    busiest_office = None
    if office_df is not None and len(office_df):
        top = office_df.sort_values("cases_per_staff", ascending=False).iloc[0]
        busiest_office = {
            "office": top["office"],
            "cases_per_staff": None if pd.isna(top["cases_per_staff"]) else top["cases_per_staff"],
            "explanation": "The office currently carrying the most open "
                            "cases per staff member, useful context for "
                            "reading a stale case as a capacity problem "
                            "rather than negligence.",
        }

    return jsonify({
        "description": "The headline numbers behind both required "
                        "outputs, with a plain-English explanation next "
                        "to each one. This is a read of whatever is "
                        "currently in output/, run `python src/pipeline.py` "
                        "again first if you want fresh numbers.",
        "students_flagged_for_attention": {
            "count": n_flagged,
            "total_students": total_students,
            "percent_of_students": flagged_pct,
            "by_confidence": by_confidence,
            "explanation": f"{n_flagged} of {total_students} students "
                            f"({flagged_pct}%) have at least two "
                            "independent sources declining relative to "
                            "their own early-term baseline. "
                            f"{by_confidence.get('High', 0)} of those are "
                            "High confidence (3+ sources, or 2 sources "
                            "plus peer corroboration)." if total_students else
                            "Student total unavailable, data/students.csv not found.",
        },
        "institutional_continuity_gaps": {
            "count": n_gaps,
            "by_gap_type": by_gap_type,
            "explanation": f"{n_gaps} cases were found where the "
                            "institution's own handling, not the "
                            "student's behavior, is the signal: a stale "
                            "open referral, an unanswered outreach with "
                            "no follow-up, an unowned handoff, or "
                            "uncoordinated cases across offices. See "
                            "gap_types on /continuity-gaps for what each "
                            "category means.",
        },
        "busiest_office": busiest_office,
    })


@app.route("/health")
def health():
    output_exists = os.path.isdir(OUTPUT_DIR) and os.path.exists(FLAGGED_STUDENTS_PATH)
    return jsonify({
        "status": "ok",
        "output_available": output_exists,
        "hint": None if output_exists else "run `python src/pipeline.py` first",
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
