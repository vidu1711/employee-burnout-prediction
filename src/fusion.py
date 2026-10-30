"""
fusion.py
----------
Combines the independent signals into one burnout risk score.

Base weights:
    message tone         : 30%
    workload / schedule  : 25%
    physiological        : 20%   (ESP32: heart rate + skin conductance vs own baseline)
    weekly mood          : 15%
    chatbot conversation : 10%

(The first version of the project used three signals at 40 / 35 / 25. The two
new signals are optional: if an employee has no device or has not used the
chatbot, the remaining weights are renormalised, so the three-signal
behaviour is the special case where only tone, workload and mood exist.)

Confidence-aware reweighting: if a signal is missing or low-confidence
(e.g. an employee skipped most pulse-checks, has too few messages, or has not
finished building a physiological baseline), its weight is redistributed
proportionally across the remaining available signals rather than silently
treating a missing signal as zero risk.
"""

BASE_WEIGHTS = {"tone": 0.30, "workload": 0.25, "physio": 0.20, "pulse": 0.15, "chatbot": 0.10}
CONF = {"high": 1.0, "medium": 0.7, "low": 0.3}


def fuse_signals(tone_result: dict, workload_result: dict, pulse_result: dict,
                 chatbot_result: dict = None, physio_result: dict = None) -> dict:
    scores, confidences = {}, {}

    if tone_result.get("overall_tone_risk") is not None:
        scores["tone"] = tone_result["overall_tone_risk"]
        confidences["tone"] = 1.0
    else:
        confidences["tone"] = 0.0

    if workload_result.get("workload_risk_score") is not None:
        scores["workload"] = workload_result["workload_risk_score"]
        confidences["workload"] = 1.0
    else:
        confidences["workload"] = 0.0

    if pulse_result.get("pulse_risk_score") is not None:
        scores["pulse"] = pulse_result["pulse_risk_score"]
        confidences["pulse"] = CONF.get(pulse_result.get("confidence", "low"), 0.3)
    else:
        confidences["pulse"] = 0.0

    if chatbot_result and chatbot_result.get("chatbot_risk_score") is not None:
        scores["chatbot"] = chatbot_result["chatbot_risk_score"]
        confidences["chatbot"] = CONF.get(chatbot_result.get("confidence", "low"), 0.3)
    else:
        confidences["chatbot"] = 0.0

    if physio_result and physio_result.get("physio_risk_score") is not None:
        scores["physio"] = physio_result["physio_risk_score"]
        confidences["physio"] = CONF.get(physio_result.get("confidence", "low"), 0.3)
    else:
        confidences["physio"] = 0.0

    effective = {k: BASE_WEIGHTS[k] * confidences.get(k, 0.0) for k in BASE_WEIGHTS if k in scores}
    total = sum(effective.values())
    if total == 0:
        return {"combined_score": None, "risk_level": "Unknown",
                "note": "Insufficient data across all signals to compute a score."}

    weights = {k: w / total for k, w in effective.items()}
    combined = round(sum(scores[k] * weights[k] for k in scores), 1)
    level = "High" if combined >= 60 else "Medium" if combined >= 35 else "Low"
    return {"combined_score": combined, "risk_level": level, "signal_scores": scores,
            "effective_weights_used": {k: round(v, 3) for k, v in weights.items()},
            "confidences": confidences}


if __name__ == "__main__":
    tone = {"overall_tone_risk": 72.0}
    work = {"workload_risk_score": 84.6}
    pulse = {"pulse_risk_score": 75.8, "confidence": "medium"}
    print(fuse_signals(tone, work, pulse))
    print(fuse_signals(tone, work, pulse, {"chatbot_risk_score": 60, "confidence": "high"},
                       {"physio_risk_score": 70, "confidence": "high"}))
