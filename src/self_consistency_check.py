"""
Self-consistency check -- NOT real-world validation.

I generated this synthetic data AND built the detection logic, so any
agreement between them is partly circular: I know what pattern I told
the generator to produce, which makes it easy to unconsciously build
detection logic that finds exactly that pattern. This script exists to
be transparent about that, not to claim the detectors "work."

What this actually checks: does the (independently designed) detection
logic recover something resembling the archetypes I seeded into the
data, using a ground-truth file (data/_ground_truth_archetypes.csv)
that a real prototype would never have access to.

See docs/evaluation_logic.md for how this differs from real validation,
and what would be needed to validate this against real institutional
data and real human-reviewer judgment.

In short: this script compares the detectors' output against the
generator's hidden archetypes, explicitly documented as circular and
non-validating, since the detectors and generator were built with the
same intent in mind, agreement between them can never prove real-world
usefulness, only that the logic isn't obviously broken.
"""
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

HERE = os.path.dirname(__file__)
DATA_DIR = os.path.join(HERE, "..", "data")
OUTPUT_DIR = os.path.join(HERE, "..", "output")


def main():
    gt = pd.read_csv(os.path.join(DATA_DIR, "_ground_truth_archetypes.csv"))
    flags = pd.read_csv(os.path.join(OUTPUT_DIR, "flagged_students.csv"))
    gaps = pd.read_csv(os.path.join(OUTPUT_DIR, "continuity_gaps.csv"))

    merged = gt.copy()
    merged["disconnection_flagged"] = merged["student_id"].isin(set(flags["student_id"]))
    merged["gap_flagged"] = merged["student_id"].isin(set(gaps["student_id"]))

    lines = []
    lines.append("SELF-CONSISTENCY CHECK (circular -- see docstring / evaluation_logic.md)")
    lines.append("=" * 70)
    lines.append("")
    lines.append("Student disconnection detector vs. seeded archetype:")
    t1 = merged.groupby("archetype")["disconnection_flagged"].agg(
        flagged="sum", total="count")
    t1["rate"] = (t1["flagged"] / t1["total"]).map(lambda x: f"{x:.0%}")
    lines.append(t1.to_string())
    lines.append("")
    lines.append("Continuity gap detector vs. seeded archetype:")
    t2 = merged.groupby("archetype")["gap_flagged"].agg(flagged="sum", total="count")
    t2["rate"] = (t2["flagged"] / t2["total"]).map(lambda x: f"{x:.0%}")
    lines.append(t2.to_string())
    lines.append("")
    lines.append("Read as: 'disconnecting' and 'dropped_course' archetypes should have high")
    lines.append("flag rates (that's what the detector is meant to catch). 'stable' and")
    lines.append("'noisy_false_flag_bait' should have LOW flag rates (that's the false-")
    lines.append("positive check). 'care_gap' should have a high gap_flagged rate. None of")
    lines.append("this proves the detector will work on real data -- it only proves the")
    lines.append("code does what I intended it to do on data I built to match that intent.")

    text = "\n".join(lines)
    print(text)
    with open(os.path.join(OUTPUT_DIR, "self_consistency_check.txt"), "w") as f:
        f.write(text + "\n")


if __name__ == "__main__":
    main()
