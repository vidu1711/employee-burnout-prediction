"""
build_features.py
-------------------
Runs all three signal modules + fusion over every employee in the synthetic
dataset, producing a flat feature table (CSV) ready for model training.
"""

import json
import os
import pandas as pd

from signal_message_tone import score_employee_messages
from signal_workload import score_employee_workload
from signal_pulse_check import score_employee_pulse
from signal_chatbot import score_employee_chatbot
from signal_physio import score_employee_physio
from fusion import fuse_signals

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def main():
    with open(os.path.join(DATA_DIR, "synthetic_employees.json")) as f:
        employees = json.load(f)

    rows = []
    for emp in employees:
        # flatten weekly messages into a single list of message texts for tone scoring
        tone_result = score_employee_messages(emp["weekly_messages"])
        workload_result = score_employee_workload(
            emp["daily_meetings_per_week"], emp["after_hours_hours_per_week"]
        )
        pulse_result = score_employee_pulse(emp["pulse_checks"])
        chatbot_result = score_employee_chatbot(emp.get("chatbot_weekly"))
        physio_result = score_employee_physio(emp.get("physio_readings"))

        # two variants of every employee: with every signal, and "core" (only the
        # original three) so the model also learns to work when no device is used
        for variant, cb, ph in (("full", chatbot_result, physio_result), ("core", None, None)):
            fusion_result = fuse_signals(tone_result, workload_result, pulse_result, cb, ph)
            rows.append({
                "employee_id": emp["employee_id"],
                "variant": variant,
                "true_burnout_state": emp["true_burnout_state"],
                "tone_risk_score": tone_result.get("overall_tone_risk"),
                "tone_trend": tone_result.get("trend"),
                "workload_risk_score": workload_result.get("workload_risk_score"),
                "workload_trend": workload_result.get("trend"),
                "meeting_increase_pct": workload_result.get("meeting_increase_pct"),
                "afterhours_increase_pct": workload_result.get("afterhours_increase_pct"),
                "pulse_risk_score": pulse_result.get("pulse_risk_score"),
                "pulse_confidence": pulse_result.get("confidence"),
                "missed_checkins": pulse_result.get("missed_checkins"),
                "chatbot_risk_score": cb.get("chatbot_risk_score") if cb else None,
                "physio_risk_score": ph.get("physio_risk_score") if ph else None,
                "physio_hr_dev_bpm": ph.get("hr_deviation_bpm") if ph else None,
                "physio_gsr_dev_pct": ph.get("gsr_deviation_pct") if ph else None,
                "combined_score": fusion_result.get("combined_score"),
                "risk_level_rule_based": fusion_result.get("risk_level"),
            })

    df = pd.DataFrame(rows)
    out_path = os.path.join(DATA_DIR, "features.csv")
    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df)} rows -> {out_path}")
    full = df[df["variant"] == "full"]
    print("employees with physio signal:", int(full["physio_risk_score"].notna().sum()),
          "| with chatbot signal:", int(full["chatbot_risk_score"].notna().sum()))
    print(full["risk_level_rule_based"].value_counts())


if __name__ == "__main__":
    main()
