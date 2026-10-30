"""
pipeline.py
------------
End-to-end inference pipeline: given one employee's raw weekly data
(messages, calendar pattern, pulse-check history), runs all three signal
modules, fuses them, and produces a final burnout risk prediction using
the trained Random Forest model -- alongside the rule-based fusion score,
for transparency (so the dashboard can show HR *why* a score was given,
not just a black-box label).
"""

import os
import joblib
import pandas as pd

from signal_message_tone import score_employee_messages
from signal_workload import score_employee_workload
from signal_pulse_check import score_employee_pulse
from signal_chatbot import score_employee_chatbot
from signal_physio import score_employee_physio
from fusion import fuse_signals

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "burnout_rf_classifier.joblib")
_bundle = joblib.load(MODEL_PATH)
_model = _bundle["model"]
_feature_columns = _bundle["feature_columns"]


def predict_employee(employee: dict) -> dict:
    """
    employee: dict with keys weekly_messages, daily_meetings_per_week,
              after_hours_hours_per_week, pulse_checks (same shape as the
              synthetic dataset, minus the ground-truth label).
    """
    tone_result = score_employee_messages(employee["weekly_messages"])
    workload_result = score_employee_workload(
        employee["daily_meetings_per_week"], employee["after_hours_hours_per_week"]
    )
    pulse_result = score_employee_pulse(employee["pulse_checks"])
    chatbot_result = score_employee_chatbot(employee.get("chatbot_weekly"))
    physio_result = score_employee_physio(employee.get("physio_readings"))
    fusion_result = fuse_signals(tone_result, workload_result, pulse_result, chatbot_result, physio_result)

    features = {
        "tone_risk_score": tone_result.get("overall_tone_risk"),
        "workload_risk_score": workload_result.get("workload_risk_score"),
        "pulse_risk_score": pulse_result.get("pulse_risk_score"),
        "chatbot_risk_score": chatbot_result.get("chatbot_risk_score"),
        "physio_risk_score": physio_result.get("physio_risk_score"),
        "physio_hr_dev_bpm": physio_result.get("hr_deviation_bpm"),
        "physio_gsr_dev_pct": physio_result.get("gsr_deviation_pct"),
        "meeting_increase_pct": workload_result.get("meeting_increase_pct"),
        "afterhours_increase_pct": workload_result.get("afterhours_increase_pct"),
        "missed_checkins": pulse_result.get("missed_checkins"),
        "combined_score": fusion_result.get("combined_score"),
    }
    X = pd.DataFrame([features]).reindex(columns=_feature_columns)
    for col in ("chatbot_risk_score", "physio_risk_score"):     # -1 means "not measured"
        if col in X.columns:
            X[col] = X[col].fillna(-1)
    X = X.fillna(0)

    ml_prediction = _model.predict(X)[0]
    ml_proba = dict(zip(_model.classes_, _model.predict_proba(X)[0].round(3)))

    return {
        "employee_id": employee.get("employee_id", "unknown"),
        "signals": {
            "message_tone": tone_result,
            "workload": workload_result,
            "pulse_check": pulse_result,
            "chatbot": chatbot_result,
            "physio": physio_result,
        },
        "rule_based_fusion": fusion_result,
        "ml_prediction": {
            "predicted_risk": ml_prediction,
            "class_probabilities": ml_proba,
        },
    }


if __name__ == "__main__":
    import json
    DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "synthetic_employees.json")
    with open(DATA_PATH) as f:
        employees = json.load(f)

    # run end-to-end on a few sample employees and print a readable summary
    print(f"{'ID':8s} {'TrueState':10s} {'RuleBased':10s} {'MLPred':8s} {'Combined':9s}")
    for emp in employees[:10]:
        result = predict_employee(emp)
        print(
            f"{result['employee_id']:8s} "
            f"{emp['true_burnout_state']:10s} "
            f"{result['rule_based_fusion']['risk_level']:10s} "
            f"{result['ml_prediction']['predicted_risk']:8s} "
            f"{result['rule_based_fusion']['combined_score']:>6}"
        )

    # save one full detailed example for inspection
    sample_output = predict_employee(employees[2])
    out_path = os.path.join(os.path.dirname(__file__), "..", "outputs", "sample_prediction.json")
    with open(out_path, "w") as f:
        json.dump(sample_output, f, indent=2)
    print(f"\nFull detailed example saved -> {out_path}")
