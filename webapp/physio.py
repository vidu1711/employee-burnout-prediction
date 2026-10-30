"""
physio.py -- body check-ins (ESP32 with MAX30102 heart-rate sensor and GSR sensor).

Flow:
  1. The employee presses "Start" on the website (morning / afternoon / evening).
     That creates a check-in SESSION for one device.
  2. The ESP32 polls /api/device/poll. When it sees a session it asks the person
     to place a finger on the sensors, measures for ~30 seconds, and POSTs one
     reading (average heart rate + average skin conductance) to /api/device/readings.
  3. The reading is stored, compared with that person's own baseline, and the
     website shows the result.

Privacy rules:
  * readings are only used for burnout analysis when the person switched
    "physiological check-ins" on (separate from message analysis consent)
  * managers see a level (normal / elevated / high) and "persistent or not",
    never the raw numbers
  * the device is never told who is measuring
"""

import time
import hashlib
import os
import secrets
import random
from datetime import datetime, timedelta

from . import db, analysis
from .services import ServiceError, now, iso

SLOTS = ("morning", "afternoon", "evening")
SESSION_MINUTES = 3
SHARED_DEVICE_ID = "ESP32-DEMO"
SHARED_DEVICE_KEY = os.environ.get("PULSECHECK_DEMO_DEVICE_KEY", "demo-device-key")
ALLOW_SIMULATION = os.environ.get("PULSECHECK_ALLOW_SIMULATION", "1") != "0"
HR_RANGE = (35.0, 210.0)
GSR_RANGE = (0.0, 4095.0)


def _hash_key(key: str) -> str:
    return hashlib.sha256(("pulsecheck-device:" + key).encode()).hexdigest()


def ensure_shared_device():
    """The demo/shared device that any employee can use."""
    if not db.one("SELECT id FROM devices WHERE id=?", (SHARED_DEVICE_ID,)):
        db.run("INSERT INTO devices(id, key_hash, user_id, label, created_at) VALUES (?,?,?,?,?)",
               (SHARED_DEVICE_ID, _hash_key(SHARED_DEVICE_KEY), None, "Shared check-in station", iso(now())))


def default_slot(dt: datetime = None) -> str:
    h = (dt or now()).hour
    return "morning" if h < 12 else "afternoon" if h < 17 else "evening"


# -------------------------------------------------------------- devices
def register_device(user: dict, label: str = None) -> dict:
    """Personal device for one employee. The key is shown once."""
    n = db.scalar("SELECT COUNT(*) FROM devices WHERE user_id=?", (user["id"],), 0)
    if n >= 3:
        raise ServiceError("You already have 3 devices. Remove one first.")
    dev_id = "PC-" + secrets.token_hex(3).upper()
    key = secrets.token_urlsafe(18)
    db.run("INSERT INTO devices(id, key_hash, user_id, label, created_at) VALUES (?,?,?,?,?)",
           (dev_id, _hash_key(key), user["id"], (label or "My ESP32")[:40], iso(now())))
    return {"device_id": dev_id, "device_key": key, "label": (label or "My ESP32")[:40]}


def remove_device(user: dict, device_id: str):
    d = db.one("SELECT * FROM devices WHERE id=?", (device_id,))
    if not d or d["user_id"] != user["id"]:
        raise ServiceError("That device isn't yours.", 404)
    db.run("DELETE FROM devices WHERE id=?", (device_id,))


def device_online(d: dict) -> bool:
    if not d.get("last_seen"):
        return False
    return (now() - datetime.fromisoformat(d["last_seen"])).total_seconds() < 20


def my_devices(user_id: int) -> list:
    rows = db.rows("SELECT id, label, user_id, last_seen FROM devices WHERE user_id=? OR user_id IS NULL "
                   "ORDER BY user_id IS NULL, created_at", (user_id,))
    return [{"id": r["id"], "label": r["label"], "shared": r["user_id"] is None, "online": device_online(r),
             "last_seen": r["last_seen"]} for r in rows]


def authenticate_device(device_id: str, key: str) -> dict:
    d = db.one("SELECT * FROM devices WHERE id=?", (device_id or "",))
    if not d or not secrets.compare_digest(d["key_hash"], _hash_key(key or "")):
        raise ServiceError("Unknown device or wrong key.", 401)
    db.run("UPDATE devices SET last_seen=? WHERE id=?", (iso(now()), d["id"]))
    d["last_seen"] = iso(now())
    return d


# ------------------------------------------------------------- sessions
def _expire_old():
    t = iso(now())
    db.run("UPDATE checkin_sessions SET status='expired', message='Nobody picked this up in time. Try again.' "
           "WHERE status IN ('pending','measuring') AND expires_at<?", (t,))


def _serialize_session(s: dict) -> dict:
    out = {"id": s["id"], "slot": s["slot"], "status": s["status"], "message": s["message"], "device_id": s["device_id"],
           "created_at": s["created_at"], "seconds": 30, "server_now": time.time(),
           "picked_at": s.get("picked_at"), "measure_at": s.get("measure_at")}
    if s["reading_id"]:
        out["reading"] = reading_view(s["reading_id"], s["user_id"])
    return out


def start_session(user: dict, slot: str = None, device_id: str = None) -> dict:
    _expire_old()
    slot = (slot or default_slot()).lower()
    if slot not in SLOTS:
        raise ServiceError("Pick morning, afternoon or evening.")
    if not user.get("physio_consent"):
        raise ServiceError("Turn on body check-ins first (the switch on this page).", 403)
    devices = {d["id"]: d for d in my_devices(user["id"])}
    if not devices:
        raise ServiceError("No device is linked to your account yet.")
    if device_id:
        if device_id not in devices:
            raise ServiceError("That device isn't available to you.", 404)
    else:
        personal = [d for d in devices.values() if not d["shared"]]
        device_id = (personal or list(devices.values()))[0]["id"]
    mine = db.one("SELECT id FROM checkin_sessions WHERE user_id=? AND status IN ('pending','measuring')", (user["id"],))
    if mine:
        db.run("UPDATE checkin_sessions SET status='cancelled', message='Replaced by a new check-in.' WHERE id=?", (mine["id"],))
    busy = db.one("SELECT id FROM checkin_sessions WHERE device_id=? AND status IN ('pending','measuring')", (device_id,))
    if busy:
        raise ServiceError("Someone else is using that device right now. Try again in a minute.", 409)
    t0 = now()
    sid = db.run("INSERT INTO checkin_sessions(user_id, device_id, slot, status, created_at, expires_at) VALUES (?,?,?,?,?,?)",
                 (user["id"], device_id, slot, "pending", iso(t0), iso(t0 + timedelta(minutes=SESSION_MINUTES))))
    return get_session(user, sid)


def get_session(user: dict, session_id: int) -> dict:
    _expire_old()
    s = db.one("SELECT * FROM checkin_sessions WHERE id=? AND user_id=?", (session_id, user["id"]))
    if not s:
        raise ServiceError("Check-in not found.", 404)
    return _serialize_session(s)


def cancel_session(user: dict, session_id: int):
    s = db.one("SELECT * FROM checkin_sessions WHERE id=? AND user_id=?", (session_id, user["id"]))
    if not s:
        raise ServiceError("Check-in not found.", 404)
    if s["status"] in ("pending", "measuring"):
        db.run("UPDATE checkin_sessions SET status='cancelled', message='Cancelled.' WHERE id=?", (session_id,))


def active_session(user_id: int):
    _expire_old()
    s = db.one("SELECT * FROM checkin_sessions WHERE user_id=? AND status IN ('pending','measuring') ORDER BY id DESC LIMIT 1",
               (user_id,))
    return _serialize_session(s) if s else None


# --------------------------------------------------- device-facing calls
def device_poll(device: dict) -> dict:
    """Called by the ESP32 every couple of seconds."""
    _expire_old()
    s = db.one("SELECT * FROM checkin_sessions WHERE device_id=? AND status IN ('pending','measuring') ORDER BY id LIMIT 1",
               (device["id"],))
    if not s:
        return {"session": None}
    if s["status"] == "pending":
        db.run("UPDATE checkin_sessions SET status='measuring', picked_at=? WHERE id=?", (time.time(), s["id"]))
    return {"session": {"id": s["id"], "slot": s["slot"], "seconds": 30}}


def device_progress(device: dict, payload: dict) -> dict:
    """The device says the finger is on and the 30 second measurement has started."""
    s = db.one("SELECT * FROM checkin_sessions WHERE id=? AND device_id=?", (payload.get("session_id"), device["id"]))
    if not s or s["status"] not in ("pending", "measuring"):
        return {"ok": False}
    if payload.get("phase") == "measuring":
        db.run("UPDATE checkin_sessions SET status='measuring', measure_at=? WHERE id=?", (time.time(), s["id"]))
    return {"ok": True}


def device_report(device: dict, payload: dict) -> dict:
    sid = payload.get("session_id")
    s = db.one("SELECT * FROM checkin_sessions WHERE id=? AND device_id=?", (sid, device["id"]))
    if not s:
        raise ServiceError("No such check-in for this device.", 404)
    if s["status"] not in ("pending", "measuring"):
        raise ServiceError("That check-in is already closed.", 409)

    if not payload.get("valid", True):
        reason = {"no_finger": "No finger was detected on the sensor.",
                  "no_pulse": "A clear pulse could not be found. Keep still and rest your finger lightly."
                  }.get(payload.get("reason"), "The device could not take a clear reading.")
        db.run("UPDATE checkin_sessions SET status='failed', message=? WHERE id=?", (reason, sid))
        return {"ok": True}

    try:
        hr, gsr = float(payload.get("hr")), float(payload.get("gsr"))
    except (TypeError, ValueError):
        raise ServiceError("hr and gsr must be numbers.")
    if not (HR_RANGE[0] <= hr <= HR_RANGE[1]) or not (GSR_RANGE[0] <= gsr <= GSR_RANGE[1]):
        db.run("UPDATE checkin_sessions SET status='failed', message='The reading looked out of range. Please try again.' WHERE id=?", (sid,))
        raise ServiceError("Reading out of range.")
    rid = _store(s["user_id"], s["slot"], hr, gsr, float(payload.get("quality") or 0) or None,
                 int(payload.get("n_samples") or 0) or None, "device", device["id"], sid)
    db.run("UPDATE checkin_sessions SET status='done', reading_id=?, message=NULL WHERE id=?", (rid, sid))
    return {"ok": True, "reading_id": rid}


def _store(user_id, slot, hr, gsr, quality, n, source, device_id=None, session_id=None, when=None) -> int:
    rid = db.run("INSERT INTO physio_readings(user_id, session_id, device_id, slot, hr, gsr, quality, n_samples, source, created_at) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (user_id, session_id, device_id, slot, round(hr, 1), round(gsr, 1), quality, n, source, when or iso(now())))
    analysis.touch(user_id)
    return rid


# ------------------------------------------------------------- simulation
def simulate(user: dict, slot: str = None, level: str = "auto") -> dict:
    """A demo reading when no hardware is connected. Always stored with source='simulated'."""
    if not ALLOW_SIMULATION:
        raise ServiceError("Simulated readings are turned off on this server.", 403)
    if not user.get("physio_consent"):
        raise ServiceError("Turn on body check-ins first (the switch on this page).", 403)
    slot = (slot or default_slot()).lower()
    if slot not in SLOTS:
        raise ServiceError("Pick morning, afternoon or evening.")
    base = analysis.physio_baseline_for(user["id"])
    hr_b, gsr_b = (base["hr"], base["gsr"]) if base else (72.0, 420.0)
    rng = random.Random()
    if level == "elevated":
        hr, gsr = hr_b + rng.uniform(12, 20), gsr_b * rng.uniform(1.30, 1.65)
    else:
        hr, gsr = hr_b + rng.uniform(-3, 4), gsr_b * rng.uniform(0.95, 1.08)
    rid = _store(user["id"], slot, hr, gsr, 1.0, 900, "simulated")
    return {"reading": reading_view(rid, user["id"])}


def simulate_baseline(user: dict) -> dict:
    """Demo helper: fills ~6 days of normal-range readings dated 4-9 days ago, so a new account
    has a baseline right away. Marked source='simulated'. Not available when simulation is off."""
    if not ALLOW_SIMULATION:
        raise ServiceError("Simulated readings are turned off on this server.", 403)
    if not user.get("physio_consent"):
        raise ServiceError("Turn on body check-ins first (the switch on this page).", 403)
    rng = random.Random(user["id"] * 7919)
    hr0, gsr0 = rng.uniform(62, 82), rng.uniform(300, 560)
    t = now()
    n = 0
    for d in range(4, 10):
        for k, slot in enumerate(SLOTS):
            when = (t - timedelta(days=d)).replace(hour=(9, 14, 19)[k], minute=rng.randint(0, 50), second=0, microsecond=0)
            rid = db.run("INSERT INTO physio_readings(user_id, slot, hr, gsr, quality, n_samples, source, created_at) "
                         "VALUES (?,?,?,?,?,?,?,?)",
                         (user["id"], slot, round(hr0 + rng.gauss(0, 2), 1), round(gsr0 * (1 + rng.gauss(0, 0.05)), 1),
                          1.0, 900, "simulated", iso(when)))
            n += 1
    analysis.touch(user["id"])
    return {"added": n}


# ------------------------------------------------------------ views
def reading_view(reading_id: int, user_id: int) -> dict:
    r = db.one("SELECT * FROM physio_readings WHERE id=? AND user_id=?", (reading_id, user_id))
    if not r:
        return None
    return _reading_dict(r, analysis.physio_baseline_for(user_id))


def _reading_dict(r: dict, base: dict = None) -> dict:
    from signal_physio import reading_score, status_for
    out = {"id": r["id"], "slot": r["slot"], "hr": r["hr"], "gsr": r["gsr"], "at": r["created_at"], "source": r["source"]}
    if base:
        sc = reading_score(r["hr"], r["gsr"], base["hr"], base["gsr"])
        out.update({"status": status_for(sc), "hr_baseline": base["hr"], "hr_deviation": round(r["hr"] - base["hr"], 1),
                    "gsr_baseline": base["gsr"], "gsr_deviation_pct": round((r["gsr"] - base["gsr"]) / max(base["gsr"], 1) * 100, 1)})
    else:
        out["status"] = None
    return out


def status_for_user(user: dict) -> dict:
    """Everything the check-in page needs."""
    _expire_old()
    uid = user["id"]
    today = now().date().isoformat()
    todays = db.rows("SELECT * FROM physio_readings WHERE user_id=? AND created_at>=? ORDER BY created_at", (uid, today))
    base = analysis.physio_baseline_for(uid)
    slots = {s: None for s in SLOTS}
    for r in todays:
        slots[r["slot"]] = _reading_dict(r, base)
    history = db.rows("SELECT * FROM physio_readings WHERE user_id=? ORDER BY created_at DESC LIMIT 60", (uid,))
    history = [_reading_dict(r, base) for r in reversed(history)]
    summary = analysis.physio_summary(uid)
    return {"consent": bool(user.get("physio_consent")), "devices": my_devices(uid), "slots": slots,
            "suggested_slot": default_slot(), "session": active_session(uid), "summary": summary,
            "history": history, "simulation": ALLOW_SIMULATION}
