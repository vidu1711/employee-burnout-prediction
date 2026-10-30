"""
signal_pulse_check.py
-----------------------
Signal 3: Self-reported weekly pulse-check (chatbot check-in).

Each week the employee answers a simple one-tap mood prompt from the
Teams bot: great / good / okay / stressed / overwhelmed, mapped to a
1-5 wellbeing value (5 = great, 1 = overwhelmed). Missed check-ins are
tracked separately, since consistently skipping check-ins is itself a
mild signal (disengagement) but should not be treated the same as an
active "overwhelmed" response.

Output: a 0-100 "pulse risk" score, higher = more self-reported distress.
"""

import numpy as np

VALUE_MAP = {"great": 5, "good": 4, "okay": 3, "stressed": 2, "overwhelmed": 1}


def score_employee_pulse(pulse_checks: list) -> dict:
    """
    pulse_checks: list of {week, missed, label, value}
    """
    answered = [p for p in pulse_checks if not p["missed"]]
    missed_count = len(pulse_checks) - len(answered)
    missed_rate = missed_count / len(pulse_checks) if pulse_checks else 0

    if not answered:
        # no data at all -> treat as moderate-uncertain risk, flagged separately
        return {
            "pulse_risk_score": 50.0,
            "avg_wellbeing_value": None,
            "missed_checkins": missed_count,
            "missed_rate": round(missed_rate, 2),
            "confidence": "low",
            "note": "No pulse-check responses available; score is a neutral placeholder.",
        }

    values = [p["value"] for p in answered]
    avg_value = float(np.mean(values))  # 1 (worst) .. 5 (best)

    # map 1..5 -> 100..0 risk
    base_risk = (5 - avg_value) / 4 * 100

    # recent weeks weighted more heavily than early weeks
    if len(values) >= 2:
        recent_avg = float(np.mean(values[-2:]))
        recent_risk = (5 - recent_avg) / 4 * 100
        pulse_risk_score = round(0.4 * base_risk + 0.6 * recent_risk, 1)
    else:
        pulse_risk_score = round(base_risk, 1)

    # small penalty for high missed-checkin rate (mild disengagement signal)
    missed_penalty = min(15, missed_rate * 30)
    pulse_risk_score = min(100, pulse_risk_score + missed_penalty)

    confidence = "high" if missed_rate < 0.25 else "medium" if missed_rate < 0.5 else "low"

    return {
        "pulse_risk_score": round(pulse_risk_score, 1),
        "avg_wellbeing_value": round(avg_value, 2),
        "missed_checkins": missed_count,
        "missed_rate": round(missed_rate, 2),
        "confidence": confidence,
    }


if __name__ == "__main__":
    sample = [
        {"week": 1, "missed": False, "label": "good", "value": 4},
        {"week": 2, "missed": False, "label": "okay", "value": 3},
        {"week": 3, "missed": True, "label": None, "value": None},
        {"week": 4, "missed": False, "label": "overwhelmed", "value": 1},
    ]
    print(score_employee_pulse(sample))
