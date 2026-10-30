"""
analysis.py -- the "AI" layer of the web app.

  * analyze_text()      reads one message and says calm / tense / stressed (+ why)
  * analyze_events()    reads a week of meetings and says light / balanced / busy / hectic (+ why)
  * predict_user()      builds the employee record from live database rows and runs
                        the real three-signal pipeline (tone + workload + mood -> fusion
                        -> trained Random Forest) from src/pipeline.py
"""

import os
import sys
import threading
from datetime import datetime, date, timedelta

from . import db

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from signal_message_tone import score_message, stress_label  # noqa: E402
from signal_physio import score_employee_physio  # noqa: E402


def _load_pipeline():
    """Import the trained pipeline; if the saved model can't be read by this
    scikit-learn version, retrain it once (takes a couple of seconds)."""
    try:
        import pipeline
        return pipeline
    except Exception as exc:  # pragma: no cover - only on version mismatch
        print(f"[pulsecheck] saved model could not be loaded ({exc}); retraining...")
        import subprocess
        for script in ("build_features.py", "train_model.py"):
            subprocess.run([sys.executable, os.path.join(SRC, script)], cwd=SRC, check=True)
        import importlib
        sys.modules.pop("pipeline", None)
        return importlib.import_module("pipeline")


_pipeline = _load_pipeline()

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MOOD_VALUES = {"great": 5, "good": 4, "okay": 3, "stressed": 2, "overwhelmed": 1}
WORK_START, WORK_END = 9 * 60, 18 * 60          # minutes from midnight


# ---------------------------------------------------------------- messages
def analyze_text(text: str) -> dict:
    r = score_message(text)
    return {
        "risk": r["risk"],
        "label": stress_label(r["risk"]),
        "cues": r["stress_cues"],
        "positive": r["positive_cues"],
    }


# ---------------------------------------------------------------- schedule
def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _mins(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def _label(score: float) -> str:
    if score < 22:
        return "light"
    if score < 45:
        return "balanced"
    if score < 65:
        return "busy"
    return "hectic"


def analyze_day(events: list) -> dict:
    """events: dicts with 'start' and 'end' (datetime). One calendar day."""
    if not events:
        return {"score": 0.0, "label": "light", "count": 0, "hours": 0.0, "back_to_back": 0,
                "longest_stretch_h": 0.0, "lunch_blocked": False, "after_hours_min": 0, "conflicts": 0}

    ev = sorted(events, key=lambda e: e["start"])
    iv = [(e["start"].hour * 60 + e["start"].minute, e["end"].hour * 60 + e["end"].minute) for e in ev]
    iv = [(s, max(e, s + 1)) for s, e in iv]

    # merge into continuous blocks (gap < 10 min counts as back-to-back)
    blocks, b2b, conflicts = [], 0, 0
    cur_s, cur_e = iv[0]
    for s, e in iv[1:]:
        if s < cur_e:
            conflicts += 1
        if s - cur_e < 10:
            if s - cur_e >= 0 or s < cur_e:
                b2b += 1
            cur_e = max(cur_e, e)
        else:
            blocks.append((cur_s, cur_e))
            cur_s, cur_e = s, e
    blocks.append((cur_s, cur_e))

    total_min = sum(e - s for s, e in blocks)
    longest = max(e - s for s, e in blocks)

    # is there a free 45-min window between 11:30 and 14:30?
    lunch_free = False
    cursor = 11 * 60 + 30
    for s, e in blocks + [(14 * 60 + 30, 14 * 60 + 30)]:
        if e <= 11 * 60 + 30:
            continue
        if min(s, 14 * 60 + 30) - cursor >= 45:
            lunch_free = True
            break
        cursor = max(cursor, e)
        if cursor >= 14 * 60 + 30:
            break
    lunch_blocked = (not lunch_free) and total_min >= 180

    after = 0
    for s, e in blocks:
        after += max(0, min(e, WORK_START) - s) + max(0, e - max(s, WORK_END))

    hours = total_min / 60
    score = (35 * _clip(hours / 6.5) + 20 * _clip(b2b / 4) + 12 * _clip(len(ev) / 8)
             + (13 if lunch_blocked else 0) + 10 * _clip(longest / 180) + 10 * _clip(after / 120)
             + min(5, 2.5 * conflicts))
    score = min(100.0, score)
    return {"score": round(score, 1), "label": _label(score), "count": len(ev), "hours": round(hours, 2),
            "back_to_back": b2b, "longest_stretch_h": round(longest / 60, 2),
            "lunch_blocked": lunch_blocked, "after_hours_min": int(after), "conflicts": conflicts}


def analyze_events(events: list, week_start: date, baseline_hours: float = None) -> dict:
    """events: dicts {'start': datetime, 'end': datetime, ...} inside [week_start, +7d)."""
    days = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        day_events = [e for e in events if e["start"].date() == d]
        a = analyze_day(day_events)
        a.update({"date": d.isoformat(), "weekday": DAY_NAMES[i]})
        days.append(a)

    weekdays, weekend = days[:5], days[5:]
    mean_wd = sum(d["score"] for d in weekdays) / 5
    peak = max(d["score"] for d in days)
    weekend_h = sum(d["hours"] for d in weekend)
    score = min(100.0, 0.55 * mean_wd + 0.45 * peak + min(15, weekend_h * 5))
    total_h = sum(d["hours"] for d in days)
    evenings = sum(1 for d in days if d["after_hours_min"] >= 30)

    reasons = []
    worst = sorted([d for d in days if d["score"] >= 45], key=lambda d: -d["score"])[:2]
    for d in worst:
        bits = [f"{d['count']} meetings", f"{d['hours']:.1f} h booked"]
        if d["back_to_back"]:
            bits.append(f"{d['back_to_back']} back-to-back")
        if d["lunch_blocked"]:
            bits.append("no lunch break")
        reasons.append(f"{d['weekday']}: " + ", ".join(bits))
    if evenings:
        reasons.append(f"{evenings} day{'s' if evenings > 1 else ''} with work outside 9-6")
    if weekend_h > 0:
        reasons.append(f"{weekend_h:.1f} h of meetings on the weekend")
    if baseline_hours and baseline_hours > 2 and total_h > baseline_hours * 1.25:
        pct = round((total_h / baseline_hours - 1) * 100)
        reasons.append(f"{total_h:.1f} h in meetings, about {pct}% more than your usual {baseline_hours:.1f} h")

    label = _label(score)
    if label == "light":
        suggestion = "Plenty of open time this week. A good moment for focused work."
    elif label == "balanced":
        suggestion = "A healthy mix of meetings and open time."
    elif worst:
        w = worst[0]
        suggestion = (f"Try moving one meeting off {w['weekday']}"
                      + (" and protecting a 45-minute lunch." if w["lunch_blocked"] else "."))
    else:
        suggestion = "Look for one meeting you can shorten or skip."

    return {"week_start": week_start.isoformat(), "score": round(score, 1), "label": label,
            "total_hours": round(total_h, 1), "meeting_count": sum(d["count"] for d in days),
            "days": days, "reasons": reasons[:4], "suggestion": suggestion}


def events_between(user_id: int, start: datetime, end: datetime) -> list:
    rows = db.rows(
        "SELECT id, group_id, title, start_ts, end_ts, kind, organizer_id FROM meetings "
        "WHERE owner_id=? AND start_ts>=? AND start_ts<? ORDER BY start_ts",
        (user_id, start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")),
    )
    for r in rows:
        r["start"], r["end"] = _mins(r["start_ts"]), _mins(r["end_ts"])
    return rows


def analyze_week(user_id: int, week_start: date) -> dict:
    ws = datetime.combine(week_start, datetime.min.time())
    evs = events_between(user_id, ws, ws + timedelta(days=7))
    past = []
    for k in range(1, 5):
        p = ws - timedelta(days=7 * k)
        pe = events_between(user_id, p, p + timedelta(days=7))
        if pe:
            past.append(sum((e["end"] - e["start"]).total_seconds() for e in pe) / 3600)
    baseline = sum(past) / len(past) if past else None
    res = analyze_events(evs, week_start, baseline)
    res["events"] = evs
    return res


# ------------------------------------------------- live pipeline prediction
NOW_FN = datetime.now          # swapped in tests
_REV: dict = {}
_CACHE: dict = {}
_LOCK = threading.Lock()


def touch(*user_ids):
    """Mark users' data as changed so their cached prediction is recomputed."""
    with _LOCK:
        for u in user_ids:
            _REV[u] = _REV.get(u, 0) + 1


def _week_starts(n=6):
    this = monday_of(NOW_FN().date())
    return [this - timedelta(days=7 * (n - 1 - i)) for i in range(n)]


def physio_readings_for(user_id: int, days: int = 28) -> list:
    """Device readings as {days_ago, slot, hr, gsr}. Empty unless the person switched body check-ins on."""
    u = db.one("SELECT physio_consent FROM users WHERE id=?", (user_id,))
    if not u or not u["physio_consent"]:
        return []
    t = NOW_FN()
    since = (t - timedelta(days=days)).isoformat(timespec="seconds")
    out = []
    for r in db.rows("SELECT slot, hr, gsr, created_at FROM physio_readings WHERE user_id=? AND created_at>=? "
                     "ORDER BY created_at", (user_id, since)):
        d = (t - datetime.fromisoformat(r["created_at"])).total_seconds() / 86400
        out.append({"days_ago": max(d, 0.0), "slot": r["slot"], "hr": r["hr"], "gsr": r["gsr"]})
    return out


def physio_summary(user_id: int) -> dict:
    """The full physiological picture (numbers included). Only the person themself may see this."""
    return score_employee_physio(physio_readings_for(user_id))


def physio_baseline_for(user_id: int):
    s = physio_summary(user_id)
    if s.get("hr_baseline") is None:
        return None
    return {"hr": s["hr_baseline"], "gsr": s["gsr_baseline"]}


def build_record(user_id: int) -> dict:
    """Shape live DB rows like the dataset the model was trained on."""
    weeks = _week_starts(6)
    user = db.one("SELECT consent, physio_consent FROM users WHERE id=?", (user_id,))
    record = {"employee_id": str(user_id), "weekly_messages": [], "daily_meetings_per_week": [],
              "after_hours_hours_per_week": [], "pulse_checks": [], "chatbot_weekly": [],
              "physio_readings": physio_readings_for(user_id)}
    for i, ws in enumerate(weeks):
        w0 = datetime.combine(ws, datetime.min.time())
        w1 = w0 + timedelta(days=7)
        a, b = w0.isoformat(timespec="seconds"), w1.isoformat(timespec="seconds")

        texts = []
        if user and user["consent"]:
            texts = [r["text"] for r in db.rows(
                "SELECT text FROM messages WHERE sender_id=? AND kind='chat' AND analyzed=1 "
                "AND created_at>=? AND created_at<? ORDER BY created_at", (user_id, a, b))]
        record["weekly_messages"].append({"week": i + 1, "messages": texts})

        bot = []
        if user and user["consent"]:          # chatbot text is analysed under the same switch as messages
            bot = [r["content"] for r in db.rows(
                "SELECT content FROM chat_messages WHERE user_id=? AND role='user' "
                "AND created_at>=? AND created_at<? ORDER BY id", (user_id, a, b))]
        record["chatbot_weekly"].append({"week": i + 1, "messages": bot})

        evs = events_between(user_id, w0, w1)
        daily = [0] * 5
        after_h = 0.0
        for e in evs:
            s_min, e_min = e["start"].hour * 60 + e["start"].minute, e["end"].hour * 60 + e["end"].minute
            out = max(0, min(e_min, WORK_START) - s_min) + max(0, e_min - max(s_min, WORK_END))
            if e["start"].weekday() >= 5:
                out = e_min - s_min
            after_h += out / 60
            if e["start"].weekday() < 5 and s_min >= WORK_START and s_min < WORK_END:
                daily[e["start"].weekday()] += 1
        record["daily_meetings_per_week"].append(daily)
        record["after_hours_hours_per_week"].append(round(after_h, 1))

        mood = db.one("SELECT label, value FROM moods WHERE user_id=? AND created_at>=? AND created_at<? "
                      "ORDER BY created_at DESC LIMIT 1", (user_id, a, b))
        record["pulse_checks"].append({"week": i + 1, "missed": mood is None,
                                       "label": mood["label"] if mood else None,
                                       "value": mood["value"] if mood else None})
    return record


def _tone_level(overall):
    if overall is None:
        return None
    return stress_label(overall)


def predict_user(user_id: int) -> dict:
    this_week = monday_of(NOW_FN().date())
    key = (_REV.get(user_id, 0), this_week)
    with _LOCK:
        hit = _CACHE.get(user_id)
        if hit and hit[0] == key:
            return hit[1]

    record = build_record(user_id)
    out = _pipeline.predict_employee(record)
    tone = out["signals"]["message_tone"]
    work = out["signals"]["workload"]
    pulse = out["signals"]["pulse_check"]
    bot = out["signals"]["chatbot"]
    body = out["signals"]["physio"]

    weeks = _week_starts(6)
    sched_weeks = []
    for ws in weeks:
        a = analyze_events(
            [e for e in events_between(user_id, datetime.combine(ws, datetime.min.time()),
                                       datetime.combine(ws, datetime.min.time()) + timedelta(days=7))],
            ws)
        sched_weeks.append({"week_start": ws.isoformat(), "label": a["label"], "score": a["score"],
                            "hours": a["total_hours"]})
    cur = analyze_week(user_id, this_week)

    tone_weeks = []
    for ws, w in zip(weeks, tone["weekly_scores"]):
        r = w["tone_risk_score"]
        tone_weeks.append({"week_start": ws.isoformat(), "risk": r,
                           "label": stress_label(r) if r is not None else None})

    latest_mood = db.one("SELECT label, created_at FROM moods WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
                         (user_id,))
    mood_weeks = [{"week_start": ws.isoformat(), "label": p["label"]} for ws, p in zip(weeks, record["pulse_checks"])]

    tone_level = _tone_level(tone["overall_tone_risk"])
    sched_recent = max(sched_weeks[-2:], key=lambda w: w["score"])["label"]
    risk = out["ml_prediction"]["predicted_risk"].capitalize()

    reasons = []
    stressed_weeks = sum(1 for w in tone_weeks if w["label"] == "stressed")
    tense_weeks = sum(1 for w in tone_weeks if w["label"] == "tense")
    if stressed_weeks:
        reasons.append(f"Messages read as stressed in {stressed_weeks} of the last 6 weeks")
    elif tense_weeks >= 2:
        reasons.append(f"Messages read as tense in {tense_weeks} of the last 6 weeks")
    elif tone_level == "calm":
        reasons.append("Message tone has been calm")
    reasons.extend(cur["reasons"][:2])
    if work["trend"] == "escalating":
        reasons.append("Meetings and after-hours work are climbing compared with their own normal")
    if latest_mood:
        days = (NOW_FN() - datetime.fromisoformat(latest_mood["created_at"])).days
        when = "today" if days == 0 else f"{days} day{'s' if days != 1 else ''} ago"
        reasons.append(f"Last check-in: {latest_mood['label'].capitalize()} ({when})")
    else:
        reasons.append("No weekly check-in yet")
    if body.get("status") in ("elevated", "high"):
        reasons.append("Body check-ins are above their own normal range" +
                       (" on more than one occasion" if body.get("persistent") else ""))
    elif body.get("status") == "normal":
        reasons.append("Body check-ins are within their normal range")
    if bot.get("chatbot_risk_score") is not None and stress_label(bot["chatbot_risk_score"]) != "calm":
        reasons.append("Recent messages to the assistant sound " + stress_label(bot["chatbot_risk_score"]))
    missed = pulse["missed_checkins"]
    if missed >= 3:
        reasons.append(f"Skipped {missed} of the last 6 weekly check-ins")

    result = {
        "user_id": user_id, "risk": risk, "score": out["rule_based_fusion"]["combined_score"],
        "probabilities": out["ml_prediction"]["class_probabilities"],
        "tone": {"level": tone_level, "overall": tone["overall_tone_risk"], "trend": tone["trend"], "weeks": tone_weeks},
        "schedule": {"level": sched_recent, "current": {k: v for k, v in cur.items() if k != "events"},
                     "weeks": sched_weeks},
        "mood": {"latest": latest_mood["label"] if latest_mood else None, "weeks": mood_weeks,
                 "missed": missed},
        "physio": {"level": body.get("status"), "persistent": bool(body.get("persistent")),
                   "ready": bool(body.get("baseline_ready")), "n_recent": body.get("n_recent", 0),
                   "score": body.get("physio_risk_score")},
        "chatbot": {"level": stress_label(bot["chatbot_risk_score"]) if bot.get("chatbot_risk_score") is not None else None,
                    "n": bot.get("n_messages", 0)},
        "reasons": reasons[:7],
    }
    with _LOCK:
        _CACHE[user_id] = (key, result)
    return result
