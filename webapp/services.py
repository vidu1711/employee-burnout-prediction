"""
services.py -- business logic shared by the REST API and the chatbot tools.

Privacy rules enforced here (not in the browser):
  * people only ever see their OWN message analysis
  * leads/admins get levels and plain-language reasons, never message text
  * leads only see their own team; admins see everyone
"""

import json
import uuid
from datetime import datetime, date, timedelta

from . import db, analysis

MAX_TEXT = 2000


class ServiceError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def now() -> datetime:
    return analysis.NOW_FN()


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


def public_user(u: dict) -> dict:
    return {"id": u["id"], "name": u["name"], "username": u["username"], "role": u["role"],
            "team_id": u.get("team_id"), "team_name": u.get("team_name"), "initials": initials(u["name"]),
            "consent": bool(u["consent"]), "physio_consent": bool(u.get("physio_consent")),
            "emp_code": u.get("emp_code")}


# ------------------------------------------------------------------ people
def people_search(q: str = "", limit: int = 20, exclude_id: int = None) -> list:
    q = (q or "").strip().lower()
    args, where = [], ["1=1"]
    if q:
        where.append("(lower(u.name) LIKE ? OR lower(u.emp_code) LIKE ? OR lower(u.username) LIKE ?)")
        like = f"%{q}%"
        args += [like, like, like]
    if exclude_id:
        where.append("u.id<>?")
        args.append(exclude_id)
    args.append(limit)
    return db.rows(
        "SELECT u.id, u.name, u.role, u.emp_code, t.name AS team FROM users u LEFT JOIN teams t ON t.id=u.team_id "
        f"WHERE {' AND '.join(where)} ORDER BY u.name LIMIT ?", args)


def get_user(uid: int):
    return db.one("SELECT u.*, t.name AS team_name FROM users u LEFT JOIN teams t ON t.id=u.team_id WHERE u.id=?", (uid,))


# ---------------------------------------------------------------- messages
def _serialize_message(m: dict, viewer_id: int) -> dict:
    mine = m["sender_id"] == viewer_id
    out = {"id": m["id"], "from_me": mine, "text": m["text"], "kind": m["kind"], "at": m["created_at"],
           "read": bool(m["is_read"]), "sender_id": m["sender_id"]}
    if mine and m["analyzed"]:
        out["analysis"] = {"label": m["stress_label"], "risk": m["stress_risk"],
                           "cues": json.loads(m["cues"] or "[]")}
    return out


def create_message(sender: dict, to_id: int, text: str, kind: str = "chat") -> dict:
    text = (text or "").strip()
    if not text:
        raise ServiceError("Write a message first.")
    if len(text) > MAX_TEXT:
        raise ServiceError(f"Messages can be up to {MAX_TEXT} characters.")
    rcpt = get_user(to_id)
    if not rcpt or rcpt["id"] == sender["id"]:
        raise ServiceError("Pick someone else to message.")
    analyzed, risk, label, cues = 0, None, None, None
    if kind == "chat" and sender["consent"]:
        a = analysis.analyze_text(text)
        analyzed, risk, label, cues = 1, a["risk"], a["label"], json.dumps(a["cues"])
    mid = db.run(
        "INSERT INTO messages(sender_id, recipient_id, text, kind, created_at, is_read, analyzed, stress_risk, stress_label, cues) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (sender["id"], to_id, text, kind, iso(now()), 0, analyzed, risk, label, cues))
    analysis.touch(sender["id"])
    return _serialize_message(db.one("SELECT * FROM messages WHERE id=?", (mid,)), sender["id"])


def conversations(user_id: int) -> list:
    rows = db.rows(
        "SELECT * FROM messages WHERE sender_id=? OR recipient_id=? ORDER BY id DESC", (user_id, user_id))
    seen, out = {}, []
    for m in rows:
        other = m["recipient_id"] if m["sender_id"] == user_id else m["sender_id"]
        if other not in seen:
            seen[other] = {"other_id": other, "last": m, "unread": 0}
            out.append(seen[other])
        if m["recipient_id"] == user_id and not m["is_read"]:
            seen[other]["unread"] += 1
    result = []
    for c in out:
        u = get_user(c["other_id"])
        if not u:
            continue
        m = c["last"]
        result.append({"user": {"id": u["id"], "name": u["name"], "team": u["team_name"], "role": u["role"]},
                       "last": {"text": m["text"], "at": m["created_at"], "from_me": m["sender_id"] == user_id,
                                "kind": m["kind"]},
                       "unread": c["unread"]})
    return result


def thread(user_id: int, other_id: int, after_id: int = 0, limit: int = 200) -> dict:
    other = get_user(other_id)
    if not other:
        raise ServiceError("That person doesn't exist.", 404)
    rows = db.rows(
        "SELECT * FROM (SELECT * FROM messages WHERE ((sender_id=? AND recipient_id=?) OR (sender_id=? AND recipient_id=?)) "
        "AND id>? ORDER BY id DESC LIMIT ?) ORDER BY id",
        (user_id, other_id, other_id, user_id, after_id, limit))
    db.run("UPDATE messages SET is_read=1 WHERE recipient_id=? AND sender_id=? AND is_read=0", (user_id, other_id))
    return {"other": {"id": other["id"], "name": other["name"], "team": other["team_name"], "role": other["role"]},
            "messages": [_serialize_message(m, user_id) for m in rows]}


def unread_count(user_id: int) -> int:
    return db.scalar("SELECT COUNT(*) FROM messages WHERE recipient_id=? AND is_read=0", (user_id,), 0)


# ---------------------------------------------------------------- schedule
def serialize_event(e: dict, viewer_id: int) -> dict:
    others = db.rows(
        "SELECT u.id, u.name FROM meetings m JOIN users u ON u.id=m.owner_id WHERE m.group_id=? AND m.owner_id<>?",
        (e["group_id"], viewer_id))
    org = get_user(e["organizer_id"])
    return {"id": e["id"], "title": e["title"], "start": e["start_ts"], "end": e["end_ts"], "kind": e["kind"],
            "organizer": org["name"] if org else None, "mine": e["organizer_id"] == viewer_id,
            "attendees": [o["name"] for o in others][:8], "attendee_count": len(others)}


def week_view(user_id: int, week_start: date) -> dict:
    a = analysis.analyze_week(user_id, week_start)
    events = [serialize_event(e, user_id) for e in a.pop("events")]
    return {"week_start": week_start.isoformat(), "events": events, "analysis": a}


def create_meeting(creator: dict, title: str, start: datetime, end: datetime,
                   invitee_ids: list = None, kind: str = "meeting") -> dict:
    title = (title or "").strip() or "Meeting"
    if end <= start:
        raise ServiceError("The end time has to be after the start time.")
    if end - start > timedelta(hours=12):
        raise ServiceError("Meetings can be up to 12 hours long.")
    if start.date() != end.date():
        raise ServiceError("Keep a meeting within a single day.")
    invitee_ids = [i for i in dict.fromkeys(invitee_ids or []) if i != creator["id"]][:20]
    for i in invitee_ids:
        if not get_user(i):
            raise ServiceError("One of the invitees doesn't exist.")
    gid = uuid.uuid4().hex
    mine = None
    for owner in [creator["id"]] + invitee_ids:
        mid = db.run(
            "INSERT INTO meetings(group_id, owner_id, organizer_id, title, start_ts, end_ts, kind, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)", (gid, owner, creator["id"], title, iso(start), iso(end), kind, iso(now())))
        if owner == creator["id"]:
            mine = mid
    analysis.touch(creator["id"], *invitee_ids)
    ws = analysis.monday_of(start.date())
    wk = analysis.analyze_week(creator["id"], ws)
    day = next(d for d in wk["days"] if d["date"] == start.date().isoformat())
    warning = None
    if day["label"] in ("busy", "hectic"):
        warning = (f"{day['weekday']} is now {day['label']}: {day['count']} meetings, "
                   f"{day['hours']:.1f} h booked" + (", no lunch break" if day["lunch_blocked"] else "") + ".")
    ev = serialize_event(db.one("SELECT * FROM meetings WHERE id=?", (mine,)), creator["id"])
    return {"event": ev, "warning": warning, "day": {k: day[k] for k in ("label", "count", "hours", "weekday")}}


def delete_meeting(user: dict, meeting_id: int):
    m = db.one("SELECT * FROM meetings WHERE id=?", (meeting_id,))
    if not m or m["owner_id"] != user["id"]:
        raise ServiceError("That meeting isn't on your calendar.", 404)
    db.run("DELETE FROM meetings WHERE id=?", (meeting_id,))
    analysis.touch(user["id"])
    return m


def find_conflicts(user_id: int, start: datetime, end: datetime) -> list:
    return db.rows(
        "SELECT id, title, start_ts, end_ts FROM meetings WHERE owner_id=? AND start_ts<? AND end_ts>?",
        (user_id, iso(end), iso(start)))


def free_slots(user_id: int, day: date, minutes: int = 30) -> list:
    """Free start times between 9:00 and 18:00 that fit `minutes`, 15-minute steps."""
    d0 = datetime.combine(day, datetime.min.time())
    busy = [(e["start"], e["end"]) for e in analysis.events_between(user_id, d0, d0 + timedelta(days=1))]
    out, t = [], d0.replace(hour=9)
    end_of_day = d0.replace(hour=18)
    floor = now() if day == now().date() else None
    while t + timedelta(minutes=minutes) <= end_of_day:
        t_end = t + timedelta(minutes=minutes)
        if not any(s < t_end and e > t for s, e in busy) and (floor is None or t > floor):
            out.append(t.strftime("%H:%M"))
        t += timedelta(minutes=15)
    return out


# -------------------------------------------------------------------- mood
def log_mood(user_id: int, label: str, note: str = None) -> dict:
    label = (label or "").lower().strip()
    if label not in analysis.MOOD_VALUES:
        raise ServiceError("Pick one of: great, good, okay, stressed, overwhelmed.")
    db.run("INSERT INTO moods(user_id, label, value, note, created_at) VALUES (?,?,?,?,?)",
           (user_id, label, analysis.MOOD_VALUES[label], (note or "")[:500] or None, iso(now())))
    analysis.touch(user_id)
    return {"label": label}


# ------------------------------------------------------- manager / admin
def scope_employee_ids(manager: dict) -> list:
    if manager["role"] == "admin":
        rows = db.rows("SELECT id FROM users WHERE role='employee'")
    elif manager["role"] == "lead":
        rows = db.rows("SELECT id FROM users WHERE role='employee' AND team_id=?", (manager["team_id"],))
    else:
        raise ServiceError("Your role doesn't have access to this.", 403)
    return [r["id"] for r in rows]


def _check_in_scope(manager: dict, emp_id: int):
    if emp_id not in set(scope_employee_ids(manager)):
        raise ServiceError("That person isn't in your team.", 403)


def _last_checkin(emp_id: int):
    return db.one(
        "SELECT m.created_at, u.name AS by_name FROM messages m JOIN users u ON u.id=m.sender_id "
        "WHERE m.recipient_id=? AND m.kind='checkin' ORDER BY m.id DESC LIMIT 1", (emp_id,))


def _upcoming_wellbeing(emp_id: int):
    return db.one(
        "SELECT start_ts, title FROM meetings WHERE owner_id=? AND kind='wellbeing' AND start_ts>=? "
        "ORDER BY start_ts LIMIT 1", (emp_id, iso(now())))


def employee_row(emp_id: int) -> dict:
    u = get_user(emp_id)
    p = analysis.predict_user(emp_id)
    ck = _last_checkin(emp_id)
    mt = _upcoming_wellbeing(emp_id)
    return {"id": emp_id, "name": u["name"], "emp_code": u["emp_code"], "team": u["team_name"], "team_id": u["team_id"],
            "risk": p["risk"], "score": p["score"], "tone": p["tone"]["level"], "schedule": p["schedule"]["level"],
            "mood": p["mood"]["latest"], "body": p["physio"]["level"], "body_persistent": p["physio"]["persistent"],
            "assistant": p["chatbot"]["level"], "last_checkin": ck["created_at"] if ck else None,
            "meeting": mt["start_ts"] if mt else None}


def manager_rows(manager: dict) -> list:
    return [employee_row(i) for i in scope_employee_ids(manager)]


def overview(manager: dict) -> dict:
    rows = manager_rows(manager)
    counts = {"total": len(rows), "high": 0, "medium": 0, "low": 0}
    for r in rows:
        counts[r["risk"].lower()] += 1
    sched = {"light": 0, "balanced": 0, "busy": 0, "hectic": 0}
    tone = {"calm": 0, "tense": 0, "stressed": 0}
    for r in rows:
        sched[r["schedule"]] = sched.get(r["schedule"], 0) + 1
        if r["tone"]:
            tone[r["tone"]] += 1

    preds = [analysis.predict_user(r["id"]) for r in rows]
    weeks = []
    if preds:
        for i in range(6):
            vals = [p["tone"]["weeks"][i]["risk"] for p in preds if p["tone"]["weeks"][i]["risk"] is not None]
            hect = sum(1 for p in preds if p["schedule"]["weeks"][i]["label"] in ("busy", "hectic"))
            weeks.append({"week_start": preds[0]["tone"]["weeks"][i]["week_start"],
                          "avg_tone": round(sum(vals) / len(vals), 1) if vals else None,
                          "stressed_share": round(sum(1 for v in vals if v >= 50) / len(vals) * 100) if vals else None,
                          "busy_share": round(hect / len(preds) * 100)})

    teams = []
    if manager["role"] == "admin":
        by = {}
        for r in rows:
            t = by.setdefault(r["team_id"], {"id": r["team_id"], "name": r["team"], "size": 0, "high": 0, "medium": 0})
            t["size"] += 1
            if r["risk"] == "High":
                t["high"] += 1
            if r["risk"] == "Medium":
                t["medium"] += 1
        teams = sorted(by.values(), key=lambda t: -(t["high"] * 2 + t["medium"]) / max(t["size"], 1))

    since = iso(now() - timedelta(days=7))
    if manager["role"] == "admin":
        sent = db.scalar("SELECT COUNT(*) FROM messages WHERE kind='checkin' AND created_at>=?", (since,), 0)
    else:
        sent = db.scalar("SELECT COUNT(*) FROM messages WHERE kind='checkin' AND sender_id=? AND created_at>=?",
                         (manager["id"], since), 0)
    booked = sum(1 for r in rows if r["meeting"])
    follow = sorted([r for r in rows if r["risk"] in ("High", "Medium")],
                    key=lambda r: (r["risk"] != "High", -r["score"]))
    return {"scope": "org" if manager["role"] == "admin" else "team",
            "scope_name": "Whole organisation" if manager["role"] == "admin" else (manager.get("team_name") or "Your team"),
            "counts": counts, "schedule_levels": sched, "tone_levels": tone, "weeks": weeks, "teams": teams,
            "followups": follow, "checkins_sent_7d": sent, "wellbeing_meetings_booked": booked}


def employee_detail(manager: dict, emp_id: int) -> dict:
    _check_in_scope(manager, emp_id)
    u = get_user(emp_id)
    p = analysis.predict_user(emp_id)
    history = db.rows(
        "SELECT m.created_at AS at, u.name AS by_name, m.text FROM messages m JOIN users u ON u.id=m.sender_id "
        "WHERE m.recipient_id=? AND m.kind='checkin' ORDER BY m.id DESC LIMIT 5", (emp_id,))
    mt = _upcoming_wellbeing(emp_id)
    return {"id": emp_id, "name": u["name"], "emp_code": u["emp_code"], "team": u["team_name"],
            "risk": p["risk"], "tone": p["tone"], "schedule": {"level": p["schedule"]["level"], "weeks": p["schedule"]["weeks"],
                                                              "current": {k: p["schedule"]["current"][k] for k in ("label", "total_hours", "meeting_count", "reasons", "suggestion")}},
            "mood": p["mood"], "reasons": p["reasons"], "consent": bool(u["consent"]),
            "body": {k: p["physio"][k] for k in ("level", "persistent", "ready")}, "assistant": {"level": p["chatbot"]["level"]}, "physio_consent": bool(u["physio_consent"]),
            "checkins": history, "meeting": mt["start_ts"] if mt else None}


def send_checkins(manager: dict, ids: list, text: str) -> dict:
    allowed = set(scope_employee_ids(manager))
    ids = [i for i in dict.fromkeys(ids) if i in allowed]
    if not ids:
        raise ServiceError("Pick at least one person from your team.")
    text = (text or "").strip()
    if not text:
        raise ServiceError("Write a message first.")
    stamp = iso(now())
    with db.tx() as c:
        for i in ids:
            c.execute("INSERT INTO messages(sender_id, recipient_id, text, kind, created_at, is_read, analyzed) "
                      "VALUES (?,?,?,?,?,0,0)", (manager["id"], i, text, "checkin", stamp))
    return {"sent": len(ids)}


# -------------------------------------------------------------- self view
def my_insights(user: dict) -> dict:
    p = analysis.predict_user(user["id"])
    this_week = analysis.monday_of(now().date())
    cur = analysis.analyze_week(user["id"], this_week)
    cur.pop("events", None)
    pending = db.rows(
        "SELECT m.id, m.created_at, u.name AS by_name, m.sender_id, m.text FROM messages m JOIN users u ON u.id=m.sender_id "
        "WHERE m.recipient_id=? AND m.kind='checkin' ORDER BY m.id DESC LIMIT 3", (user["id"],))
    last_mood = db.one("SELECT label, created_at FROM moods WHERE user_id=? ORDER BY created_at DESC LIMIT 1", (user["id"],))
    return {"tone": {"weeks": p["tone"]["weeks"], "level": p["tone"]["level"]},
            "schedule": {"weeks": p["schedule"]["weeks"], "current": cur},
            "mood": {"weeks": p["mood"]["weeks"], "latest": last_mood},
            "checkins": pending, "consent": bool(user["consent"]),
            "physio_consent": bool(user.get("physio_consent")), "body": analysis.physio_summary(user["id"])}
