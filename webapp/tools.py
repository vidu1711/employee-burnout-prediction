"""
tools.py -- the chatbot's backend tools.

Every tool runs *as the signed-in user*: scope and role are checked here, on the
server, no matter what the model (or a prompt-injection) asks for. Tools never
return other people's message text.
"""

from datetime import datetime, date, timedelta

from . import analysis, db, services
from .nlp_dates import parse_date, hhmm

EMPLOYEE, LEAD, ADMIN = "employee", "lead", "admin"
ALL = {EMPLOYEE, LEAD, ADMIN}
MANAGERS = {LEAD, ADMIN}

RESOURCES = {
    "breathing": {"title": "Two-minute reset", "steps": [
        "Sit back and let your shoulders drop.", "Breathe in through your nose for 4 seconds.",
        "Hold for 4 seconds.", "Breathe out slowly for 6 seconds.", "Repeat for about two minutes."]},
    "sleep": {"title": "Winding down for sleep", "steps": [
        "Pick a screen-off time 30-45 minutes before bed.", "Write tomorrow's top three tasks so your mind can let go.",
        "Keep the room cool and dark.", "If you're awake after 20 minutes, get up and do something calm until you feel sleepy."]},
    "focus": {"title": "Getting focus back", "steps": [
        "Pick one task and write it on a sticky note.", "Silence notifications for 25 minutes.",
        "Work the 25, then take a real 5-minute break away from your screen.", "Repeat up to four times, then take a longer break."]},
    "boundaries": {"title": "Switching off after work", "steps": [
        "Decide a shutdown time and tell your team.", "Close the day by listing what's done and what's next.",
        "Mute work chat on your phone after hours.", "Do something physical or social to mark the end of the day."]},
    "meetings": {"title": "Taking back your calendar", "steps": [
        "Block a 45-minute lunch every day.", "Ask for an agenda; decline meetings without one.",
        "Shorten 30-minute meetings to 25 so you get breaks.", "Hold one half-day each week free for focused work."]},
    "workload_conversation": {"title": "Talking to your manager about workload", "steps": [
        "List your current tasks and roughly how long each takes.", "Say what's not sustainable, for example 'I'm working until 9pm most nights'.",
        "Ask which priorities can move, not just for more time.", "Agree on a check-in date to review how it's going."]},
    "stress": {"title": "When stress is building", "steps": [
        "Name what's weighing on you most, in one sentence.", "Do the two-minute breathing reset.",
        "Take a short walk, even five minutes helps.", "Tell one person you trust how you're doing."]},
    "support": {"title": "Talking to someone", "steps": [
        "Your manager or HR can help rebalance your workload.", "If your company has an employee assistance programme, it's confidential.",
        "In India, Tele-MANAS offers free, 24x7 mental-health support on 14416 or 1-800-891-4416.",
        "If you're in immediate danger, call your local emergency number."]},
}
TOPIC_ALIASES = {"relax": "breathing", "calm": "breathing", "anxiety": "breathing", "insomnia": "sleep",
                 "concentration": "focus", "distraction": "focus", "overtime": "boundaries", "after_hours": "boundaries",
                 "calendar": "meetings", "overload": "workload_conversation", "workload": "workload_conversation",
                 "help": "support", "counselling": "support", "therapy": "support"}

SPECS = [
    {"name": "get_my_schedule", "roles": ALL,
     "description": "Get the signed-in user's meetings and a plain-language read on how hectic they are. "
                    "'range' can be today, tomorrow, this_week, next_week, a weekday name, or a YYYY-MM-DD date.",
     "input_schema": {"type": "object", "properties": {"range": {"type": "string"}}, "required": ["range"]}},
    {"name": "find_free_slots", "roles": ALL,
     "description": "Find open time in the user's calendar (9:00-18:00) on a day, big enough for a meeting of the given length.",
     "input_schema": {"type": "object", "properties": {"date": {"type": "string", "description": "today, tomorrow, weekday or YYYY-MM-DD"},
                                                        "duration_minutes": {"type": "integer"}}, "required": ["date"]}},
    {"name": "schedule_meeting", "roles": ALL,
     "description": "Book a meeting on the user's calendar (and on invitees' calendars). Use search_people first to get invitee ids. "
                    "If it conflicts with something, it will not book unless ignore_conflicts is true; ask the user first.",
     "input_schema": {"type": "object", "properties": {
         "title": {"type": "string"}, "date": {"type": "string", "description": "YYYY-MM-DD, today, tomorrow or weekday"},
         "start_time": {"type": "string", "description": "24h HH:MM"}, "duration_minutes": {"type": "integer"},
         "invitee_ids": {"type": "array", "items": {"type": "integer"}},
         "wellbeing": {"type": "boolean", "description": "true for a wellbeing check-in chat"},
         "ignore_conflicts": {"type": "boolean"}}, "required": ["title", "date", "start_time"]}},
    {"name": "cancel_meeting", "roles": ALL,
     "description": "Remove a meeting from the user's own calendar. Get the meeting_id from get_my_schedule.",
     "input_schema": {"type": "object", "properties": {"meeting_id": {"type": "integer"}}, "required": ["meeting_id"]}},
    {"name": "log_mood", "roles": ALL,
     "description": "Record the user's weekly check-in mood. Only call this when the user has said how they feel or asked you to log it.",
     "input_schema": {"type": "object", "properties": {"mood": {"type": "string", "enum": ["great", "good", "okay", "stressed", "overwhelmed"]},
                                                        "note": {"type": "string"}}, "required": ["mood"]}},
    {"name": "get_my_wellbeing", "roles": ALL,
     "description": "The user's own recent trends: message tone by week, schedule load by week and recent check-ins. Use it when they ask how they're doing.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "search_people", "roles": ALL,
     "description": "Look up colleagues by name or employee id. Returns id, name, team. Needed before messaging or inviting someone.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "send_message", "roles": ALL,
     "description": "Send a direct message from the user to a colleague. Only send after the user has clearly asked you to and the wording is agreed.",
     "input_schema": {"type": "object", "properties": {"to_id": {"type": "integer"}, "text": {"type": "string"}}, "required": ["to_id", "text"]}},
    {"name": "get_wellbeing_resources", "roles": ALL,
     "description": "Short practical guides. Topics: breathing, sleep, focus, boundaries, meetings, workload_conversation, stress, support.",
     "input_schema": {"type": "object", "properties": {"topic": {"type": "string"}}, "required": ["topic"]}},
    {"name": "get_team_overview", "roles": MANAGERS,
     "description": "Counts of people by wellbeing level and who needs a follow-up, for the manager's scope (team for leads, whole organisation for admins). "
                    "Optionally filter by level (High, Medium, Low).",
     "input_schema": {"type": "object", "properties": {"level": {"type": "string", "enum": ["High", "Medium", "Low"]}, "limit": {"type": "integer"}}}},
    {"name": "get_employee_status", "roles": MANAGERS,
     "description": "Level and plain-language reasons for one employee in the manager's scope. Never includes message text.",
     "input_schema": {"type": "object", "properties": {"employee_id": {"type": "integer"}}, "required": ["employee_id"]}},
    {"name": "send_checkin", "roles": MANAGERS,
     "description": "Send a private wellbeing check-in message to one or more employees in scope. Confirm the wording with the manager first.",
     "input_schema": {"type": "object", "properties": {"employee_ids": {"type": "array", "items": {"type": "integer"}},
                                                        "text": {"type": "string"}}, "required": ["employee_ids", "text"]}},
]

LABELS = {"get_my_schedule": "Checked your calendar", "find_free_slots": "Looked for free time",
          "schedule_meeting": "Booked a meeting", "cancel_meeting": "Cancelled a meeting", "log_mood": "Logged your check-in",
          "get_my_wellbeing": "Reviewed your trends", "search_people": "Searched the directory", "send_message": "Sent a message",
          "get_wellbeing_resources": "Opened a wellbeing guide", "get_team_overview": "Reviewed the team",
          "get_employee_status": "Looked up a teammate's status", "send_checkin": "Sent check-ins"}


def tool_specs(role: str) -> list:
    return [{k: v for k, v in s.items() if k != "roles"} for s in SPECS if role in s["roles"]]


def _today() -> date:
    return services.now().date()


def _resolve_day(arg: str):
    a = (arg or "").strip().lower()
    return parse_date(a, _today())


def _ev(e):
    return {"id": e["id"], "title": e["title"], "time": f"{hhmm(e['start'])}-{hhmm(e['end'])}"}


def _day_summary(d: dict, evs: list) -> dict:
    return {"date": d["date"], "weekday": d["weekday"], "label": d["label"], "count": d["count"], "hours": d["hours"],
            "back_to_back": d["back_to_back"], "lunch_blocked": d["lunch_blocked"],
            "events": [_ev(e) for e in evs]}


def t_get_my_schedule(user, a):
    rng = (a.get("range") or "this_week").strip().lower().replace(" ", "_")
    today = _today()
    if rng in ("this_week", "week", "next_week"):
        ws = analysis.monday_of(today) + (timedelta(days=7) if rng == "next_week" else timedelta())
        wk = analysis.analyze_week(user["id"], ws)
        by_day = {}
        for e in wk["events"]:
            by_day.setdefault(e["start"].date().isoformat(), []).append(e)
        return {"range": rng, "week_label": wk["label"], "total_hours": wk["total_hours"],
                "meeting_count": wk["meeting_count"], "reasons": wk["reasons"], "suggestion": wk["suggestion"],
                "days": [_day_summary(d, by_day.get(d["date"], [])) for d in wk["days"] if d["count"] or d["weekday"] in
                         ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")]}
    day = today if rng == "today" else (today + timedelta(days=1) if rng == "tomorrow" else _resolve_day(rng))
    if not day:
        return {"error": "I couldn't read that date. Use today, tomorrow, a weekday or YYYY-MM-DD."}
    ws = analysis.monday_of(day)
    wk = analysis.analyze_week(user["id"], ws)
    evs = [e for e in wk["events"] if e["start"].date() == day]
    d = next(x for x in wk["days"] if x["date"] == day.isoformat())
    return {"range": rng, "day": _day_summary(d, evs), "week_label": wk["label"]}


def t_find_free_slots(user, a):
    day = _resolve_day(a.get("date", "today"))
    if not day:
        return {"error": "I couldn't read that date."}
    mins = int(a.get("duration_minutes") or 30)
    starts = services.free_slots(user["id"], day, mins)
    windows = []
    for s in starts:
        h, m = map(int, s.split(":"))
        t0 = h * 60 + m
        if windows and t0 - windows[-1][1] <= 15 and windows[-1][1] == t0 - 15:
            windows[-1][1] = t0
        else:
            windows.append([t0, t0])
    wl = [{"from": f"{w[0] // 60:02d}:{w[0] % 60:02d}", "to": f"{(w[1] + mins) // 60:02d}:{(w[1] + mins) % 60:02d}"} for w in windows]
    suggested = [s for s in starts if s.endswith(":00") or s.endswith(":30")][:6]
    return {"date": day.isoformat(), "weekday": analysis.DAY_NAMES[day.weekday()], "duration_minutes": mins,
            "free_windows": wl, "suggested_starts": suggested}


def t_schedule_meeting(user, a):
    day = _resolve_day(a.get("date", ""))
    if not day:
        return {"error": "I couldn't read the date."}
    try:
        hh, mm = map(int, str(a.get("start_time", "")).split(":")[:2])
    except Exception:
        return {"error": "start_time must look like 14:30."}
    dur = int(a.get("duration_minutes") or 30)
    start = datetime.combine(day, datetime.min.time()).replace(hour=hh, minute=mm)
    end = start + timedelta(minutes=dur)
    if start < services.now() - timedelta(minutes=1):
        return {"error": "That time has already passed."}
    ids = [int(i) for i in (a.get("invitee_ids") or [])]
    if not a.get("ignore_conflicts"):
        clashes = []
        for uid in [user["id"]] + ids:
            for c in services.find_conflicts(uid, start, end):
                who = "You" if uid == user["id"] else services.get_user(uid)["name"]
                clashes.append({"who": who, "title": c["title"], "time": f"{c['start_ts'][11:16]}-{c['end_ts'][11:16]}"})
        if clashes:
            return {"created": False, "conflicts": clashes[:5],
                    "note": "Nothing booked. Ask whether to book anyway or pick another time."}
    res = services.create_meeting(user, a.get("title") or "Meeting", start, end, ids,
                                  "wellbeing" if a.get("wellbeing") else "meeting")
    return {"created": True, "meeting": {"id": res["event"]["id"], "title": res["event"]["title"], "date": day.isoformat(),
                                         "weekday": analysis.DAY_NAMES[day.weekday()], "start": hhmm(start), "end": hhmm(end),
                                         "attendees": res["event"]["attendees"]},
            "day_load": res["day"], "warning": res["warning"]}


def t_cancel_meeting(user, a):
    try:
        m = services.delete_meeting(user, int(a.get("meeting_id")))
    except services.ServiceError as e:
        return {"error": str(e)}
    return {"cancelled": True, "title": m["title"], "start": m["start_ts"]}


def t_log_mood(user, a):
    try:
        return {"logged": True, **services.log_mood(user["id"], a.get("mood"), a.get("note"))}
    except services.ServiceError as e:
        return {"error": str(e)}


def t_get_my_wellbeing(user, a):
    ins = services.my_insights(user)
    cur = ins["schedule"]["current"]
    return {"message_tone_by_week": [{"week_start": w["week_start"], "tone": w["label"]} for w in ins["tone"]["weeks"]],
            "message_analysis_enabled": ins["consent"],
            "schedule_load_by_week": [{"week_start": w["week_start"], "load": w["label"], "hours": w["hours"]} for w in ins["schedule"]["weeks"]],
            "this_week": {"load": cur["label"], "hours": cur["total_hours"], "reasons": cur["reasons"]},
            "last_check_in": (ins["mood"]["latest"] or {}).get("label"),
            "last_check_in_at": (ins["mood"]["latest"] or {}).get("created_at"),
            "check_in_moods_by_week": [{"week_start": w["week_start"], "mood": w["label"]} for w in ins["mood"]["weeks"]]}


def t_search_people(user, a):
    res = services.people_search(a.get("query", ""), limit=8, exclude_id=user["id"])
    return {"matches": [{"id": r["id"], "name": r["name"], "team": r["team"], "role": r["role"]} for r in res]}


def t_send_message(user, a):
    try:
        m = services.create_message(user, int(a.get("to_id")), a.get("text", ""))
    except services.ServiceError as e:
        return {"error": str(e)}
    return {"sent": True, "to": services.get_user(int(a["to_id"]))["name"], "message_id": m["id"]}


def t_get_wellbeing_resources(user, a):
    key = (a.get("topic") or "stress").strip().lower().replace(" ", "_")
    key = TOPIC_ALIASES.get(key, key)
    return RESOURCES.get(key) or {**RESOURCES["stress"], "note": f"No guide called '{key}', showing the general one."}


def t_get_team_overview(user, a):
    ov = services.overview(user)
    rows = ov["followups"]
    if a.get("level"):
        rows = [r for r in services.manager_rows(user) if r["risk"] == a["level"]]
        rows.sort(key=lambda r: -r["score"])
    lim = max(1, min(int(a.get("limit") or 8), 25))
    return {"scope": ov["scope_name"], "counts": ov["counts"], "schedule_levels": ov["schedule_levels"],
            "tone_levels": ov["tone_levels"], "checkins_sent_last_7_days": ov["checkins_sent_7d"],
            "people": [{"id": r["id"], "name": r["name"], "team": r["team"], "level": r["risk"], "tone": r["tone"],
                        "schedule": r["schedule"], "last_check_in_mood": r["mood"],
                        "check_in_sent": bool(r["last_checkin"]), "meeting_booked": bool(r["meeting"])} for r in rows[:lim]],
            "more": max(0, len(rows) - lim)}


def t_get_employee_status(user, a):
    try:
        d = services.employee_detail(user, int(a.get("employee_id")))
    except services.ServiceError as e:
        return {"error": str(e)}
    return {"name": d["name"], "team": d["team"], "level": d["risk"], "tone": d["tone"]["level"],
            "schedule": d["schedule"]["level"], "last_check_in_mood": d["mood"]["latest"], "reasons": d["reasons"],
            "message_analysis_enabled": d["consent"], "meeting_booked": d["meeting"]}


def t_send_checkin(user, a):
    try:
        return {**services.send_checkins(user, [int(i) for i in a.get("employee_ids", [])], a.get("text", "")), "ok": True}
    except services.ServiceError as e:
        return {"error": str(e)}


HANDLERS = {s["name"]: globals()[f"t_{s['name']}"] for s in SPECS}


def execute(user: dict, name: str, args: dict) -> dict:
    spec = next((s for s in SPECS if s["name"] == name), None)
    if not spec:
        return {"error": f"Unknown tool {name}."}
    if user["role"] not in spec["roles"]:
        return {"error": "Your role doesn't have access to that."}
    try:
        return HANDLERS[name](user, args or {})
    except services.ServiceError as e:
        return {"error": str(e)}
    except Exception as e:  # never let a tool crash the chat
        return {"error": f"Something went wrong running {name}: {e}"}
