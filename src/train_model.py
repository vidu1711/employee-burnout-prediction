"""
train_model.py
----------------
Trains a scikit-learn Random Forest Classifier to predict burnout risk
level (Low / Medium / High) from the three fused signal scores, using
the synthetic dataset's known ground-truth state as the training label.

Why a classifier on top of the rule-based fusion score at all (expected
guide question): the rule-based combined_score already works reasonably
well, but a trained classifier can learn non-linear interactions between
signals (e.g. "medium tone risk is only concerning when workload is also
escalating") that a fixed linear weighted sum cannot capture, and it
outputs calibrated class probabilities instead of just a threshold cut.
"""

import os
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
os.makedirs(MODEL_DIR, exist_ok=True)

FEATURE_COLUMNS = [
    "tone_risk_score",
    "workload_risk_score",
    "pulse_risk_score",
    "chatbot_risk_score",
    "physio_risk_score",
    "physio_hr_dev_bpm",
    "physio_gsr_dev_pct",
    "meeting_increase_pct",
    "afterhours_increase_pct",
    "missed_checkins",
    "combined_score",
]


def main():
    df = pd.read_csv(os.path.join(DATA_DIR, "features.csv"))

    # -1 means "this signal was not measured" (no device / no chatbot use)
    for col in ("chatbot_risk_score", "physio_risk_score"):
        df[col] = df[col].fillna(-1)
    for col in ("physio_hr_dev_bpm", "physio_gsr_dev_pct"):
        df[col] = df[col].fillna(0)
    other = [c for c in FEATURE_COLUMNS if c not in ("chatbot_risk_score", "physio_risk_score",
                                                      "physio_hr_dev_bpm", "physio_gsr_dev_pct")]
    df[other] = df[other].fillna(df[other].median())

    # split by EMPLOYEE so the full and core rows of one person never sit on both sides
    people = df.drop_duplicates("employee_id")[["employee_id", "true_burnout_state"]]
    train_ids, test_ids = train_test_split(people["employee_id"], test_size=0.25, random_state=42,
                                           stratify=people["true_burnout_state"])
    train = df[df["employee_id"].isin(train_ids)]
    test = df[df["employee_id"].isin(test_ids)]

    clf = RandomForestClassifier(n_estimators=200, max_depth=6, random_state=42, class_weight="balanced")
    clf.fit(train[FEATURE_COLUMNS], train["true_burnout_state"])

    for variant, label in (("core", "core signals only (no device, no chatbot)"), ("full", "all five signals")):
        t = test[test["variant"] == variant]
        pred = clf.predict(t[FEATURE_COLUMNS])
        print(f"=== Test set, {label}: {len(t)} employees ===")
        print(classification_report(t["true_burnout_state"], pred, digits=3))
        print(confusion_matrix(t["true_burnout_state"], pred, labels=["low", "medium", "high"]))
        print()

    # employees who really have device readings: does the extra signal help?
    t = test[(test["variant"] == "full") & (test["physio_risk_score"] >= 0)]
    c = test[(test["variant"] == "core") & (test["employee_id"].isin(t["employee_id"]))]
    if len(t):
        a_full = (clf.predict(t[FEATURE_COLUMNS]) == t["true_burnout_state"]).mean()
        a_core = (clf.predict(c[FEATURE_COLUMNS]) == c["true_burnout_state"]).mean()
        print(f"Same {len(t)} test employees who have device readings: core-only accuracy {a_core:.2f}, with device {a_full:.2f}")

    print("\n=== Feature importances ===")
    for feat, imp in sorted(zip(FEATURE_COLUMNS, clf.feature_importances_), key=lambda x: -x[1]):
        print(f"  {feat:30s} {imp:.3f}")

    model_path = os.path.join(MODEL_DIR, "burnout_rf_classifier.joblib")
    joblib.dump({"model": clf, "feature_columns": FEATURE_COLUMNS}, model_path)
    print(f"\nSaved model -> {model_path}")


if __name__ == "__main__":
    main()
