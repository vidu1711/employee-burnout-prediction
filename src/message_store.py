"""
message_store.py
------------------
Tiny JSON-file-backed message store shared across all dashboard sessions.

Why this exists: Streamlit's st.session_state is per-browser-session, not
shared between users. In the demo, Admin/HR, Team Lead, and Employee are
opened as separate logins (often separate browser tabs), so a message sent
by Admin needs to live somewhere both sessions can read -- a flat JSON file
plays that role here, standing in for a real database/messaging backend.
"""

import json
import os
import threading
from datetime import datetime

STORE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "messages.json")
_lock = threading.Lock()


def _load() -> dict:
    if not os.path.exists(STORE_PATH):
        return {}
    with open(STORE_PATH) as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _save(data: dict) -> None:
    with open(STORE_PATH, "w") as f:
        json.dump(data, f, indent=2)


def get_thread(emp_id: str) -> list:
    with _lock:
        return _load().get(emp_id, [])


def _append(data: dict, emp_id: str, entry: dict) -> None:
    data.setdefault(emp_id, []).append(entry)


def send_message(emp_id: str, frm: str, text: str, msg_type: str = "checkin") -> None:
    with _lock:
        data = _load()
        _append(data, emp_id, {
            "from": frm, "text": text, "type": msg_type,
            "time": datetime.now().strftime("%d %b, %I:%M %p"),
        })
        _save(data)


def send_bulk(emp_ids: list, frm: str, text: str, msg_type: str = "checkin") -> None:
    with _lock:
        data = _load()
        for emp_id in emp_ids:
            _append(data, emp_id, {
                "from": frm, "text": text, "type": msg_type,
                "time": datetime.now().strftime("%d %b, %I:%M %p"),
            })
        _save(data)


def add_response(emp_id: str, frm: str, text: str, msg_type: str = "response", extra: dict = None) -> None:
    with _lock:
        data = _load()
        entry = {
            "from": frm, "text": text, "type": msg_type,
            "time": datetime.now().strftime("%d %b, %I:%M %p"),
        }
        if extra:
            entry.update(extra)
        _append(data, emp_id, entry)
        _save(data)


def latest_of_type(emp_id: str, msg_type: str):
    thread = get_thread(emp_id)
    matches = [m for m in thread if m.get("type") == msg_type]
    return matches[-1] if matches else None
