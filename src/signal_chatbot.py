"""
signal_chatbot.py
------------------
Signal 5: what the employee tells the support chatbot (PulseBot).

People often say more to a chatbot than to a colleague ("I can't keep up",
"I'm dreading Monday"), so the same stress-language analysis used for
messages is applied to the employee's own chatbot messages. Only messages
the employee typed are analysed (never the bot's replies), and only when
the employee has switched message analysis on.
"""

from signal_message_tone import score_employee_messages


def score_employee_chatbot(weekly_chat: list) -> dict:
    """weekly_chat: list of {week, messages}. Same shape as weekly_messages."""
    res = score_employee_messages(weekly_chat or [])
    total = sum(len(w.get("messages", [])) for w in (weekly_chat or []))
    if total == 0 or res.get("overall_tone_risk") is None:
        return {"chatbot_risk_score": None, "n_messages": 0, "confidence": "low", "trend": "stable",
                "weekly_scores": res.get("weekly_scores", [])}
    conf = "high" if total >= 4 else "medium" if total >= 2 else "low"
    return {"chatbot_risk_score": res["overall_tone_risk"], "n_messages": total, "confidence": conf,
            "trend": res["trend"], "weekly_scores": res["weekly_scores"]}
