import pandas as pd
import numpy as np

BASELINE_WEEKS = [1, 2]
RECENT_WEEKS = [6, 7]


def _relative_change(baseline, recent):
    if baseline is None or pd.isna(baseline) or baseline == 0:
        return np.nan
    return (recent - baseline) / abs(baseline)


_ENGAGEMENT_FEATURE_COLUMNS = ["student_id"]
for _col in ["attendance_rate", "lms_activity_score", "participation_score"]:
    _ENGAGEMENT_FEATURE_COLUMNS += [f"{_col}_baseline", f"{_col}_recent", f"{_col}_rel_change"]


def compute_engagement_features(engagement):
    rows = []
    for sid, g in engagement.groupby("student_id"):
        base = g[g["week_number"].isin(BASELINE_WEEKS)]
        recent = g[g["week_number"].isin(RECENT_WEEKS)]
        row = {"student_id": sid}
        for col in ["attendance_rate", "lms_activity_score", "participation_score"]:
            b = base[col].mean()
            r = recent[col].mean()
            row[f"{col}_baseline"] = b
            row[f"{col}_recent"] = r
            row[f"{col}_rel_change"] = _relative_change(b, r)
        rows.append(row)
    if not rows:
        return pd.DataFrame(columns=_ENGAGEMENT_FEATURE_COLUMNS)
    return pd.DataFrame(rows)


def compute_belonging_features(belonging):
    rows = []
    for sid, g in belonging.groupby("student_id"):
        base = g[g["week_number"].isin(BASELINE_WEEKS) & g["survey_submitted"]]
        recent = g[g["week_number"].isin(RECENT_WEEKS) & g["survey_submitted"]]
        row = {"student_id": sid}

        if len(base) >= 1 and len(recent) >= 1:
            b = base["belonging_score"].mean()
            r = recent["belonging_score"].mean()
            row["belonging_score_baseline"] = b
            row["belonging_score_recent"] = r
            row["belonging_score_rel_change"] = _relative_change(b, r)
            row["belonging_data_status"] = "sufficient"
        else:
            row["belonging_score_baseline"] = np.nan
            row["belonging_score_recent"] = np.nan
            row["belonging_score_rel_change"] = np.nan
            row["belonging_data_status"] = "insufficient_data"

        bp = g[g["week_number"].isin(BASELINE_WEEKS)]["peer_interaction_count"].mean()
        rp = g[g["week_number"].isin(RECENT_WEEKS)]["peer_interaction_count"].mean()
        row["peer_interaction_rel_change"] = _relative_change(bp, rp)

        base_resp = g[g["week_number"].isin(BASELINE_WEEKS)]["survey_submitted"].mean()
        recent_resp = g[g["week_number"].isin(RECENT_WEEKS)]["survey_submitted"].mean()
        row["survey_response_rate_drop"] = (
            base_resp - recent_resp if pd.notna(base_resp) and pd.notna(recent_resp) else np.nan
        )
        rows.append(row)
    if not rows:
        return pd.DataFrame(columns=[
            "student_id", "belonging_score_baseline", "belonging_score_recent",
            "belonging_score_rel_change", "belonging_data_status",
            "peer_interaction_rel_change", "survey_response_rate_drop",
        ])
    return pd.DataFrame(rows)


def build_student_features(cleaned):
    eng_feats = compute_engagement_features(cleaned["engagement"])
    bel_feats = compute_belonging_features(cleaned["belonging"])
    features = eng_feats.merge(bel_feats, on="student_id", how="outer")
    features = features.merge(cleaned["students"][["student_id", "program", "class_year"]],
                               on="student_id", how="left")
    return features
