"""
Adds sample history (messages, schedule, mood, check-ins) to one employee account.

    python tools/add_vidula_data.py                    # account "vidula"
    python tools/add_vidula_data.py --username vidula --password mypassword

Run it from the PulseCheck folder while the website is CLOSED (or just after closing run_lan.bat),
then start the website again. Safe to run twice: it removes the sample rows it added before.

Everything it adds is SAMPLE data (check-ins are marked source = "simulated"). Real readings taken
with the device are added separately and are never touched by this script.
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from webapp import analysis, db, security  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--username", default="vidula")
ap.add_argument("--name", default="Vidula Sanjana")
ap.add_argument("--full", action="store_true", help="add 3 readings a day for 9 days (default: a minimal set)")
ap.add_argument("--password", default="vidula123", help="only used if the account does not exist yet")
a = ap.parse_args()

db.init()


def iso(dt):
    return dt.isoformat(timespec="seconds")


now = analysis.NOW_FN().replace(second=0, microsecond=0)
rng = random.Random(4242)

# ------------------------------------------------------------------ the account
user = db.one("SELECT * FROM users WHERE username=?", (a.username.lower(),))
if not user:
    team = db.one("SELECT t.id FROM teams t LEFT JOIN users u ON u.team_id=t.id AND u.role='employee' "
                  "GROUP BY t.id ORDER BY COUNT(u.id), t.id LIMIT 1")
    uid = db.run("INSERT INTO users(username, password_hash, name, role, team_id, consent, physio_consent, created_at) "
                 "VALUES (?,?,?,?,?,1,1,?)",
                 (a.username.lower(), security.hash_password(a.password), a.name, "employee", team["id"] if team else None, iso(now)))
    db.run("UPDATE users SET emp_code=? WHERE id=?", (f"EMP{uid:03d}", uid))
    print(f"Created account '{a.username}' (password: {a.password}).")
else:
    uid = user["id"]
    db.run("UPDATE users SET physio_consent=1, consent=1 WHERE id=?", (uid,))
    print(f"Using existing account '{a.username}'.")
user = db.one("SELECT * FROM users WHERE id=?", (uid,))

# -------------------------------------------------- remove what an earlier run added
ZW = "\u200b"   # invisible marker at the end of sample moods/messages so a re-run can remove them
db.run("DELETE FROM physio_readings WHERE user_id=? AND source='simulated'", (uid,))
db.run("DELETE FROM moods WHERE user_id=? AND note LIKE ?", (uid, "%" + ZW))
db.run("DELETE FROM meetings WHERE owner_id=? AND group_id LIKE 'sample-%'", (uid,))
db.run("DELETE FROM messages WHERE (sender_id=? OR recipient_id=?) AND text LIKE ?", (uid, uid, "%" + ZW))


# ------------------------------------------------------------------ check-ins
# Minimal by default: 6 older readings (days 5 and 4 ago, 3 slots) = just enough for a personal normal range,
# plus 2 recent ones so the dashboard shows an average and a small change. --full adds 3 a day for 9 days.
hr0, gsr0 = 74.0, 500.0
count = 0
plan = [(d, k) for d in range(9, 0, -1) for k in range(3)] if a.full else \
       [(5, 0), (5, 1), (5, 2), (4, 0), (4, 1), (4, 2), (1, 0), (1, 1)]
for d, k in plan:
    slot = ("morning", "afternoon", "evening")[k]
    recent = d < 4
    step = (4 - d) if recent else 0
    hr_shift, gsr_mult = (3.0 * step, 1.0 + 0.12 * step) if a.full else ((4.0, 1.12) if recent else (0.0, 1.0))
    when = (now - timedelta(days=d)).replace(hour=(9, 14, 19)[k], minute=rng.randint(0, 45))
    hr = hr0 + hr_shift + rng.gauss(0, 1.6)
    gsr = gsr0 * gsr_mult * (1 + rng.gauss(0, 0.04))
    db.run("INSERT INTO physio_readings(user_id, slot, hr, gsr, quality, n_samples, source, created_at) "
           "VALUES (?,?,?,?,?,?,?,?)", (uid, slot, round(hr, 1), round(gsr, 1), 1.0, 900, "simulated", iso(when)))
    count += 1
print(f"Check-ins: {count} sample readings.")

# ---------------------------------------------------------------------- mood
moods = [(20, "good", "Steady week"), (17, "good", ""), (14, "okay", "Deadlines coming up"), (11, "okay", ""),
         (8, "good", "Better after the weekend"), (6, "okay", ""), (4, "stressed", "Two releases in one week"),
         (2, "stressed", "Late meetings again"), (1, "overwhelmed", "Too many things at once")]
for days_ago, label, note in moods:
    when = (now - timedelta(days=days_ago)).replace(hour=rng.choice((9, 10, 18)), minute=rng.randint(0, 50))
    db.run("INSERT INTO moods(user_id, label, value, note, created_at) VALUES (?,?,?,?,?)",
           (uid, label, analysis.MOOD_VALUES[label], (note or "") + ZW, iso(when)))
print(f"Mood: {len(moods)} entries.")

# ------------------------------------------------------------------ schedule
monday = analysis.monday_of(now.date())
mtg = [  # (week offset, weekday 0-4, "HH:MM", minutes, title)
    (-2, 0, "09:30", 30, "Daily standup"), (-2, 1, "11:00", 60, "Sprint planning"), (-2, 2, "15:00", 45, "Design review"),
    (-2, 3, "10:00", 30, "1:1 with manager"), (-2, 4, "16:00", 60, "Demo and retro"),
    (-1, 0, "09:30", 30, "Daily standup"), (-1, 0, "11:00", 60, "Roadmap sync"), (-1, 0, "14:00", 60, "Client sync"),
    (-1, 1, "09:30", 30, "Daily standup"), (-1, 1, "13:00", 90, "Architecture review"), (-1, 1, "18:30", 90, "Release support"),
    (-1, 2, "09:30", 30, "Daily standup"), (-1, 2, "10:30", 60, "Backlog grooming"), (-1, 2, "15:00", 60, "Cross-team sync"),
    (-1, 3, "09:30", 30, "Daily standup"), (-1, 3, "12:00", 60, "Hiring panel"), (-1, 3, "18:30", 120, "Deployment window"),
    (-1, 4, "11:00", 60, "Status update"),
    (0, 0, "09:30", 30, "Daily standup"), (0, 0, "10:30", 60, "Quarterly planning"), (0, 0, "12:00", 60, "Customer call"),
    (0, 0, "13:00", 60, "Incident review"), (0, 0, "14:00", 60, "Design review"), (0, 0, "15:00", 60, "Roadmap sync"),
    (0, 1, "09:30", 30, "Daily standup"), (0, 1, "10:00", 90, "Sprint planning"), (0, 1, "11:30", 60, "Client sync"),
    (0, 1, "14:00", 90, "Backlog grooming"), (0, 1, "18:30", 120, "Release support"),
    (0, 2, "09:30", 30, "Daily standup"), (0, 2, "11:00", 60, "Cross-team sync"), (0, 2, "15:30", 60, "1:1 with manager"),
    (0, 3, "09:30", 30, "Daily standup"), (0, 3, "13:00", 60, "Project review"), (0, 3, "18:30", 90, "Catch-up on tasks"),
    (0, 4, "10:00", 60, "Final project review"), (0, 4, "14:00", 60, "Viva preparation"),
    (1, 0, "09:30", 30, "Daily standup"), (1, 1, "11:00", 60, "Planning"), (1, 2, "15:00", 45, "Team sync"),
]
for wk, wd, hhmm, mins, title in mtg:
    day = monday + timedelta(weeks=wk, days=wd)
    h, m = map(int, hhmm.split(":"))
    start = datetime(day.year, day.month, day.day, h, m)
    end = start + timedelta(minutes=mins)
    gid = "sample-" + os.urandom(8).hex()
    db.run("INSERT INTO meetings(group_id, owner_id, organizer_id, title, start_ts, end_ts, kind, created_at) VALUES (?,?,?,?,?,?,?,?)",
           (gid, uid, uid, title, iso(start), iso(end), "meeting", iso(now)))
print(f"Schedule: {len(mtg)} calendar entries (last 2 weeks, this week, next week).")

# ------------------------------------------------------------------ messages
admin = db.one("SELECT id, name FROM users WHERE role='admin' ORDER BY id LIMIT 1")
lead = db.one("SELECT id, name FROM users WHERE role='lead' AND team_id=? ORDER BY id LIMIT 1", (user["team_id"],)) \
    or db.one("SELECT id, name FROM users WHERE role='lead' ORDER BY id LIMIT 1")
mate = db.one("SELECT id, name FROM users WHERE role='employee' AND team_id=? AND id<>? ORDER BY id LIMIT 1", (user["team_id"], uid))

convo = []   # (days_ago, hour, from_me, other, text)
if lead:
    convo += [
        (19, 10, False, lead, "Hi Vidula, welcome to the team. Ping me any time you need something."),
        (19, 10, True, lead, "Thanks! Happy to be here, the first week has been great."),
        (12, 15, True, lead, "The sprint is going well, I should finish the dashboard changes by Friday."),
        (12, 15, False, lead, "Great to hear. Keep me posted."),
        (6, 17, True, lead, "Quick update: I have two releases this week, so it is getting a bit busy."),
        (6, 17, False, lead, "Thanks for flagging it. Let me know if you need a hand."),
        (3, 21, True, lead, "Sorry for the late reply, I'm stretched and a little tired, but I'll get it done."),
        (3, 21, False, lead, "No rush. Look after yourself, we can move the deadline if needed."),
        (1, 22, True, lead, "Honestly I'm exhausted, I can't keep up with the late meetings and everything on my plate."),
    ]
if mate:
    convo += [
        (15, 11, False, mate, "Did you see the new design mockups? Looks nice."),
        (15, 11, True, mate, "Yes, love them. Let's review them after lunch."),
        (8, 14, True, mate, "Can you cover the standup tomorrow? Pretty tired today."),
        (8, 14, False, mate, "Sure, no problem."),
        (2, 20, True, mate, "I'm overwhelmed with the release, I will be offline for a bit."),
    ]
if admin:
    convo += [
        (9, 12, False, admin, "Hello Vidula, please make sure your three daily check-ins are done this week."),
        (9, 12, True, admin, "Will do, thanks for the reminder."),
    ]
n_msg = 0
slot_clock = {}   # (days_ago, hour) -> minutes already used, so replies always come after the message they answer
for days_ago, hour, from_me, other, text in sorted(convo, key=lambda x: -x[0]):
    key = (days_ago, hour)
    slot_clock[key] = slot_clock.get(key, rng.randint(0, 20)) + rng.randint(3, 12)
    when = (now - timedelta(days=days_ago)).replace(hour=hour, minute=min(slot_clock[key], 59))
    sender, rcpt = (uid, other["id"]) if from_me else (other["id"], uid)
    analyzed, risk, label, cues = 0, None, None, None
    if from_me:
        res = analysis.analyze_text(text)
        analyzed, risk, label, cues = 1, res["risk"], res["label"], json.dumps(res["cues"])
    db.run("INSERT INTO messages(sender_id, recipient_id, text, kind, created_at, is_read, analyzed, stress_risk, stress_label, cues) "
           "VALUES (?,?,?,?,?,?,?,?,?,?)",
           (sender, rcpt, text + ZW, "chat", iso(when), 1, analyzed, risk, label, cues))
    n_msg += 1
print(f"Messages: {n_msg} (all marked as read; new messages you send from admin will show as unread).")

analysis.touch(uid)
print("\nDone. Start the website again (run_lan.bat) and sign in as", a.username)
