# Baseline Audit Data Model

How the four new Week 1 tables relate to the existing Early Signal Intelligence schema, and how the sprint brief's terms (workflow, case, referral, handoff, interaction, assignment, signal) map onto this project's tables. Written before any Week 1 code, per the planning note's Option C.

## How department relates to office

**Chosen approach:** `department` is `office` with two fields added, `department_id` and `service_area`, not a second, disconnected roster. `departments.csv` reuses the same five names already in `staff.csv` and `care_interactions.csv` (Counseling, Academic Advising, Financial Aid, Dean of Students, Residential Life), with the same staff counts. `staff.csv` itself is untouched, a staff member's `office` field is read as their department. This keeps the existing Early Signal Intelligence pipeline fully intact while giving Baseline Audit's department bottleneck summary the same underlying entity `office_caseload_summary.csv` already reports on, just with an ID and a service-area label added.

## How service_interactions relates to care_interactions

`service_interactions.csv` is a second, richer interaction log alongside `care_interactions.csv`, not a replacement for it. `care_interactions.csv` keeps powering the original two Early Signal Intelligence outputs exactly as before. `service_interactions.csv` adds the fields Baseline Audit's broader analysis needs that the original table doesn't carry: `workflow_id`, explicit `date_opened`/`date_closed` instead of one `date`, `assigned_owner` on every row instead of only handoffs, `source_priority`, and `referral_source`/`referred_to_department` for tracking cross-department activity.

## Terminology, as used in this codebase

**Workflow.** The overarching support process behind a student's need, identified by `workflow_id`. One workflow can span multiple logged interactions over time, and sometimes more than one department. It is a lightweight linking key, not a full case file, per the brief's own definition.

**Case.** Used loosely in the brief as a synonym for workflow. This schema doesn't model a separate "case" entity, a case is a workflow.

**Referral.** One specific `interaction_type` value on a `service_interactions.csv` row: a department directing a student toward another department or service. Tracked via `referred_to_department` when it crosses departments.

**Handoff.** Another `interaction_type` value: a workflow step changing which staff member owns it. Whether it's "owned" is read directly from `assigned_owner` on that row, not a separate field.

**Interaction.** Any single row in `service_interactions.csv`. One row is one logged event: one step, in one workflow, on one date.

**Assignment.** Not its own table or event type, it's the state of the `assigned_owner` field on an interaction. An interaction is "assigned" if that field is non-empty, "unassigned" if it's blank, which is itself one of the continuity-gap patterns Week 1 detects.

**Signal.** Not raw data at all. A signal is what the analysis layer produces after reading workflows, interactions, and assignments: a bottleneck, a continuity gap, an overdue action plan. Nothing in the raw tables is a signal by itself, signals are computed, not logged.

## New table schemas

**departments.csv**: `department_id`, `department_name`, `staff_count`, `service_area`. Five rows, one per existing office, reusing `staff.csv`'s staff counts.

**service_interactions.csv**: `interaction_id`, `workflow_id`, `student_id`, `date_opened`, `date_closed`, `department`, `service_category`, `interaction_type` (`referral` / `handoff` / `check_in`), `status` (`open` / `closed` / `pending`), `source_priority`, `assigned_owner`, `referral_source`, `referred_to_department`.

**action_plans.csv**: `plan_id`, `student_id`, `department`, `date_created`, `target_completion_date`, `actual_completion_date`, `completion_status`, `completion_percentage`.

**students.csv**: adds `cohort` (derived from `class_year`, e.g. `Fall2025` for a current Freshman) to the existing `student_id`, `program`, `class_year`, `enrollment_status`. Additive only, existing readers select columns by name and are unaffected.

## Deliberate messiness (per the brief's requirements)

Inconsistent department-name casing on `service_interactions.department` and `action_plans.department` (the same variant pattern already used for `care_interactions.office`), inconsistent `status` casing, missing `assigned_owner`, a small percentage of duplicate interaction rows, a small percentage of rows referencing an unknown `student_id` or an unrecognized department name, `date_closed` occasionally before `date_opened`, workflows left open with no `date_closed`, `completion_percentage` values outside 0-100, and `completion_status` occasionally disagreeing with `completion_percentage`. All of it is injected on purpose so the Week 1 cleaning and validation step has real, countable work to do, matching how `generate_data.py` already treats the original five tables.
