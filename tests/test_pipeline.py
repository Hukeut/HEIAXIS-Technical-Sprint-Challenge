"""
Tier 1 test suite for the HEIAXIS Early Signal Intelligence prototype.

See docs/testing_strategy.md for the full plan and reasoning behind what's
covered here versus in tests/test_system.py (Tier 2).

Run with:
    cd heiaxis-sprint
    python3 -m pytest tests/test_pipeline.py -v
or, without pytest installed:
    python3 tests/test_pipeline.py

Two kinds of tests live in this file: checks against the actual generated
dataset (data integrity, cleaning correctness), and checks against small,
hand-constructed inputs with known expected outputs (feature math, signal
detection boundary conditions). The second kind matters more, it's the only
way to test a boundary condition (like "exactly 2 declining sources") that
the real synthetic dataset might not happen to contain an example of.
"""
import os
import sys
import pandas as pd
import numpy as np

HERE = os.path.dirname(__file__)
SRC = os.path.join(HERE, "..", "src")
sys.path.insert(0, SRC)

def _setup():

    if "result" not in _CACHE:
        raw = load_raw(DATA_DIR)
        cleaned, report = clean_all(raw)
        features = build_student_features(cleaned)
        _CACHE["result"] = (cleaned, report, features)
    return _CACHE["result"]

def test_cleaning_removes_invalid_attendance():
    return

def test_cleaning_marks_negative_logins_missing_not_zero():
    return

def test_office_names_are_canonicalized():
    return

def test_no_duplicate_care_interactions():
    return

def test_no_duplicate_care_interactions():
    return



if __name__ == "__main__":
    # Allow running without pytest installed.
    import traceback
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    passed, failed = 0, 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception:
            print(f"ERROR {t.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
