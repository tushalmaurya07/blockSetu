
from pathlib import Path
from typing import Optional
import json
import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    from ortools.sat.python import cp_model
    ORTOOLS_AVAILABLE = True
except Exception:
    cp_model = None
    ORTOOLS_AVAILABLE = False

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"

DEMAND_FILE = DATA / "railway_block_demands_dataset.csv"
WINDOW_FILE = DATA / "coa_train_traffic_windows.csv"
BLOCK_FILE = DATA / "joint_possession_optimized_blocks.csv"
HISTORY_FILE = DATA / "historical_block_execution_logs.csv"

demands = pd.read_csv(DEMAND_FILE)
windows = pd.read_csv(WINDOW_FILE)
blocks = pd.read_csv(BLOCK_FILE)
history = pd.read_csv(HISTORY_FILE)

# We deliberately exclude ai_priority_score and priority_tier from model features.
# This avoids target leakage and makes the model learn from operational/risk inputs.
FEATURES = [
    "asset_age_years",
    "asset_lifecycle_exhaustion_pct",
    "section_annual_gmt",
    "days_since_last_maintenance",
    "existing_speed_restriction_kmph",
    "duration_requested_min",
    "min_acceptable_duration_min",
    "crew_count_required",
    "is_track_machine_involved",
    "is_power_isolation_required",
    "adjacent_line_caution_required",
    "derailment_risk_factor",
    "traffic_impact_factor",
]
TARGET = "priority_tier"

X = demands[FEATURES].apply(pd.to_numeric, errors="coerce")
X = X.fillna(X.median(numeric_only=True))
y_raw = demands[TARGET].astype(str)

labels = sorted(y_raw.unique().tolist())
label_to_int = {v: i for i, v in enumerate(labels)}
int_to_label = {i: v for v, i in label_to_int.items()}
y = y_raw.map(label_to_int).astype(int)

# A simple, reproducible XGBoost multiclass classifier.
model = xgb.XGBClassifier(
    n_estimators=180,
    max_depth=4,
    learning_rate=0.06,
    subsample=0.9,
    colsample_bytree=0.9,
    objective="multi:softprob",
    num_class=len(labels),
    eval_metric="mlogloss",
    random_state=42,
    n_jobs=2,
)
model.fit(X, y)

# SHAP TreeExplainer is used for per-demand explanations.
explainer = shap.TreeExplainer(model)

# Basic in-sample metric for the demo; production should use a proper held-out evaluation.
train_accuracy = float((model.predict(X).astype(int) == y.to_numpy()).mean())

app = FastAPI(title="BlockSetu AI Planning API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def clean(v):
    if isinstance(v, (np.integer,)): return int(v)
    if isinstance(v, (np.floating,)): return float(v)
    if pd.isna(v): return None
    return v

def record(df):
    return [{k: clean(v) for k, v in row.items()} for row in df.to_dict(orient="records")]

def predict_one(row: pd.Series):
    x = pd.DataFrame([{f: pd.to_numeric(row.get(f), errors="coerce") for f in FEATURES}])
    x = x.fillna(X.median(numeric_only=True))
    proba = model.predict_proba(x)[0]
    idx = int(np.argmax(proba))
    pred = int_to_label[idx]

    # SHAP output for multiclass differs by SHAP/XGBoost version.
    sv = explainer.shap_values(x)
    if isinstance(sv, list):
        vals = np.asarray(sv[idx])[0]
    else:
        arr = np.asarray(sv)
        if arr.ndim == 3:
            # Common shape: (samples, features, classes)
            vals = arr[0, :, idx]
        elif arr.ndim == 2:
            vals = arr[0]
        else:
            vals = np.zeros(len(FEATURES))

    explanation = sorted(
        [{"feature": f, "value": float(x.iloc[0][f]), "shap": float(vals[i])}
         for i, f in enumerate(FEATURES)],
        key=lambda z: abs(z["shap"]),
        reverse=True
    )

    return {
        "prediction": pred,
        "confidence": float(proba[idx]),
        "probabilities": {int_to_label[i]: float(proba[i]) for i in range(len(labels))},
        "shap": explanation[:8],
    }

class PlanRequest(BaseModel):
    demand_id: str
    min_duration_min: Optional[int] = None

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "xgboost": True,
        "shap": True,
        "ortools_cpsat": ORTOOLS_AVAILABLE,
        "demand_records": len(demands),
        "traffic_windows": len(windows),
        "joint_blocks": len(blocks),
        "history_records": len(history),
    }

@app.get("/api/summary")
def summary():
    return {
        "demand_records": len(demands),
        "traffic_windows": len(windows),
        "joint_blocks": len(blocks),
        "history_records": len(history),
        "train_accuracy_demo": train_accuracy,
        "labels": labels,
        "ortools_available": ORTOOLS_AVAILABLE,
    }

@app.get("/api/demands")
def get_demands():
    return record(demands)

@app.get("/api/windows")
def get_windows():
    return record(windows)

@app.get("/api/blocks")
def get_blocks():
    return record(blocks)

@app.get("/api/history")
def get_history():
    return record(history)

@app.get("/api/model")
def model_info():
    return {
        "algorithm": "XGBoost multiclass classifier",
        "features": FEATURES,
        "target": TARGET,
        "classes": labels,
        "n_estimators": 180,
        "max_depth": 4,
        "learning_rate": 0.06,
        "training_records": len(demands),
        "demo_training_accuracy": train_accuracy,
        "explainability": "SHAP TreeExplainer",
    }

@app.get("/api/predict/{demand_id}")
def predict(demand_id: str):
    match = demands[demands.demand_id.astype(str) == str(demand_id)]
    if match.empty:
        raise HTTPException(404, "Demand not found")
    row = match.iloc[0]
    return {
        "demand": {k: clean(v) for k, v in row.to_dict().items()},
        "model": predict_one(row),
    }

def cpsat_plan(target_row, min_duration):
    if not ORTOOLS_AVAILABLE:
        raise HTTPException(
            503,
            "OR-Tools is not installed. Run: pip install -r requirements.txt"
        )

    section = target_row["section_code"]
    tag = target_row["bundling_compatibility_tag"]

    candidate_windows = windows[
        (windows.section_code == section) &
        (pd.to_numeric(windows.window_duration_min, errors="coerce") >= min_duration)
    ].copy()

    candidate_windows = candidate_windows.sort_values(
        ["is_ideal_joint_possession_window", "expected_train_delay_penalty_inr"],
        ascending=[False, True]
    ).head(25)

    if candidate_windows.empty:
        return {"status": "NO_WINDOW", "message": "No compatible traffic window found."}

    # Target + same-section, same-compatibility-tag jobs are possible bundled jobs.
    compatible = demands[
        (demands.section_code == section) &
        (demands.bundling_compatibility_tag == tag)
    ].copy()
    compatible["duration_requested_min"] = pd.to_numeric(
        compatible["duration_requested_min"], errors="coerce"
    ).fillna(0)
    compatible["ai_priority_score"] = pd.to_numeric(
        compatible["ai_priority_score"], errors="coerce"
    ).fillna(0)
    compatible = compatible.drop_duplicates("demand_id").head(35)

    # Always include the selected target.
    if target_row["demand_id"] not in compatible.demand_id.astype(str).tolist():
        compatible = pd.concat([pd.DataFrame([target_row]), compatible], ignore_index=True)

    # Build a CP-SAT model:
    # - exactly one traffic window
    # - selected jobs require that window
    # - total job duration must fit selected window
    # - target demand is mandatory
    # - objective rewards priority and ideal windows while penalizing train-delay cost
    m = cp_model.CpModel()

    wvars = {}
    for idx in candidate_windows.index:
        wvars[idx] = m.NewBoolVar(f"window_{idx}")

    m.Add(sum(wvars.values()) == 1)

    jvars = {}
    for j, (_, r) in enumerate(compatible.iterrows()):
        jvars[j] = m.NewBoolVar(f"job_{j}")

    target_idx = next(
        (j for j, (_, r) in enumerate(compatible.iterrows())
         if str(r["demand_id"]) == str(target_row["demand_id"])), None
    )
    m.Add(jvars[target_idx] == 1)

    # Link every job to the selected window and capacity.
    # A job can be selected if the chosen window is long enough.
    for j, (_, r) in enumerate(compatible.iterrows()):
        duration = int(max(1, float(r["duration_requested_min"])))
        allowed = [idx for idx in candidate_windows.index
                   if duration <= int(candidate_windows.loc[idx, "window_duration_min"])]
        if not allowed:
            m.Add(jvars[j] == 0)
        else:
            # j <= sum(allowed windows)
            m.Add(jvars[j] <= sum(wvars[idx] for idx in allowed))

    for idx in candidate_windows.index:
        cap = int(candidate_windows.loc[idx, "window_duration_min"])
        m.Add(
            sum(
                int(max(1, float(r["duration_requested_min"]))) * jvars[j]
                for j, (_, r) in enumerate(compatible.iterrows())
                if int(max(1, float(r["duration_requested_min"]))) <= cap
            ) <= cap
        ).OnlyEnforceIf(wvars[idx])

    # Scale objective to integers.
    objective_terms = []
    for j, (_, r) in enumerate(compatible.iterrows()):
        score = int(round(float(r["ai_priority_score"]) * 100))
        objective_terms.append(score * jvars[j])

    for idx in candidate_windows.index:
        delay_penalty = int(round(
            float(candidate_windows.loc[idx, "expected_train_delay_penalty_inr"]) / 1000
        ))
        ideal_bonus = 500 if int(candidate_windows.loc[idx, "is_ideal_joint_possession_window"]) == 1 else 0
        objective_terms.append((ideal_bonus - delay_penalty) * wvars[idx])

    m.Maximize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 3.0
    solver.parameters.num_search_workers = 4
    status = solver.Solve(m)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": "NO_FEASIBLE_PLAN", "message": "CP-SAT found no feasible plan."}

    chosen_window_idx = next(idx for idx in candidate_windows.index if solver.Value(wvars[idx]))
    chosen_window = candidate_windows.loc[chosen_window_idx]

    selected_jobs = [
        {k: clean(v) for k, v in r.to_dict().items()}
        for j, (_, r) in enumerate(compatible.iterrows())
        if solver.Value(jvars[j])
    ]

    return {
        "status": "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE",
        "solver": "Google OR-Tools CP-SAT",
        "window": {k: clean(v) for k, v in chosen_window.to_dict().items()},
        "selected_jobs": selected_jobs,
        "job_count": len(selected_jobs),
        "total_requested_duration_min": sum(float(x["duration_requested_min"]) for x in selected_jobs),
        "target_prediction": predict_one(target_row),
    }

@app.post("/api/plan")
def plan(req: PlanRequest):
    match = demands[demands.demand_id.astype(str) == str(req.demand_id)]
    if match.empty:
        raise HTTPException(404, "Demand not found")
    row = match.iloc[0]
    pred = predict_one(row)
    min_duration = req.min_duration_min or int(row["min_acceptable_duration_min"])
    result = cpsat_plan(row, min_duration)
    result["model_prediction"] = pred
    return result

# Serve the HTML/CSS/JS UI from the same FastAPI server.
app.mount("/", StaticFiles(directory=str(BASE / "frontend"), html=True), name="frontend")
