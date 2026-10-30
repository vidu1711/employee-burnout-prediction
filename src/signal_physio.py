"""
signal_physio.py
-----------------
Signal 4: physiological check-ins (heart rate from a MAX30102 + skin
conductance from a GSR sensor, both read by an ESP32).

The device does not decide anything. This module compares the employee's
RECENT readings with the employee's OWN baseline, because resting heart
rate and skin conductance differ a lot from person to person, and a single
reading is easily affected by caffeine, walking up stairs or excitement.

Input: a list of readings, each {"days_ago": float, "slot": str, "hr": bpm, "gsr": raw units}
Output: a 0-100 physiological-deviation score (higher = further above own baseline),
        a status (normal / elevated / high), the numbers shown on the website,
        and a confidence used by the fusion step.
"""

import statistics

RECENT_DAYS = 3.0          # readings from the last 3 days are "current"
MIN_BASELINE = 6           # readings needed (older than RECENT_DAYS) to trust a baseline
HR_UNIT = 0.20             # +20% heart rate over baseline counts as 1.0 unit of deviation
GSR_UNIT = 0.40            # +40% skin conductance over baseline counts as 1.0 unit
ELEVATED_AT = 35
HIGH_AT = 60


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


def reading_score(hr, gsr, hr_base, gsr_base):
    """0-100 score for one reading relative to the baseline."""
    hr_dev = (hr - hr_base) / max(hr_base, 40.0)
    gsr_dev = (gsr - gsr_base) / max(gsr_base, 1.0)
    raw = 0.5 * _clip(hr_dev / HR_UNIT, -1.0, 1.5) + 0.5 * _clip(gsr_dev / GSR_UNIT, -1.0, 1.5)
    score = 15 + 60 * raw if raw >= 0 else 15 + 10 * raw
    return _clip(score, 0.0, 100.0)


def status_for(score):
    if score is None:
        return None
    if score >= HIGH_AT:
        return "high"
    if score >= ELEVATED_AT:
        return "elevated"
    return "normal"


def score_employee_physio(readings: list) -> dict:
    readings = [r for r in (readings or []) if r.get("hr") and r.get("gsr") is not None]
    base = [r for r in readings if r["days_ago"] >= RECENT_DAYS]
    recent = [r for r in readings if r["days_ago"] < RECENT_DAYS]
    out = {"physio_risk_score": None, "status": None, "n_baseline": len(base), "n_recent": len(recent),
           "baseline_needed": MIN_BASELINE, "baseline_ready": len(base) >= MIN_BASELINE,
           "hr_baseline": None, "gsr_baseline": None, "hr_current": None, "gsr_current": None,
           "hr_deviation_bpm": None, "gsr_deviation_pct": None, "persistent": False,
           "confidence": "low", "elevated_readings": 0}
    if len(base) < MIN_BASELINE:
        out["note"] = "Still learning this person's normal range."
        return out
    if not recent:
        out["note"] = "No readings in the last 3 days."
        out["hr_baseline"] = round(statistics.median(r["hr"] for r in base), 1)
        out["gsr_baseline"] = round(statistics.median(r["gsr"] for r in base), 1)
        return out

    hr_b = statistics.median(r["hr"] for r in base)
    gsr_b = statistics.median(r["gsr"] for r in base)
    scores = [reading_score(r["hr"], r["gsr"], hr_b, gsr_b) for r in recent]
    overall = sum(scores) / len(scores)

    hr_now = sum(r["hr"] for r in recent) / len(recent)
    gsr_now = sum(r["gsr"] for r in recent) / len(recent)

    elevated = [(r, s) for r, s in zip(recent, scores) if s >= ELEVATED_AT]
    days_elevated = {int(r["days_ago"]) for r, _ in elevated}
    per_day = {}
    for r, s in elevated:
        per_day[int(r["days_ago"])] = per_day.get(int(r["days_ago"]), 0) + 1
    persistent = len(days_elevated) >= 2 or any(c >= 2 for c in per_day.values())

    if len(recent) >= 4 and len(base) >= 10:
        conf = "high"
    elif len(recent) >= 2:
        conf = "medium"
    else:
        conf = "low"

    out.update({
        "physio_risk_score": round(overall, 1), "status": status_for(overall),
        "hr_baseline": round(hr_b, 1), "gsr_baseline": round(gsr_b, 1),
        "hr_current": round(hr_now, 1), "gsr_current": round(gsr_now, 1),
        "hr_deviation_bpm": round(hr_now - hr_b, 1),
        "gsr_deviation_pct": round((gsr_now - gsr_b) / max(gsr_b, 1.0) * 100, 1),
        "persistent": persistent, "confidence": conf, "elevated_readings": len(elevated),
    })
    return out


if __name__ == "__main__":
    base = [{"days_ago": d + 3, "slot": "morning", "hr": 72 + (d % 3), "gsr": 420 + 10 * (d % 4)} for d in range(8)]
    recent = [{"days_ago": 0.2, "slot": "morning", "hr": 91, "gsr": 650}, {"days_ago": 1.1, "slot": "evening", "hr": 88, "gsr": 600}]
    print(score_employee_physio(base + recent))
