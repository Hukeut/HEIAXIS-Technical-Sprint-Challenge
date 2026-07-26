import pandas as pd
import numpy as np

MIN_RELATIVE_DECLINE = 0.15
N_WEEKS = 7

TERM_START = pd.Timestamp("2026-02-02")
TERM_WEEKS = 7
ANALYSIS_AS_OF = TERM_START + pd.Timedelta(weeks=TERM_WEEKS)

MAX_DAYS_OPEN_BEFORE_OVERDUE = 21

MIN_DAYS_OPEN_FOR_STALE_REFERRAL = 21
MIN_DAYS_SINCE_NO_FOLLOW_UP = 14
HIGH_DELAY_DAYS = 28
MEDIUM_DELAY_DAYS = 14

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


_BOTTLENECK_COLUMNS = ["department", "open_cases", "avg_days_to_close", "median_days_to_close",
                       "overdue_cases", "unresolved_referrals", "staff_count", "cases_per_staff"]


def build_department_bottleneck_summary(service_interactions, departments, as_of=ANALYSIS_AS_OF):
    si = service_interactions
    dept_roster = departments[["department_name", "staff_count"]].rename(
        columns={"department_name": "department"})

    if len(si) == 0:
        summary = dept_roster.copy()
        for col in ["open_cases", "overdue_cases", "unresolved_referrals"]:
            summary[col] = 0
        for col in ["avg_days_to_close", "median_days_to_close"]:
            summary[col] = np.nan
        summary["cases_per_staff"] = summary.apply(
            lambda r: round(r["open_cases"] / r["staff_count"], 2) if r["staff_count"] else np.nan, axis=1)
        return summary[_BOTTLENECK_COLUMNS].reset_index(drop=True)

    si = si.copy()
    open_mask = si["status"] != "closed"
    days_open = (as_of - si["date_opened"]).dt.days
    overdue_mask = open_mask & (days_open > MAX_DAYS_OPEN_BEFORE_OVERDUE)
    referral_open_mask = open_mask & (si["interaction_type"] == "referral")

    closed = si[si["status"] == "closed"].copy()
    closed["days_to_close"] = (closed["date_closed"] - closed["date_opened"]).dt.days

    open_counts = si[open_mask].groupby("department").size().rename("open_cases")
    overdue_counts = si[overdue_mask].groupby("department").size().rename("overdue_cases")
    referral_counts = si[referral_open_mask].groupby("department").size().rename("unresolved_referrals")
    avg_close = closed.groupby("department")["days_to_close"].mean().rename("avg_days_to_close")
    median_close = closed.groupby("department")["days_to_close"].median().rename("median_days_to_close")

    summary = dept_roster.copy()
    for series in (open_counts, overdue_counts, referral_counts, avg_close, median_close):
        summary = summary.merge(series, on="department", how="left")

    for col in ["open_cases", "overdue_cases", "unresolved_referrals"]:
        summary[col] = summary[col].fillna(0).astype(int)
    summary["avg_days_to_close"] = summary["avg_days_to_close"].round(1)
    summary["median_days_to_close"] = summary["median_days_to_close"].round(1)

    summary["cases_per_staff"] = summary.apply(
        lambda r: round(r["open_cases"] / r["staff_count"], 2) if r["staff_count"] else np.nan, axis=1)

    return summary[_BOTTLENECK_COLUMNS].sort_values(
        "cases_per_staff", ascending=False).reset_index(drop=True)


def _confidence_from_days(days_elapsed):
    if days_elapsed >= HIGH_DELAY_DAYS:
        return "High"
    if days_elapsed >= MEDIUM_DELAY_DAYS:
        return "Medium"
    return "Low"


def _priority_from_risk_factors(*risk_factors):
    n = sum(1 for f in risk_factors if f)
    if n >= 3:
        return "High"
    if n >= 1:
        return "Medium"
    return "Low"


_BASELINE_GAP_COLUMNS = ["gap_type", "student_id", "workflow_id", "department",
                         "days_elapsed", "confidence", "priority",
                         "leading_signal", "reason", "evidence"]


def build_baseline_continuity_gaps(service_interactions, action_plans, department_bottleneck,
                                    as_of=ANALYSIS_AS_OF):
    si = service_interactions
    ap = action_plans
    gaps = []

    load_by_dept = dict(zip(department_bottleneck["department"], department_bottleneck["cases_per_staff"]))
    valid_loads = [v for v in load_by_dept.values() if pd.notna(v)]
    median_load = float(np.median(valid_loads)) if valid_loads else 0.0

    def _dept_under_pressure(dept_names):
        for d in dept_names:
            v = load_by_dept.get(d)
            if pd.notna(v) and v >= median_load:
                return True
        return False

    if len(si):
        referrals = si[(si["interaction_type"] == "referral") & (si["status"] != "closed")]
        for _, r in referrals.iterrows():
            days_open = (as_of - r["date_opened"]).days
            if days_open < MIN_DAYS_OPEN_FOR_STALE_REFERRAL:
                continue
            owner_missing = r["assigned_owner"] == ""
            pressured = _dept_under_pressure([r["department"]])
            gaps.append({
                "gap_type": "stale_open_referral",
                "student_id": r["student_id"],
                "workflow_id": r["workflow_id"],
                "department": r["department"],
                "days_elapsed": int(days_open),
                "confidence": _confidence_from_days(days_open),
                "priority": _priority_from_risk_factors(
                    days_open >= HIGH_DELAY_DAYS, owner_missing, pressured),
                "leading_signal": "referral open past the configured threshold",
                "reason": (f"Referral opened {int(days_open)} days ago at {r['department']} "
                           f"is still open, past the {MIN_DAYS_OPEN_FOR_STALE_REFERRAL}-day "
                           f"threshold."),
                "evidence": (f"interaction_id={r['interaction_id']}, status={r['status']}, "
                             f"owner={'none' if owner_missing else r['assigned_owner']}"),
            })

        unowned = si[(si["assigned_owner"] == "") & (si["status"] != "closed")]
        for _, r in unowned.iterrows():
            days_open = (as_of - r["date_opened"]).days
            pressured = _dept_under_pressure([r["department"]])
            gaps.append({
                "gap_type": "unowned_workflow_step",
                "student_id": r["student_id"],
                "workflow_id": r["workflow_id"],
                "department": r["department"],
                "days_elapsed": int(days_open),
                "confidence": "High" if days_open >= MEDIUM_DELAY_DAYS else "Medium",
                "priority": _priority_from_risk_factors(
                    days_open >= HIGH_DELAY_DAYS, True, pressured),
                "leading_signal": f"{r['interaction_type']} logged with no named owner",
                "reason": (f"{r['interaction_type'].replace('_', ' ').capitalize()} at "
                           f"{r['department']} has no assigned_owner -- nobody on record is "
                           f"accountable for it."),
                "evidence": (f"interaction_id={r['interaction_id']}, "
                             f"interaction_type={r['interaction_type']}, status={r['status']}"),
            })

        followable = si[si["interaction_type"].isin(["check_in", "referral"]) &
                        (si["status"] != "closed")]
        for _, r in followable.iterrows():
            days_since = (as_of - r["date_opened"]).days
            if days_since < MIN_DAYS_SINCE_NO_FOLLOW_UP:
                continue
            later = si[(si["student_id"] == r["student_id"]) &
                       (si["date_opened"] > r["date_opened"])]
            if len(later) > 0:
                continue
            owner_missing = r["assigned_owner"] == ""
            pressured = _dept_under_pressure([r["department"]])
            gaps.append({
                "gap_type": "no_later_follow_up",
                "student_id": r["student_id"],
                "workflow_id": r["workflow_id"],
                "department": r["department"],
                "days_elapsed": int(days_since),
                "confidence": _confidence_from_days(days_since),
                "priority": _priority_from_risk_factors(
                    days_since >= HIGH_DELAY_DAYS, owner_missing, pressured),
                "leading_signal": f"{r['interaction_type']} with nothing recorded after it",
                "reason": (f"{r['interaction_type'].replace('_', ' ').capitalize()} at "
                           f"{r['department']} {int(days_since)} days ago has no later "
                           f"interaction of any kind recorded for this student since."),
                "evidence": f"interaction_id={r['interaction_id']}, status={r['status']}",
            })

        active = si[si["status"] != "closed"]
        for sid, g in active.groupby("student_id"):
            depts = sorted(d for d in g["department"].unique() if d != "Unknown")
            if len(depts) < 2:
                continue
            days_elapsed = int((as_of - g["date_opened"]).dt.days.max())
            pressured = _dept_under_pressure(depts)
            owner_missing_any = bool((g["assigned_owner"] == "").any())
            gaps.append({
                "gap_type": "uncoordinated_multi_department",
                "student_id": sid,
                "workflow_id": ",".join(sorted(g["workflow_id"].unique())),
                "department": " + ".join(depts),
                "days_elapsed": days_elapsed,
                "confidence": _confidence_from_days(days_elapsed),
                "priority": _priority_from_risk_factors(
                    days_elapsed >= HIGH_DELAY_DAYS, owner_missing_any, pressured, True),
                "leading_signal": "concurrently active cases in unconnected departments",
                "reason": (f"Student has active, unresolved activity open simultaneously in "
                           f"{len(depts)} different departments ({', '.join(depts)}) with no "
                           f"indication either department is aware of the other."),
                "evidence": f"interaction_ids={','.join(g['interaction_id'].astype(str))}",
            })

    if len(ap):
        for _, r in ap.iterrows():
            is_overdue = (pd.isna(r["actual_completion_date"])
                          and pd.notna(r["target_completion_date"])
                          and r["target_completion_date"] < as_of)
            is_incomplete = r["completion_status"] == "incomplete"
            if not (is_overdue or is_incomplete):
                continue
            days_elapsed = int((as_of - r["date_created"]).days) if pd.notna(r["date_created"]) else 0
            pressured = _dept_under_pressure([r["department"]])
            gaps.append({
                "gap_type": "incomplete_or_overdue_action_plan",
                "student_id": r["student_id"],
                "workflow_id": r["plan_id"],
                "department": r["department"],
                "days_elapsed": days_elapsed,
                "confidence": "High" if is_overdue else "Medium",
                "priority": _priority_from_risk_factors(
                    is_overdue, pressured, days_elapsed >= HIGH_DELAY_DAYS),
                "leading_signal": ("action plan overdue with no completion recorded" if is_overdue
                                   else "action plan marked incomplete"),
                "reason": (
                    f"Action plan at {r['department']} passed its target completion date "
                    f"with no actual_completion_date recorded."
                    if is_overdue else
                    f"Action plan at {r['department']} is marked incomplete "
                    f"({r['completion_percentage']}% complete)."
                ),
                "evidence": (f"plan_id={r['plan_id']}, completion_status={r['completion_status']}, "
                             f"completion_percentage={r['completion_percentage']}"),
            })

    out = pd.DataFrame(gaps, columns=_BASELINE_GAP_COLUMNS)
    if len(out):
        rank = {"High": 0, "Medium": 1, "Low": 2}
        out["_rank"] = out["priority"].map(rank)
        out = (out.sort_values(["_rank", "days_elapsed"], ascending=[True, False])
                  .drop(columns="_rank").reset_index(drop=True))
    return out


_ACTION_PLAN_SUMMARY_COLUMNS = ["total_plans", "completed", "partially_completed",
                                "incomplete", "overdue", "average_completion_percentage"]


def build_action_plan_summary(action_plans, as_of=ANALYSIS_AS_OF):
    ap = action_plans
    if len(ap) == 0:
        return pd.DataFrame([{
            "total_plans": 0, "completed": 0, "partially_completed": 0,
            "incomplete": 0, "overdue": 0, "average_completion_percentage": np.nan,
        }])[_ACTION_PLAN_SUMMARY_COLUMNS]

    is_overdue = (ap["actual_completion_date"].isna()
                  & ap["target_completion_date"].notna()
                  & (ap["target_completion_date"] < as_of))

    summary = {
        "total_plans": len(ap),
        "completed": int((ap["completion_status"] == "completed").sum()),
        "partially_completed": int((ap["completion_status"] == "partially_completed").sum()),
        "incomplete": int((ap["completion_status"] == "incomplete").sum()),
        "overdue": int(is_overdue.sum()),
        "average_completion_percentage": round(float(ap["completion_percentage"].mean()), 1),
    }
    return pd.DataFrame([summary])[_ACTION_PLAN_SUMMARY_COLUMNS]


_STUDENT_REVIEW_COLUMNS = ["student_id", "departments_involved", "leading_issue",
                          "days_elapsed", "confidence", "priority", "reason"]


def build_student_review_list(baseline_gaps):
    if len(baseline_gaps) == 0:
        return pd.DataFrame(columns=_STUDENT_REVIEW_COLUMNS)

    rank = {"High": 0, "Medium": 1, "Low": 2}
    gaps = baseline_gaps.copy()
    gaps["_priority_rank"] = gaps["priority"].map(rank)
    gaps["_confidence_rank"] = gaps["confidence"].map(rank)

    rows = []
    for sid, g in gaps.groupby("student_id"):
        depts = set()
        for val in g["department"]:
            for d in str(val).split("+"):
                d = d.strip()
                if d:
                    depts.add(d)

        leading = g.sort_values(
            ["_priority_rank", "_confidence_rank", "days_elapsed"],
            ascending=[True, True, False]
        ).iloc[0]

        rows.append({
            "student_id": sid,
            "departments_involved": " + ".join(sorted(depts)),
            "leading_issue": leading["gap_type"],
            "days_elapsed": int(leading["days_elapsed"]),
            "confidence": leading["confidence"],
            "priority": leading["priority"],
            "reason": leading["reason"],
        })

    out = pd.DataFrame(rows, columns=_STUDENT_REVIEW_COLUMNS)
    out["_priority_rank"] = out["priority"].map(rank)
    out["_confidence_rank"] = out["confidence"].map(rank)
    out = (out.sort_values(["_priority_rank", "_confidence_rank", "days_elapsed"],
                            ascending=[True, True, False])
              .drop(columns=["_priority_rank", "_confidence_rank"])
              .reset_index(drop=True))
    return out
