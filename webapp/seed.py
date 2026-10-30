"""
seed.py -- fills an empty database with a realistic demo organisation.

Uses the 150 simulated employees from data/synthetic_employees.json (names,
weekly messages, meeting counts, after-hours work, weekly check-ins) and turns
them into real rows: users in 10 teams, message threads with replies, calendar
entries for the last 5 weeks, this week and next week, and weekly mood logs.
It runs automatically the first time the app starts.
"""

import json
import os
import random
from datetime import datetime, timedelta

from . import db, security, analysis

DATA = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "synthetic_employees.json"))

TEAM_NAMES = ["Platform Engineering", "Customer Success", "Product Design", "Data & Analytics", "Sales Operations",
              "Quality Engineering", "Finance Operations", "People Operations", "Security", "Mobile"]
TEAM_SIZE = 15

STAFF = [  # username, password, name, role, team index
    ("admin", "admin123", "Priya Raghunathan", "admin", None),
    ("lead", "lead123", "Arjun Venkatesh", "lead", 0),
    ("lead2", "lead123", "Kavita Subramanian", "lead", 1),
]
EMPLOYEE_PASSWORD = "emp123"

REPLIES = {
    "low": ["Sounds good, thanks for letting me know.", "Nice, happy to help with that.", "Great, let's sync after lunch.",
            "Thanks! That works for me.", "Perfect, I'll review it this afternoon.", "Good progress, keep it up!",
            "Appreciate it, things are on track on my side too.", "Love it, let's ship it."],
    "medium": ["Okay, I'll try to get to it, it's a busy week.", "Thanks, a bit stretched but I'll manage.",
               "Noted, I'm juggling a lot right now.", "Can we do it later? Pretty tired today.",
               "Sure, just need to clear some backlog first.", "Okay, long day but I'll look at it.",
               "Workload has picked up, hoping it settles soon."],
    "high": ["I'm drained too honestly, I can't keep up with everything.", "Sorry, I'm completely overwhelmed right now.",
             "I don't know how I'll fit that in, I'm exhausted.", "Another late night for me. I'm running on empty.",
             "Honestly it all feels pointless lately.", "I can't take on anything else, too much on my plate."],
}
MEETING_TITLES = ["Daily standup", "Sprint planning", "Design review", "1:1 with manager", "Client sync", "Backlog grooming",
                  "Incident review", "Roadmap sync", "Retro", "Product demo", "Cross-team sync", "Hiring panel",
                  "Quarterly planning", "Architecture review", "Customer call", "Status update", "Onboarding session"]
EVENING_TITLES = ["Release support", "Client call (APAC)", "Incident follow-up", "Catch-up on tasks", "Deployment window"]


def _gen_day(rng, n):
    """n meetings between 9:00 and 17:30; many meetings leave little slack -> back-to-back days."""
    if n <= 0:
        return []
    n = min(n, 10)
    window = 510
    durs = [rng.choice([30, 30, 45, 60, 60]) for _ in range(n)]
    if sum(durs) > window:
        durs = [30] * n
    slack = window - sum(durs)
    w = [rng.random() ** 2 + 0.02 for _ in range(n + 1)]
    gaps = [int(slack * x / sum(w)) // 5 * 5 for x in w]
    t, out = 9 * 60 + gaps[0], []
    for i, d in enumerate(durs):
        out.append((t, d))
        t += d + gaps[i + 1]
    return out


def _evening_sessions(rng, hours):
    if hours < 0.5:
        return []
    k = max(1, min(4, round(hours / 1.5)))
    each = max(30, int(round(hours / k * 4)) * 15)
    days = rng.sample(range(5), k=min(k, 5))
    return [(d, (18 * 60 + 30 if rng.random() < 0.7 else 19 * 60 + 30), each) for d in days]


def reset():
    if os.path.exists(db.DB_PATH):
        os.remove(db.DB_PATH)
    for ext in ("-wal", "-shm"):
        if os.path.exists(db.DB_PATH + ext):
            os.remove(db.DB_PATH + ext)


def seed_if_empty(verbose=True):
    db.init()
    if db.scalar("SELECT COUNT(*) FROM users", (), 0) > 0:
        return False
    run_seed(verbose)
    return True


def run_seed(verbose=True):
    rng = random.Random(2026)
    now = analysis.NOW_FN()
    this_monday = analysis.monday_of(now.date())
    with open(DATA) as f:
        people = json.load(f)

    def say(msg):
        if verbose:
            print(f"[seed] {msg}", flush=True)

    say("creating teams and users (first start only, takes a few seconds)...")
    team_ids = []
    with db.tx() as c:
        for name in TEAM_NAMES:
            team_ids.append(c.execute("INSERT INTO teams(name) VALUES (?)", (name,)).lastrowid)
        stamp = now.isoformat(timespec="seconds")
        staff_ids = {}
        for username, pw, name, role, t in STAFF:
            uid = c.execute(
                "INSERT INTO users(username, password_hash, name, role, team_id, emp_code, consent, created_at) VALUES (?,?,?,?,?,?,1,?)",
                (username, security.hash_password(pw), name, role, team_ids[t] if t is not None else None, None, stamp)).lastrowid
            staff_ids[username] = uid
            if role == "lead":
                c.execute("UPDATE teams SET lead_id=? WHERE id=?", (uid, team_ids[t]))
        # demo employees use a lighter hash cost so first start stays quick
        emp_hash_iters = 40_000
        uid_by_code, state_by_uid, team_by_uid = {}, {}, {}
        for idx, p in enumerate(people):
            t = team_ids[min(idx // TEAM_SIZE, len(team_ids) - 1)]
            uid = c.execute(
                "INSERT INTO users(username, password_hash, name, role, team_id, emp_code, consent, created_at) VALUES (?,?,?,?,?,?,1,?)",
                (p["employee_id"].lower(), security.hash_password(EMPLOYEE_PASSWORD, emp_hash_iters), p["name"],
                 "employee", t, p["employee_id"], stamp)).lastrowid
            uid_by_code[p["employee_id"]] = uid
            state_by_uid[uid] = p["true_burnout_state"]
            team_by_uid[uid] = t

    team_members = {}
    for uid, t in team_by_uid.items():
        team_members.setdefault(t, []).append(uid)
    lead_of_team = {team_ids[0]: staff_ids["lead"], team_ids[1]: staff_ids["lead2"]}

    # ---------------------------------------------------------------- messages
    say("writing message threads...")
    msgs = []

    def sample_ts(week_idx, state):
        ws = datetime.combine(this_monday - timedelta(days=7 * (5 - week_idx)), datetime.min.time())
        day = rng.randrange(5)
        hour = rng.randint(9, 18)
        if state == "high" and rng.random() < 0.3:
            hour = rng.randint(19, 23)
        ts = ws + timedelta(days=day, hours=hour, minutes=rng.randrange(60))
        if ts > now:
            ts = max(ws, now - timedelta(minutes=rng.randint(5, 900)))
        return ts

    for p in people:
        uid = uid_by_code[p["employee_id"]]
        t = team_by_uid[uid]
        mates = [m for m in team_members[t] if m != uid]
        for wk in p["weekly_messages"]:
            for text in wk["messages"]:
                to = lead_of_team.get(t) if (t in lead_of_team and rng.random() < 0.25) else rng.choice(mates)
                ts = sample_ts(wk["week"] - 1, state_by_uid[uid])
                msgs.append((ts, uid, to, text))
                if rng.random() < 0.6:
                    rstate = state_by_uid.get(to, "low")
                    rts = ts + timedelta(minutes=rng.randint(5, 90))
                    if rts <= now:
                        msgs.append((rts, to, uid, rng.choice(REPLIES[rstate])))
    msgs.sort(key=lambda m: m[0])
    with db.tx() as c:
        for ts, s, r, text in msgs:
            a = analysis.analyze_text(text)
            c.execute(
                "INSERT INTO messages(sender_id, recipient_id, text, kind, created_at, is_read, analyzed, stress_risk, stress_label, cues) "
                "VALUES (?,?,?,?,?,?,1,?,?,?)",
                (s, r, text, "chat", ts.isoformat(timespec="seconds"), 1 if ts < now - timedelta(days=1) else 0,
                 a["risk"], a["label"], json.dumps(a["cues"])))

    # ---------------------------------------------------------------- calendar
    say("building calendars...")
    cal_rows = []

    def add_meeting(owner, start, minutes, title, gid):
        end = start + timedelta(minutes=minutes)
        cal_rows.append((gid, owner, owner, title, start.isoformat(timespec="seconds"),
                         end.isoformat(timespec="seconds"), "meeting", now.isoformat(timespec="seconds")))

    gcount = 0
    for p in people + [{"employee_id": k, "daily_meetings_per_week": None} for k in ()]:
        uid = uid_by_code[p["employee_id"]]
        for w in range(7):                     # 0..5 = past + this week, 6 = next week
            src = min(w, 5)
            ws = this_monday - timedelta(days=7 * (5 - w))
            counts = p["daily_meetings_per_week"][src]
            after = p["after_hours_hours_per_week"][src]
            if w == 6:
                counts = [max(0, c + rng.choice([-1, 0, 0, 1])) for c in counts]
                after = after * 0.7
            for d in range(5):
                for start_min, dur in _gen_day(rng, counts[d]):
                    gcount += 1
                    add_meeting(uid, datetime.combine(ws + timedelta(days=d), datetime.min.time()) + timedelta(minutes=start_min),
                                dur, rng.choice(MEETING_TITLES), f"seed{gcount}")
            for d, start_min, dur in _evening_sessions(rng, after):
                gcount += 1
                add_meeting(uid, datetime.combine(ws + timedelta(days=d), datetime.min.time()) + timedelta(minutes=start_min),
                            dur, rng.choice(EVENING_TITLES), f"seed{gcount}")
    # light calendars for admin and leads
    for name in ("admin", "lead", "lead2"):
        uid = staff_ids[name]
        for w in range(7):
            ws = this_monday - timedelta(days=7 * (5 - w))
            for d in range(5):
                for start_min, dur in _gen_day(rng, rng.choice([2, 3, 3, 4])):
                    gcount += 1
                    add_meeting(uid, datetime.combine(ws + timedelta(days=d), datetime.min.time()) + timedelta(minutes=start_min),
                                dur, rng.choice(MEETING_TITLES), f"seed{gcount}")
    with db.tx() as c:
        c.executemany(
            "INSERT INTO meetings(group_id, owner_id, organizer_id, title, start_ts, end_ts, kind, created_at) VALUES (?,?,?,?,?,?,?,?)",
            cal_rows)

    # ------------------------------------------------------------------ moods
    say("logging weekly check-ins...")
    with db.tx() as c:
        for p in people:
            uid = uid_by_code[p["employee_id"]]
            for pc in p["pulse_checks"]:
                if pc["missed"]:
                    continue
                ws = datetime.combine(this_monday - timedelta(days=7 * (5 - (pc["week"] - 1))), datetime.min.time())
                ts = ws + timedelta(days=rng.randrange(1, 4), hours=rng.randint(10, 16), minutes=rng.randrange(60))
                if ts > now:
                    ts = max(ws, now - timedelta(minutes=rng.randint(10, 600)))
                c.execute("INSERT INTO moods(user_id, label, value, note, created_at) VALUES (?,?,?,?,?)",
                          (uid, pc["label"], pc["value"], None, ts.isoformat(timespec="seconds")))
    seed_physio_if_needed(verbose)
    say(f"done: {len(people)} employees, {len(msgs)} messages, {len(cal_rows)} calendar entries.")
    return {"state_by_uid": state_by_uid}


def seed_physio_if_needed(verbose=True):
    """Adds the demo body check-in readings and assistant chats to an existing database.
    Safe to run on every start: does nothing once seeded (or when the dataset has none)."""
    db.init()
    if db.scalar("SELECT COUNT(*) FROM physio_readings WHERE source='seed'", (), 0) > 0:
        return False
    if not os.path.exists(DATA):
        return False
    with open(DATA) as f:
        people = json.load(f)
    if not any("physio_readings" in p for p in people):
        return False
    now = analysis.NOW_FN()
    this_monday = analysis.monday_of(now.date())
    rng = random.Random(4242)
    hours = {"morning": 9, "afternoon": 14, "evening": 19}
    codes = {r["emp_code"]: r["id"] for r in db.rows("SELECT id, emp_code FROM users WHERE emp_code IS NOT NULL")}
    n_read = n_chat = 0
    with db.tx() as c:
        for p in people:
            uid = codes.get(p["employee_id"])
            if not uid:
                continue
            rd = p.get("physio_readings") or []
            if rd:
                c.execute("UPDATE users SET physio_consent=1 WHERE id=?", (uid,))
            for r in rd:
                t = now - timedelta(days=r["days_ago"])
                t = t.replace(hour=hours[r["slot"]], minute=rng.randint(0, 50), second=0, microsecond=0)
                if t > now:
                    t = now - timedelta(minutes=rng.randint(5, 240))
                c.execute("INSERT INTO physio_readings(user_id, slot, hr, gsr, quality, n_samples, source, created_at) "
                          "VALUES (?,?,?,?,?,?,?,?)",
                          (uid, r["slot"], r["hr"], r["gsr"], 1.0, 900, "seed", t.isoformat(timespec="seconds")))
                n_read += 1
            if db.scalar("SELECT COUNT(*) FROM chat_messages WHERE user_id=?", (uid,), 0):
                continue
            for wk in p.get("chatbot_weekly") or []:
                ws = datetime.combine(this_monday - timedelta(days=7 * (5 - (wk["week"] - 1))), datetime.min.time())
                for text in wk["messages"]:
                    t = ws + timedelta(days=rng.randrange(5), hours=rng.randint(9, 18), minutes=rng.randrange(60))
                    if t > now:
                        t = now - timedelta(minutes=rng.randint(30, 900))
                    stamp = t.isoformat(timespec="seconds")
                    c.execute("INSERT INTO chat_messages(user_id, role, content, created_at) VALUES (?,?,?,?)",
                              (uid, "user", text, stamp))
                    c.execute("INSERT INTO chat_messages(user_id, role, content, created_at) VALUES (?,?,?,?)",
                              (uid, "assistant", "Thanks for telling me. I can look at your calendar or find some free time if that helps.",
                               (t + timedelta(seconds=3)).isoformat(timespec="seconds")))
                    n_chat += 1
    if verbose:
        print(f"[seed] body check-ins: {n_read} readings, {n_chat} assistant messages added.", flush=True)
    return True
