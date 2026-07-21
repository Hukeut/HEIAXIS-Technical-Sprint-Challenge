"""
Signal detection logic for the HEIAXIS Early Signal Intelligence prototype.

Deliberately rule-based and fully explainable: every flag traces back to
specific field values and thresholds, no learned model, no hidden
weights. See docs/product_interpretation_memo.md for why we chose
transparency over a fitted model given the time budget and the stakes
of this use case (a wrong flag reaches a human who may act on it).

Two independent detectors:
  1. Student disconnection risk -- requires DECLINE CO-OCCURRING across
     at least 2 of 4 independent sources, relative to the student's own
     baseline. A single noisy source is not enough to flag a person.
  2. Institutional care-continuity gaps -- the system is the signal.
     Stale open referrals, unanswered outreach with no follow-up,
     unowned handoffs, and uncoordinated multi-office cases.

In short: the student-side detector requires decline across at least
two of four independent sources before flagging anyone, a single noisy
source is never enough. The institutional-gap detector looks for four
patterns in the care data: stale open referrals, unanswered outreach
with no follow-up, unowned handoffs, and uncoordinated multi-office
cases. A third, bonus function rolls up open cases per office against
staff headcount for added context, it isn't one of the two required
ranked outputs.
"""
import pandas as pd
import numpy as np

MIN_RELATIVE_DECLINE = 0.15
N_WEEKS = 7

DECLINE_SOURCES = {
    "attendance_rate_rel_change": "attendance",
    "lms_activity_score_rel_change": "LMS activity",
    "participation_score_rel_change": "class participation",
    "belonging_score_rel_change": "self-reported belonging",
}

MIN_WEEKS_OPEN_FOR_STALE_REFERRAL = 3
MIN_WEEKS_SINCE_UNANSWERED_OUTREACH = 2


def _score_student_row(row):
    declined = []
    for col, label in DECLINE_SOURCES.items():
        val = row.get(col)
        if pd.notna(val) and val <= -MIN_RELATIVE_DECLINE:
            declined.append((label, val))

    if len(declined) < 2:
        return None

    declined.sort(key=lambda x: x[1])
    leading_signal, leading_val = declined[0]
    n = len(declined)

    peer_val = row.get("peer_interaction_rel_change")
    peer_corroborates = pd.notna(peer_val) and peer_val <= -MIN_RELATIVE_DECLINE

    if n >= 3 or (n == 2 and peer_corroborates):
        confidence = "High"
    else:
        confidence = "Medium"

    reason_bits = [f"{label} down {abs(val):.0%} vs. own early-term baseline" for label, val in declined]
    if peer_corroborates:
        reason_bits.append("peer interaction frequency also down (corroborating)")
    if row.get("belonging_data_status") == "insufficient_data":
        reason_bits.append("belonging survey response too sparse this term to include either way")

    return {
        "student_id": row["student_id"],
        "flag_type": "student_disconnection_risk",
        "confidence": confidence,
        "n_sources_declined": n,
        "leading_signal": leading_signal,
        "leading_signal_change": round(leading_val, 3),
        "reason": "; ".join(reason_bits),
    }


def build_student_flags(features):
    flags = [r for r in (_score_student_row(row) for _, row in features.iterrows()) if r]
    out = pd.DataFrame(flags)
    if len(out):
        rank = {"High": 0, "Medium": 1}
        out["_rank"] = out["confidence"].map(rank)
        out = (out.sort_values(["_rank", "n_sources_declined"], ascending=[True, False])
                  .drop(columns="_rank").reset_index(drop=True))
    return out


def _confidence_from_weeks(weeks_elapsed):
    if weeks_elapsed >= 4:
        return "High"
    if weeks_elapsed >= 2:
        return "Medium"
    return "Low"


_GAP_COLUMNS = ["gap_type", "student_id", "office", "interaction_id",
                "weeks_elapsed", "confidence", "leading_signal", "reason"]


def build_continuity_gaps(care, current_week=N_WEEKS):
    if len(care) == 0:
        return pd.DataFrame(columns=_GAP_COLUMNS)

    care = care.sort_values(["student_id", "week_number"]).reset_index(drop=True)
    gaps = []

    referrals = care[care["interaction_type"] == "referral"]
    for _, r in referrals[referrals["referral_status"] == "open"].iterrows():
        weeks_open = current_week - r["week_number"]
        if weeks_open >= MIN_WEEKS_OPEN_FOR_STALE_REFERRAL:
            gaps.append({
                "gap_type": "stale_open_referral",
                "student_id": r["student_id"],
                "office": r["office"],
                "interaction_id": r["interaction_id"],
                "weeks_elapsed": int(weeks_open),
                "confidence": _confidence_from_weeks(weeks_open),
                "leading_signal": "referral opened, no closure recorded",
                "reason": (f"Referral opened in week {int(r['week_number'])} at {r['office']} "
                           f"is still open {int(weeks_open)} weeks later with no recorded resolution."),
            })

    outreach = care[care["interaction_type"] == "outreach"]
    no_resp = outreach[outreach["response_status"] == "no_response"]
    for _, r in no_resp.iterrows():
        weeks_since = current_week - r["week_number"]
        if weeks_since < MIN_WEEKS_SINCE_UNANSWERED_OUTREACH:
            continue
        later = care[(care["student_id"] == r["student_id"]) &
                      (care["week_number"] > r["week_number"])]
        if len(later) == 0:
            gaps.append({
                "gap_type": "unanswered_outreach_no_escalation",
                "student_id": r["student_id"],
                "office": r["office"],
                "interaction_id": r["interaction_id"],
                "weeks_elapsed": int(weeks_since),
                "confidence": _confidence_from_weeks(weeks_since),
                "leading_signal": "outreach unanswered, nothing after it",
                "reason": (f"Outreach from {r['office']} in week {int(r['week_number'])} went "
                           f"unanswered, and no further contact of any kind is recorded since -- "
                           f"{int(weeks_since)} weeks of silence with no escalation."),
            })

    handoffs = care[care["interaction_type"] == "warm_handoff"]
    for _, r in handoffs[handoffs["handoff_owner"] == ""].iterrows():
        weeks_since = current_week - r["week_number"]
        gaps.append({
            "gap_type": "unowned_handoff",
            "student_id": r["student_id"],
            "office": r["office"],
            "interaction_id": r["interaction_id"],
            "weeks_elapsed": int(weeks_since),
            "confidence": "High" if weeks_since >= 2 else "Medium",
            "leading_signal": "handoff logged with no named owner",
            "reason": (f"Warm handoff at {r['office']} in week {int(r['week_number'])} "
                       f"has no owner assigned -- nobody on record is accountable for next contact."),
        })

    def _is_active(row):
        if row["interaction_type"] == "referral" and row["referral_status"] == "open":
            return True
        if row["interaction_type"] == "outreach" and row["response_status"] == "no_response":
            return True
        if row["interaction_type"] == "warm_handoff" and row["handoff_owner"] == "":
            return True
        return False

    care["_active"] = care.apply(_is_active, axis=1)
    active = care[care["_active"]]
    for sid, g in active.groupby("student_id"):
        offices = g["office"].unique()
        if len(offices) >= 2:
            max_weeks = int((current_week - g["week_number"]).max())
            gaps.append({
                "gap_type": "uncoordinated_multi_office",
                "student_id": sid,
                "office": " + ".join(sorted(offices)),
                "interaction_id": ",".join(g["interaction_id"]),
                "weeks_elapsed": max_weeks,
                "confidence": _confidence_from_weeks(max_weeks) if max_weeks >= 2 else "Medium",
                "leading_signal": "concurrently active cases in unconnected offices",
                "reason": (f"Student has active, unresolved cases open simultaneously in "
                           f"{len(offices)} different offices ({', '.join(sorted(offices))}) with "
                           f"no indication either office is aware of the other."),
            })

    out = pd.DataFrame(gaps)
    if len(out):
        rank = {"High": 0, "Medium": 1, "Low": 2}
        out["_rank"] = out["confidence"].map(rank)
        out = (out.sort_values(["_rank", "weeks_elapsed"], ascending=[True, False])
                  .drop(columns="_rank").reset_index(drop=True))
    return out


def build_office_caseload_summary(care, staff, current_week=N_WEEKS):
    def _is_active(row):
        if row["interaction_type"] == "referral" and row["referral_status"] == "open":
            return True
        if row["interaction_type"] == "warm_handoff" and row["handoff_owner"] == "":
            return True
        return False

    if len(care) == 0:
        active = care.iloc[0:0]
    else:
        active = care[care.apply(_is_active, axis=1)]
    counts = active.groupby("office").size().rename("open_cases").reset_index()
    staff_counts = staff.groupby("office").size().rename("staff_count").reset_index()
    summary = counts.merge(staff_counts, on="office", how="outer").fillna(0)
    summary["open_cases"] = summary["open_cases"].astype(int)
    summary["staff_count"] = summary["staff_count"].astype(int)
    summary["cases_per_staff"] = summary.apply(
        lambda r: round(r["open_cases"] / r["staff_count"], 2) if r["staff_count"] else np.nan, axis=1)
    return summary.sort_values("cases_per_staff", ascending=False).reset_index(drop=True)
