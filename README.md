# HEIAXIS Early Signal Intelligence Prototype

HEIAXIS is building an infrastructure layer for campus care and student continuity, built on the belief that institutions mostly fail at executing on risk, not detecting it. This repository is a small, deliberately scoped prototype exploring two things: early signs of student disconnection, and care-continuity gaps where the institution's own handling of a case, not the student, is the signal. It uses synthetic data only, no real student, staff, or institutional data appears anywhere in this repository.

The reasoning behind every major decision, what's included, what's deliberately cut, and why, lives in the documentation below rather than being repeated here. This file is an orientation point, not the argument itself.

## Repository Structure

```
heiaxis-sprint/
├── README.md
├── requirements.txt      the only two dependencies: pandas, numpy
├── data/                 synthetic dataset (7 CSV tables)
├── src/
│   ├── generate_data.py  synthetic data generator
│   ├── cleaning.py       load, clean, validate
│   ├── features.py       baseline-relative feature engineering
│   ├── signals.py        both detectors, plus office caseload rollup
│   ├── pipeline.py       runs the full pipeline, writes output/
│   └── self_consistency_check.py
├── tests/
│   ├── test_pipeline.py  Tier 1: unit-level and boundary-condition tests
│   └── test_system.py    Tier 2: end-to-end, regression, and edge-case tests
├── output/               generated on each pipeline.py run
└── docs/
    ├── product_interpretation_memo.md
    ├── data_dictionary.md
    ├── working_prototype.md
    ├── evaluation_logic.md
    ├── testing_strategy.md
    └── architecture.md
```

## Running the Prototype

Requires Python 3.9+. Only two third-party dependencies, pinned in `requirements.txt`: pandas and numpy.

```bash
cd heiaxis-sprint

python3 -m venv venv
source venv/bin/activate     # on Windows: venv\Scripts\activate
pip install -r requirements.txt

python3 src/generate_data.py          # regenerate the synthetic dataset (already included)
python3 src/pipeline.py               # clean, engineer features, detect signals, write output/
python3 tests/test_pipeline.py        # Tier 1: unit and boundary-condition tests
python3 tests/test_system.py          # Tier 2: end-to-end, regression, and edge-case tests
python3 src/self_consistency_check.py # optional, self-consistency check against generator ground truth
```

## Where to Go for What

- **`docs/product_interpretation_memo.md`**: the actual reasoning. How the product problem is understood, what "early signal" means, what data was chosen and why, what the prototype does and doesn't prove, and what was cut. Every section shows the alternatives considered, not just the conclusion reached.
- **`docs/data_dictionary.md`**: the schema field by field, how the synthetic data was generated, and what additional data a larger-scale version could reasonably add.
- **`docs/working_prototype.md`**: what the code actually does, step by step, both required ranked outputs explained, and the confidence scale defined.
- **`docs/evaluation_logic.md`**: how usefulness would actually get tested against real data, how to avoid mistaking correlation for causation, and the open questions not yet solved.
- **`docs/testing_strategy.md`**: why the tests exist and what they actually protect, the two-tier test plan, and what real bugs the edge-case tests already caught.
- **`docs/architecture.md`**: how this fits into a real HEIAXIS system end to end, stage by stage, with the options and scaling path considered at each one.
