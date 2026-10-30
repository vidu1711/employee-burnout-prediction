"""
app.py -- PulseCheck web app (FastAPI).

Run:  python -m webapp.run        (or: uvicorn webapp.app:app)
"""

import os
import re
import threading
from datetime import datetime, date, timedelta

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_env():
    """Tiny .env reader so the API key can live in a file next to the app."""
    for path in (os.path.join(HERE, ".env"), os.path.join(os.path.dirname(HERE), ".env")):
        if os.path.exists(path):
            for line in open(path, encoding="utf-8"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

from . import analysis, chatbot, db, physio, security, seed, services  # noqa: E402

app = FastAPI(title="PulseCheck", docs_url=None, redoc_url=None)


class NoCacheStatic(StaticFiles):
    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


app.mount("/static", NoCacheStatic(directory=os.path.join(HERE, "static")), name="static")


@app.on_event("startup")
def _startup():
    db.init()
    seed.seed_if_empty()
    physio.ensure_shared_device()
    seed.seed_physio_if_needed()

    def warm():  # compute everyone's wellbeing once so the first dashboard opens fast
        try:
            for r in db.rows("SELECT id FROM users WHERE role='employee'"):
                analysis.predict_user(r["id"])
        except Exception as exc:  # pragma: no cover
            print("[pulsecheck] warm-up skipped:", exc)
    threading.Thread(target=warm, daemon=True).start()


@app.exception_handler(services.ServiceError)
async def _service_error(request: Request, exc: services.ServiceError):
    return JSONResponse({"detail": str(exc)}, status_code=exc.status)


# ---------------------------------------------------------------- schemas
class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)


class SignupIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    username: str = Field(min_length=3, max_length=30, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=200)


class MessageIn(BaseModel):
    to_id: int
    text: str = Field(min_length=1, max_length=2000)


class MeetingIn(BaseModel):
    title: str = Field(default="Meeting", max_length=80)
    date: str
    start: str
    end: str
    invitee_ids: list = Field(default_factory=list, max_length=20)
    kind: str = "meeting"


class MoodIn(BaseModel):
    label: str
    note: str | None = Field(default=None, max_length=500)


class CheckinIn(BaseModel):
    employee_ids: list = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=1000)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class SettingsIn(BaseModel):
    consent: bool | None = None
    physio_consent: bool | None = None


class SessionIn(BaseModel):
    slot: str | None = None
    device_id: str | None = None


class SimulateIn(BaseModel):
    slot: str | None = None
    mode: str = "normal"          # normal | elevated | baseline


class DeviceIn(BaseModel):
    label: str | None = Field(default=None, max_length=40)


class DeviceReadingIn(BaseModel):
    session_id: int
    valid: bool = True
    reason: str | None = None
    hr: float | None = None
    gsr: float | None = None
    quality: float | None = None
    n_samples: int | None = None


class PasswordIn(BaseModel):
    old: str
    new: str = Field(min_length=8, max_length=200)


class UserAdminIn(BaseModel):
    role: str | None = None
    team_id: int | None = None


def _set_session(resp: Response, token: str):
    resp.set_cookie(security.COOKIE, token, httponly=True, samesite="lax", max_age=security.SESSION_DAYS * 86400, path="/")


def _me(user_id: int) -> dict:
    return services.public_user(services.get_user(user_id))


# ------------------------------------------------------------------- pages
@app.get("/", include_in_schema=False)
def index():
    return FileResponse(os.path.join(HERE, "static", "index.html"), headers={"Cache-Control": "no-store"})


@app.get("/api/health")
def health():
    return {"ok": True}


# -------------------------------------------------------------------- auth
@app.post("/api/auth/login")
def login(body: LoginIn, response: Response):
    uname = body.username.strip().lower()
    security.throttle_check(uname)
    user = db.one("SELECT * FROM users WHERE username=?", (uname,))
    if not user or not security.verify_password(body.password, user["password_hash"]):
        security.throttle_fail(uname)
        raise HTTPException(401, "That username and password don't match.")
    security.throttle_clear(uname)
    _set_session(response, security.create_session(user["id"]))
    return {"user": _me(user["id"])}


@app.post("/api/auth/signup")
def signup(body: SignupIn, response: Response):
    uname = body.username.strip().lower()
    if db.one("SELECT id FROM users WHERE username=?", (uname,)):
        raise HTTPException(409, "That username is taken. Try another.")
    team = db.one("SELECT t.id FROM teams t LEFT JOIN users u ON u.team_id=t.id AND u.role='employee' "
                  "GROUP BY t.id ORDER BY COUNT(u.id), t.id LIMIT 1")
    uid = db.run("INSERT INTO users(username, password_hash, name, role, team_id, consent, created_at) VALUES (?,?,?,?,?,1,?)",
                 (uname, security.hash_password(body.password), body.name.strip(), "employee", team["id"] if team else None,
                  services.iso(services.now())))
    db.run("UPDATE users SET emp_code=? WHERE id=?", (f"EMP{uid:03d}", uid))
    _set_session(response, security.create_session(uid))
    return {"user": _me(uid)}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(security.COOKIE)
    if token:
        security.end_session(token)
    response.delete_cookie(security.COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: dict = Depends(security.current_user)):
    return {"user": services.public_user(user)}


@app.patch("/api/me/settings")
def settings(body: SettingsIn, user: dict = Depends(security.current_user)):
    if body.consent is not None:
        db.run("UPDATE users SET consent=? WHERE id=?", (1 if body.consent else 0, user["id"]))
        analysis.touch(user["id"])
    if body.physio_consent is not None:
        db.run("UPDATE users SET physio_consent=? WHERE id=?", (1 if body.physio_consent else 0, user["id"]))
        analysis.touch(user["id"])
    return {"user": _me(user["id"])}


@app.post("/api/me/password")
def change_password(body: PasswordIn, user: dict = Depends(security.current_user)):
    if not security.verify_password(body.old, user["password_hash"]):
        raise HTTPException(400, "Your current password isn't right.")
    db.run("UPDATE users SET password_hash=? WHERE id=?", (security.hash_password(body.new), user["id"]))
    return {"ok": True}


@app.get("/api/notifications")
def notifications(user: dict = Depends(security.current_user)):
    return {"unread_messages": services.unread_count(user["id"]),
            "unread_checkins": db.scalar("SELECT COUNT(*) FROM messages WHERE recipient_id=? AND kind='checkin' AND is_read=0",
                                         (user["id"],), 0)}


# ------------------------------------------------------------------ people
@app.get("/api/people")
def people(q: str = "", user: dict = Depends(security.current_user)):
    return {"people": services.people_search(q, 25, exclude_id=user["id"])}


# ---------------------------------------------------------------- messages
@app.get("/api/conversations")
def conversations(user: dict = Depends(security.current_user)):
    return {"conversations": services.conversations(user["id"])}


@app.get("/api/messages/{other_id}")
def get_thread(other_id: int, after: int = 0, user: dict = Depends(security.current_user)):
    return services.thread(user["id"], other_id, after)


@app.post("/api/messages")
def post_message(body: MessageIn, user: dict = Depends(security.current_user)):
    return {"message": services.create_message(user, body.to_id, body.text)}


# ---------------------------------------------------------------- schedule
def _parse_day(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except Exception:
        raise HTTPException(400, "Use a date like 2026-10-12.")


@app.get("/api/schedule")
def schedule(week: str | None = None, user: dict = Depends(security.current_user)):
    d = _parse_day(week) if week else services.now().date()
    return services.week_view(user["id"], analysis.monday_of(d))


@app.post("/api/schedule")
def add_meeting(body: MeetingIn, user: dict = Depends(security.current_user)):
    day = _parse_day(body.date)
    try:
        sh, sm = map(int, body.start.split(":")[:2])
        eh, em = map(int, body.end.split(":")[:2])
    except Exception:
        raise HTTPException(400, "Times should look like 14:30.")
    base = datetime.combine(day, datetime.min.time())
    kind = body.kind if body.kind in ("meeting", "wellbeing") else "meeting"
    ids = [int(i) for i in body.invitee_ids]
    return services.create_meeting(user, body.title, base.replace(hour=sh, minute=sm), base.replace(hour=eh, minute=em), ids, kind)


@app.delete("/api/schedule/{meeting_id}")
def remove_meeting(meeting_id: int, user: dict = Depends(security.current_user)):
    services.delete_meeting(user, meeting_id)
    return {"ok": True}


# ------------------------------------------------------- my own wellbeing
@app.get("/api/me/insights")
def insights(user: dict = Depends(security.current_user)):
    return services.my_insights(user)


@app.post("/api/mood")
def mood(body: MoodIn, user: dict = Depends(security.current_user)):
    return services.log_mood(user["id"], body.label, body.note)


# ------------------------------------------------------ leads and admins
managers = security.require_roles("lead", "admin")
admins = security.require_roles("admin")


@app.get("/api/manager/overview")
def manager_overview(user: dict = Depends(managers)):
    return services.overview(user)


@app.get("/api/manager/employees")
def manager_employees(q: str = "", risk: str = "", team_id: int = 0, user: dict = Depends(managers)):
    rows = services.manager_rows(user)
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r["name"].lower() or ql in (r["emp_code"] or "").lower()]
    if risk in ("High", "Medium", "Low"):
        rows = [r for r in rows if r["risk"] == risk]
    if team_id:
        rows = [r for r in rows if r["team_id"] == team_id]
    rows.sort(key=lambda r: (["High", "Medium", "Low"].index(r["risk"]), -r["score"]))
    return {"employees": rows, "total": len(rows)}


@app.get("/api/manager/employees/{emp_id}")
def manager_employee(emp_id: int, user: dict = Depends(managers)):
    return services.employee_detail(user, emp_id)


@app.post("/api/manager/checkins")
def manager_checkins(body: CheckinIn, user: dict = Depends(managers)):
    return services.send_checkins(user, [int(i) for i in body.employee_ids], body.text)


# ------------------------------------------------------------------- admin
@app.get("/api/admin/users")
def admin_users(q: str = "", limit: int = 60, user: dict = Depends(admins)):
    like = f"%{q.lower()}%"
    rows = db.rows(
        "SELECT u.id, u.name, u.username, u.role, u.team_id, t.name AS team, u.emp_code FROM users u LEFT JOIN teams t ON t.id=u.team_id "
        "WHERE lower(u.name) LIKE ? OR lower(u.username) LIKE ? OR lower(IFNULL(u.emp_code,'')) LIKE ? "
        "ORDER BY CASE u.role WHEN 'admin' THEN 0 WHEN 'lead' THEN 1 ELSE 2 END, u.name LIMIT ?",
        (like, like, like, min(limit, 200)))
    teams = db.rows("SELECT t.id, t.name, u.name AS lead FROM teams t LEFT JOIN users u ON u.id=t.lead_id ORDER BY t.name")
    return {"users": rows, "teams": teams, "total": db.scalar("SELECT COUNT(*) FROM users", (), 0)}


@app.patch("/api/admin/users/{uid}")
def admin_update_user(uid: int, body: UserAdminIn, user: dict = Depends(admins)):
    target = services.get_user(uid)
    if not target:
        raise HTTPException(404, "That user doesn't exist.")
    if body.role is not None:
        if body.role not in ("employee", "lead", "admin"):
            raise HTTPException(400, "Role must be employee, lead or admin.")
        if uid == user["id"] and body.role != "admin":
            raise HTTPException(400, "You can't remove your own admin access.")
        db.run("UPDATE users SET role=? WHERE id=?", (body.role, uid))
        if body.role != "lead":
            db.run("UPDATE teams SET lead_id=NULL WHERE lead_id=?", (uid,))
    if body.team_id is not None:
        if not db.one("SELECT id FROM teams WHERE id=?", (body.team_id,)):
            raise HTTPException(400, "That team doesn't exist.")
        db.run("UPDATE users SET team_id=? WHERE id=?", (body.team_id, uid))
    t = services.get_user(uid)
    if t["role"] == "lead" and t["team_id"]:
        db.run("UPDATE teams SET lead_id=? WHERE id=?", (uid, t["team_id"]))
    return {"user": services.public_user(t)}


# --------------------------------------------------------------------- chat
# ---------------------------------------------------------------- body check-ins
def _device(request: Request) -> dict:
    return physio.authenticate_device(request.headers.get("X-Device-Id"), request.headers.get("X-Device-Key"))


@app.get("/api/device/poll")
def device_poll(request: Request):
    return physio.device_poll(_device(request))


class DeviceProgressIn(BaseModel):
    session_id: int
    phase: str = "measuring"


@app.post("/api/device/progress")
def device_progress(body: DeviceProgressIn, request: Request):
    return physio.device_progress(_device(request), body.model_dump())


@app.post("/api/device/readings")
def device_readings(body: DeviceReadingIn, request: Request):
    return physio.device_report(_device(request), body.model_dump())


@app.get("/api/physio/status")
def physio_status(user: dict = Depends(security.current_user)):
    return physio.status_for_user(user)


@app.post("/api/physio/sessions")
def physio_start(body: SessionIn, user: dict = Depends(security.current_user)):
    return {"session": physio.start_session(user, body.slot, body.device_id)}


@app.get("/api/physio/sessions/{sid}")
def physio_session(sid: int, user: dict = Depends(security.current_user)):
    return {"session": physio.get_session(user, sid)}


@app.delete("/api/physio/sessions/{sid}")
def physio_cancel(sid: int, user: dict = Depends(security.current_user)):
    physio.cancel_session(user, sid)
    return {"ok": True}


@app.post("/api/physio/simulate")
def physio_simulate(body: SimulateIn, user: dict = Depends(security.current_user)):
    if body.mode == "baseline":
        return physio.simulate_baseline(user)
    return physio.simulate(user, body.slot, "elevated" if body.mode == "elevated" else "normal")


@app.post("/api/physio/devices")
def physio_register(body: DeviceIn, user: dict = Depends(security.current_user)):
    return physio.register_device(user, body.label)


@app.delete("/api/physio/devices/{device_id}")
def physio_remove(device_id: str, user: dict = Depends(security.current_user)):
    physio.remove_device(user, device_id)
    return {"ok": True}


@app.get("/api/chat/status")
def chat_status(user: dict = Depends(security.current_user)):
    return chatbot.status()


@app.get("/api/chat/history")
def chat_history(user: dict = Depends(security.current_user)):
    return {"messages": chatbot.history(user["id"]), **chatbot.status()}


@app.post("/api/chat")
def chat(body: ChatIn, user: dict = Depends(security.current_user)):
    out = chatbot.chat(user, body.message)
    return {"reply": out["reply"], "tools": out["tool_labels"], "suggestions": out.get("suggestions", []),
            "mode": out["mode"], "notice": out.get("notice")}


@app.delete("/api/chat/history")
def chat_clear(user: dict = Depends(security.current_user)):
    chatbot.clear_history(user["id"])
    return {"ok": True}
