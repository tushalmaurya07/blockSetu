# BlockSetu — XGBoost + SHAP + OR-Tools CP-SAT

This is the upgraded SIH 2026 prototype requested for BlockSetu.

## Architecture

Browser UI
  ↓
FastAPI
  ├── XGBoost → priority classification
  ├── SHAP → per-demand explanation
  └── OR-Tools CP-SAT → joint block optimisation
          ↓
      recommended block window + bundled jobs

## Real ML / optimisation

### 1. XGBoost
A multiclass XGBClassifier is trained from the 600 supplied railway block-demand records.

Target:
`priority_tier`

Features:
- asset_age_years
- asset_lifecycle_exhaustion_pct
- section_annual_gmt
- days_since_last_maintenance
- existing_speed_restriction_kmph
- duration_requested_min
- min_acceptable_duration_min
- crew_count_required
- is_track_machine_involved
- is_power_isolation_required
- adjacent_line_caution_required
- derailment_risk_factor
- traffic_impact_factor

`ai_priority_score` and `priority_tier` are excluded from input features to avoid direct target leakage.

### 2. SHAP
SHAP TreeExplainer generates feature-level explanations for each prediction.

The UI displays the largest positive/negative feature contributions.

### 3. OR-Tools CP-SAT
The planner selects exactly one compatible traffic window and bundles compatible jobs.

Prototype constraints include:
- exactly one candidate window
- target demand must be scheduled
- job duration must fit the chosen window
- selected jobs must be compatible with the selected window
- total bundled duration cannot exceed window duration

The objective rewards maintenance priority and ideal windows while penalising expected train-delay cost.

In a production railway deployment, additional hard safety, crew, machine, possession, signalling, OHE and operational constraints must be added and validated by domain experts.

## Run

Windows:
1. Open a terminal in this folder.
2. Run `run.bat`.

Or manually:

```bash
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Open:
`http://127.0.0.1:8000`

Do not open `index.html` directly; the UI is served by FastAPI so it can call the API.

## Data

The project includes all four supplied CSV datasets:
- 600 block demands
- 300 traffic windows
- 120 joint blocks
- 350 historical execution logs

## Important

The SIH concept document describes the intended architecture as XGBoost + domain rules + SHAP for risk/priority and OR-Tools CP-SAT for the joint optimiser. This implementation turns that architecture into a working prototype with the supplied data.

The current CP-SAT model is a demonstrator and should not be presented as an operational railway safety system.


## Fixed in this version
The AI Planner demand selector is populated only after the FastAPI API has finished loading the complete demand dataset. It now shows a `Select a maintenance demand...` placeholder and handles empty/loading data safely.
