
import csv
import random
from datetime import date, timedelta

random.seed(42)

N_STUDENTS = 700
N_WEEKS = 7
START_DATE = date(2026, 2, 2)

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

DEPARTMENT_IDS = {
    "Counseling": "DPT01",
    "Academic Advising": "DPT02",
    "Financial Aid": "DPT03",
    "Dean of Students": "DPT04",
    "Residential Life": "DPT05",
}
DEPARTMENT_SERVICE_AREAS = {
    "Counseling": "Mental health and personal support",
    "Academic Advising": "Course planning and academic standing",
    "Financial Aid": "Billing, aid, and financial holds",
    "Dean of Students": "Conduct, crisis response, and student welfare",
    "Residential Life": "Housing and dorm-related issues",
}
DEPARTMENT_STAFF_COUNTS = {
    "Counseling": 4,
    "Academic Advising": 6,
    "Financial Aid": 3,
    "Dean of Students": 2,
    "Residential Life": 3,
}

STATUS_VARIANTS = {
    "open": ["open", "Open", "OPEN"],
    "closed": ["closed", "Closed", "closed "],
    "pending": ["pending", "Pending"],
}
SERVICE_INTERACTION_TYPES = ["referral", "handoff", "check_in"]
SOURCE_PRIORITIES = ["low", "medium", "high", "urgent"]
COHORT_BY_CLASS_YEAR = {
    "Freshman": "Fall2025",
    "Sophomore": "Fall2024",
    "Junior": "Fall2023",
    "Senior": "Fall2022",
}
UNKNOWN_STUDENT_IDS = ["S9999", "S0000"]
UNKNOWN_DEPARTMENT_NAMES = ["IT Helpdesk", "Unknown Dept"]


def weighted_choice(weights_dict):
    r = random.random()
    cum = 0.0
    for k, w in weights_dict.items():
        cum += w
        if r <= cum:
            return k
    return list(weights_dict.keys())[-1]


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def generate_staff():
    staff = []
    staff_id = 1
    counts_per_office = {
        "Counseling": 4,
        "Academic Advising": 6,
        "Financial Aid": 3,
        "Dean of Students": 2,
        "Residential Life": 3,
    }
    roles = ["Case Manager", "Advisor", "Coordinator", "Director"]
    for office, n in counts_per_office.items():
        for _ in range(n):
            staff.append({
                "staff_id": f"ST{staff_id:03d}",
                "office": office,
                "role": random.choice(roles),
            })
            staff_id += 1
    return staff


def generate_students():
    students = []
    archetypes = {}
    for i in range(1, N_STUDENTS + 1):
        sid = f"S{i:04d}"
        archetype = weighted_choice(ARCHETYPE_WEIGHTS)
        archetypes[sid] = archetype
        enrollment_status = "active"
        if archetype == "dropped_course":
            enrollment_status = "active"
        program = random.choice(PROGRAMS)
        class_year = random.choice(CLASS_YEARS)
        students.append({
            "student_id": sid,
            "cohort": COHORT_BY_CLASS_YEAR[class_year],
            "program": program,
            "class_year": class_year,
            "enrollment_status": enrollment_status,
        })
    return students, archetypes


def generate_departments():
    departments = []
    for name in CANONICAL_OFFICES:
        departments.append({
            "department_id": DEPARTMENT_IDS[name],
            "department_name": name,
            "staff_count": DEPARTMENT_STAFF_COUNTS[name],
            "service_area": DEPARTMENT_SERVICE_AREAS[name],
        })
    return departments


def generate_engagement(students, archetypes):
    rows = []
    for s in students:
        sid = s["student_id"]
        arch = archetypes[sid]

        base_attendance = clamp(random.gauss(0.88, 0.08), 0.4, 1.0)
        base_logins = max(0, int(random.gauss(14, 5)))
        base_activity = clamp(random.gauss(65, 15), 5, 100)
        base_participation = clamp(random.gauss(6.5, 1.5), 0, 10)


        if arch == "noisy_false_flag_bait":
            base_attendance = clamp(random.gauss(0.62, 0.05), 0.4, 0.75)
            base_activity = clamp(random.gauss(30, 8), 10, 45)
            base_participation = clamp(random.gauss(3.0, 1.0), 0, 5)

        for week in range(1, N_WEEKS + 1):
            drift = 0.0
            if arch == "disconnecting":
                drift = -0.06 * (week - 1)
            elif arch == "improving":
                drift = -0.04 * min(week - 1, 2) + 0.05 * max(0, week - 3)
            elif arch == "dropped_course" and week >= 4:
                drift = -0.35
            elif arch == "care_gap":
                drift = -0.015 * (week - 1)

            attendance = clamp(base_attendance + drift + random.gauss(0, 0.04), 0.0, 1.0)
            logins = max(0, int(base_logins + drift * 40 + random.gauss(0, 3)))
            activity = clamp(base_activity + drift * 80 + random.gauss(0, 6), 0, 100)
            missed = max(0, int((1 - attendance) * random.randint(3, 6)))
            participation = clamp(base_participation + drift * 8 + random.gauss(0, 0.8), 0, 10)

            if random.random() < 0.01:
                attendance = round(attendance + random.choice([0.15, 0.25]), 2)
            if random.random() < 0.005:
                logins = -abs(logins)

            rows.append({
                "student_id": sid,
                "week_number": week,
                "attendance_rate": round(attendance, 3),
                "lms_logins": logins,
                "lms_activity_score": round(activity, 1),
                "sessions_missed": missed,
                "participation_score": round(participation, 2),
            })
    return rows


def generate_belonging(students, archetypes):
    rows = []
    for s in students:
        sid = s["student_id"]
        arch = archetypes[sid]
        base_belonging = clamp(random.gauss(3.6, 0.7), 1, 5)
        base_peer = max(0, int(random.gauss(5, 2)))

        if arch == "noisy_false_flag_bait":
            base_belonging = clamp(random.gauss(2.6, 0.3), 1.5, 3.2)
            base_peer = max(0, int(random.gauss(2, 1)))

        for week in range(1, N_WEEKS + 1):
            response_prob = 0.65
            if arch == "disconnecting":
                response_prob = 0.65 - 0.05 * (week - 1)
            submitted = random.random() < clamp(response_prob, 0.15, 0.9)

            if not submitted:
                rows.append({
                    "student_id": sid, "week_number": week,
                    "survey_submitted": False,
                    "belonging_score": "", "peer_interaction_count": "",
                })
                continue

            drift = 0.0
            if arch == "disconnecting":
                drift = -0.18 * (week - 1)
            elif arch == "improving":
                drift = -0.1 * min(week - 1, 2) + 0.15 * max(0, week - 3)
            elif arch == "care_gap":
                drift = -0.05 * (week - 1)

            belonging = clamp(base_belonging + drift + random.gauss(0, 0.3), 1, 5)
            peer = max(0, int(base_peer + drift * 3 + random.gauss(0, 1)))

            rows.append({
                "student_id": sid, "week_number": week,
                "survey_submitted": True,
                "belonging_score": round(belonging, 1),
                "peer_interaction_count": peer,
            })
    return rows


def generate_care_interactions(students, archetypes, staff):
    rows = []
    interaction_id = 1
    staff_by_office = {}
    for st in staff:
        staff_by_office.setdefault(st["office"], []).append(st["staff_id"])

    for s in students:
        sid = s["student_id"]
        arch = archetypes[sid]

        n_interactions = 0
        if arch == "care_gap":
            n_interactions = random.randint(2, 4)
        elif arch == "disconnecting":
            n_interactions = random.choices([0, 1, 2], weights=[0.5, 0.35, 0.15])[0]
        elif arch == "improving":
            n_interactions = random.randint(2, 3)
        elif arch == "dropped_course":
            n_interactions = random.choices([0, 1], weights=[0.6, 0.4])[0]
        elif arch == "stable":
            n_interactions = random.choices([0, 1], weights=[0.85, 0.15])[0]
        else:
            n_interactions = random.choices([0, 1], weights=[0.7, 0.3])[0]

        for _ in range(n_interactions):
            office_canon = random.choice(CANONICAL_OFFICES)
            office_raw = random.choice(OFFICE_VARIANTS[office_canon])
            week = random.randint(1, N_WEEKS)
            interaction_date = START_DATE + timedelta(weeks=week - 1, days=random.randint(0, 4))
            itype = random.choices(
                INTERACTION_TYPES, weights=[0.4, 0.3, 0.15, 0.15]
            )[0]

            response_status = "n_a"
            referral_status = "n_a"
            handoff_owner = ""

            if itype == "outreach":
                response_status = random.choices(
                    ["responded", "no_response", "pending"], weights=[0.55, 0.3, 0.15]
                )[0]
                if arch == "care_gap" and random.random() < 0.6:
                    response_status = "no_response"

            elif itype == "referral":
                if arch == "care_gap":
                    referral_status = "open"
                elif arch == "improving":
                    referral_status = "closed"
                else:
                    referral_status = random.choices(
                        ["open", "closed"], weights=[0.3, 0.7]
                    )[0]

            elif itype == "warm_handoff":
                office_staff = staff_by_office.get(office_canon, [])
                if arch == "care_gap" and random.random() < 0.5:
                    handoff_owner = ""
                elif office_staff:
                    handoff_owner = random.choice(office_staff)

            elif itype == "staff_note":
                pass

            rows.append({
                "interaction_id": f"C{interaction_id:05d}",
                "student_id": sid,
                "date": interaction_date.isoformat(),
                "office": office_raw,
                "interaction_type": itype,
                "response_status": response_status,
                "referral_status": referral_status,
                "handoff_owner": handoff_owner,
                "note_category": random.choice(NOTE_CATEGORIES),
            })
            interaction_id += 1

    n_dupes = max(1, int(len(rows) * 0.015))
    for _ in range(n_dupes):
        dup = dict(random.choice(rows))
        dup["interaction_id"] = f"C{interaction_id:05d}"
        interaction_id += 1
        rows.append(dup)

    random.shuffle(rows)
    return rows


def generate_service_interactions(students, archetypes, staff):
    rows = []
    interaction_id = 1
    workflow_id = 1
    staff_by_office = {}
    for st in staff:
        staff_by_office.setdefault(st["office"], []).append(st["staff_id"])

    for s in students:
        sid = s["student_id"]
        arch = archetypes[sid]

        if arch == "care_gap":
            n_workflows = random.randint(2, 3)
        elif arch == "disconnecting":
            n_workflows = random.choices([0, 1, 2], weights=[0.5, 0.35, 0.15])[0]
        elif arch == "improving":
            n_workflows = random.randint(1, 2)
        elif arch == "dropped_course":
            n_workflows = random.choices([0, 1], weights=[0.6, 0.4])[0]
        elif arch == "stable":
            n_workflows = random.choices([0, 1], weights=[0.85, 0.15])[0]
        else:
            n_workflows = random.choices([0, 1], weights=[0.7, 0.3])[0]

        for _ in range(n_workflows):
            wf_id = f"WF{workflow_id:05d}"
            workflow_id += 1

            department_canon = random.choice(CANONICAL_OFFICES)
            department_raw = random.choice(OFFICE_VARIANTS[department_canon])
            n_steps = random.choices([1, 2, 3], weights=[0.55, 0.3, 0.15])[0]

            week = random.randint(1, N_WEEKS)
            open_date = START_DATE + timedelta(weeks=week - 1, days=random.randint(0, 4))

            resolved = True
            if arch == "care_gap" and random.random() < 0.65:
                resolved = False

            for step_idx in range(n_steps):
                step_date = open_date + timedelta(days=step_idx * random.randint(1, 4))

                itype = random.choices(
                    SERVICE_INTERACTION_TYPES, weights=[0.45, 0.3, 0.25]
                )[0]

                status_key = "closed" if resolved else "open"
                if not resolved and random.random() < 0.1:
                    status_key = "pending"
                status = random.choice(STATUS_VARIANTS[status_key])

                date_closed = ""
                if resolved:
                    close_lag = random.randint(1, 21)
                    close_date = step_date + timedelta(days=close_lag)
                    date_closed = close_date.isoformat()
                    if random.random() < 0.01:
                        date_closed = (step_date - timedelta(days=random.randint(1, 5))).isoformat()

                assigned_owner = ""
                office_staff = staff_by_office.get(department_canon, [])
                if not (arch == "care_gap" and random.random() < 0.5):
                    if office_staff:
                        assigned_owner = random.choice(office_staff)

                referred_to_department = ""
                referral_source = ""
                if itype == "referral":
                    referral_source = random.choice(CANONICAL_OFFICES + ["self", "faculty"])
                    if random.random() < 0.4:
                        referred_to_department = random.choice(
                            [o for o in CANONICAL_OFFICES if o != department_canon]
                        )

                student_id_field = sid
                if random.random() < 0.004:
                    student_id_field = random.choice(UNKNOWN_STUDENT_IDS)

                department_field = department_raw
                if random.random() < 0.004:
                    department_field = random.choice(UNKNOWN_DEPARTMENT_NAMES)

                rows.append({
                    "interaction_id": f"SI{interaction_id:05d}",
                    "workflow_id": wf_id,
                    "student_id": student_id_field,
                    "date_opened": step_date.isoformat(),
                    "date_closed": date_closed,
                    "department": department_field,
                    "service_category": random.choice(NOTE_CATEGORIES),
                    "interaction_type": itype,
                    "status": status,
                    "source_priority": random.choice(SOURCE_PRIORITIES),
                    "assigned_owner": assigned_owner,
                    "referral_source": referral_source,
                    "referred_to_department": referred_to_department,
                })
                interaction_id += 1

    n_dupes = max(1, int(len(rows) * 0.015))
    for _ in range(n_dupes):
        dup = dict(random.choice(rows))
        dup["interaction_id"] = f"SI{interaction_id:05d}"
        interaction_id += 1
        rows.append(dup)

    for i in range(3):
        rows[i]["student_id"] = random.choice(UNKNOWN_STUDENT_IDS)
    for i in range(3, 6):
        rows[i]["department"] = random.choice(UNKNOWN_DEPARTMENT_NAMES)

    random.shuffle(rows)
    return rows


def generate_action_plans(students, archetypes):
    rows = []
    plan_id = 1
    for s in students:
        sid = s["student_id"]
        arch = archetypes[sid]

        if arch == "care_gap":
            n_plans = random.choices([0, 1, 2], weights=[0.3, 0.4, 0.3])[0]
        elif arch in ("disconnecting", "dropped_course"):
            n_plans = random.choices([0, 1], weights=[0.6, 0.4])[0]
        elif arch == "improving":
            n_plans = random.choices([0, 1], weights=[0.4, 0.6])[0]
        else:
            n_plans = random.choices([0, 1], weights=[0.85, 0.15])[0]

        for _ in range(n_plans):
            department_canon = random.choice(CANONICAL_OFFICES)
            week = random.randint(1, N_WEEKS)
            created = START_DATE + timedelta(weeks=week - 1, days=random.randint(0, 4))
            target_days = random.randint(7, 28)
            target = created + timedelta(days=target_days)

            if arch == "care_gap":
                outcome = random.choices(
                    ["overdue", "incomplete", "partially_completed"],
                    weights=[0.45, 0.3, 0.25],
                )[0]
            elif arch == "improving":
                outcome = random.choices(
                    ["completed", "partially_completed"], weights=[0.7, 0.3]
                )[0]
            else:
                outcome = random.choices(
                    ["completed", "partially_completed", "incomplete", "overdue"],
                    weights=[0.5, 0.2, 0.15, 0.15],
                )[0]

            actual_completion_date = ""
            if outcome == "completed":
                completion_status = "completed"
                completion_percentage = 100
                lag = random.randint(0, target_days - 1) if target_days > 1 else 0
                actual_completion_date = (target - timedelta(days=lag)).isoformat()
            elif outcome == "partially_completed":
                completion_status = "partially_completed"
                completion_percentage = random.randint(20, 80)
            elif outcome == "overdue":
                completion_status = "incomplete"
                completion_percentage = random.randint(0, 60)
            else:
                completion_status = "incomplete"
                completion_percentage = random.randint(0, 40)

            if random.random() < 0.01:
                completion_percentage = random.choice([-10, 120, 150])
            if random.random() < 0.008:
                completion_status = "completed"

            rows.append({
                "plan_id": f"AP{plan_id:04d}",
                "student_id": sid,
                "department": random.choice(OFFICE_VARIANTS[department_canon]),
                "date_created": created.isoformat(),
                "target_completion_date": target.isoformat(),
                "actual_completion_date": actual_completion_date,
                "completion_status": completion_status,
                "completion_percentage": completion_percentage,
            })
            plan_id += 1

    if len(rows) >= 5:
        rows[0]["completion_percentage"] = -10
        rows[1]["completion_percentage"] = 120
        rows[2]["completion_status"] = "completed"
        rows[2]["completion_percentage"] = 55

    return rows


def generate_outcomes(students, archetypes):
    rows = []
    for s in students:
        sid = s["student_id"]
        arch = archetypes[sid]
        for week in range(1, N_WEEKS + 1):
            if arch == "stable":
                status = "no_action_needed"
            elif arch == "disconnecting":
                status = "unresolved" if week >= 4 else "no_action_needed"
            elif arch == "care_gap":
                status = "referred" if week >= 3 else "no_action_needed"
            elif arch == "improving":
                status = "improved" if week >= 5 else "referred"
            elif arch == "dropped_course":
                status = "dropped_course" if week >= 4 else "no_action_needed"
            else:
                status = "no_action_needed"
            rows.append({"student_id": sid, "week_number": week, "status": status})
    return rows


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    import os
    out_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(out_dir, exist_ok=True)

    staff = generate_staff()
    students, archetypes = generate_students()
    engagement = generate_engagement(students, archetypes)
    belonging = generate_belonging(students, archetypes)
    care = generate_care_interactions(students, archetypes, staff)
    outcomes = generate_outcomes(students, archetypes)
    calendar_rows = [{"week_number": k, "week_label": v} for k, v in CALENDAR.items()]

    departments = generate_departments()
    service_interactions = generate_service_interactions(students, archetypes, staff)
    action_plans = generate_action_plans(students, archetypes)

    write_csv(os.path.join(out_dir, "students.csv"), students,
              ["student_id", "cohort", "program", "class_year", "enrollment_status"])
    write_csv(os.path.join(out_dir, "staff.csv"), staff,
              ["staff_id", "office", "role"])
    write_csv(os.path.join(out_dir, "engagement_weekly.csv"), engagement,
              ["student_id", "week_number", "attendance_rate", "lms_logins",
               "lms_activity_score", "sessions_missed", "participation_score"])
    write_csv(os.path.join(out_dir, "belonging_pulse.csv"), belonging,
              ["student_id", "week_number", "survey_submitted",
               "belonging_score", "peer_interaction_count"])
    write_csv(os.path.join(out_dir, "care_interactions.csv"), care,
              ["interaction_id", "student_id", "date", "office", "interaction_type",
               "response_status", "referral_status", "handoff_owner", "note_category"])
    write_csv(os.path.join(out_dir, "weekly_outcome.csv"), outcomes,
              ["student_id", "week_number", "status"])
    write_csv(os.path.join(out_dir, "academic_calendar.csv"), calendar_rows,
              ["week_number", "week_label"])
    write_csv(os.path.join(out_dir, "departments.csv"), departments,
              ["department_id", "department_name", "staff_count", "service_area"])
    write_csv(os.path.join(out_dir, "service_interactions.csv"), service_interactions,
              ["interaction_id", "workflow_id", "student_id", "date_opened", "date_closed",
               "department", "service_category", "interaction_type", "status",
               "source_priority", "assigned_owner", "referral_source",
               "referred_to_department"])
    write_csv(os.path.join(out_dir, "action_plans.csv"), action_plans,
              ["plan_id", "student_id", "department", "date_created",
               "target_completion_date", "actual_completion_date",
               "completion_status", "completion_percentage"])

    gt_rows = [{"student_id": sid, "archetype": arch} for sid, arch in archetypes.items()]
    write_csv(os.path.join(out_dir, "_ground_truth_archetypes.csv"), gt_rows,
              ["student_id", "archetype"])

    print(f"Generated {len(students)} students, {len(engagement)} engagement rows, "
          f"{len(belonging)} belonging rows, {len(care)} care interactions, "
          f"{len(outcomes)} outcome rows.")
    print(f"Baseline Audit: {len(departments)} departments, "
          f"{len(service_interactions)} service interactions, "
          f"{len(action_plans)} action plans.")
    print("Archetype distribution:")
    from collections import Counter
    for k, v in Counter(archetypes.values()).items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
