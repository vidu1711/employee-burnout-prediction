"""
dashboard.py
-------------
Streamlit dashboard wired to the real pipeline (src/pipeline.py) — every
score used here is computed live by the three-signal scoring + fusion +
trained Random Forest model.

Design choices in this version:
  - Messages are stored in a shared JSON file (src/message_store.py), not
    st.session_state, so a message sent by Admin/HR in one browser session
    is actually visible to the Employee in a different login/session —
    this mirrors how a real internal tool would need shared, persistent
    storage rather than per-tab memory.
  - Admin/HR and Team Lead can message one employee, or broadcast one
    wellbeing check-in to every High-risk employee at once.
  - The Employee's own view deliberately does NOT show their risk level,
    score, or any chart derived from it. Showing someone a "you are High
    risk" label is exactly the kind of thing this project's own ethics
    section argues against. Instead, employees get: a weekly pulse-check
    chatbot (the actual third signal, same as the real Teams bot would
    be), and an inbox of check-in messages from their manager/HR with a
    "schedule a meeting" action. The employee never sees why they were
    reached out to -- only that someone wants to talk.
  - "Employee" login accepts any employee ID present in the dataset with
    a shared demo password, rather than one single hardcoded account --
    standing in for individual company accounts without needing 150 demo
    passwords.

Run with:
    streamlit run dashboard.py
"""

import sys
import os
import json

import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from pipeline import predict_employee  # noqa: E402
import message_store as store  # noqa: E402

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "synthetic_employees.json")

st.set_page_config(page_title="PulseCheck | Wellbeing Dashboard", layout="wide", page_icon="💬")

# ---------------------------------------------------------------------------
# Global styling
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    #MainMenu, footer, header {visibility: hidden;}
    .block-container {padding-top: 1.5rem; max-width: 1100px;}

    .app-header {
        display: flex; justify-content: space-between; align-items: center;
        padding: 0.75rem 1.25rem; background: #ffffff; border: 1px solid #e5e7eb;
        border-radius: 10px; margin-bottom: 1.25rem;
    }
    .app-header .brand {font-size: 1.15rem; font-weight: 700; color: #1f2937;}
    .app-header .brand span {color: #2563eb;}
    .app-header .user-chip {display: flex; align-items: center; gap: 0.6rem; font-size: 0.9rem; color: #374151;}
    .avatar {
        width: 34px; height: 34px; border-radius: 50%; background: #2563eb; color: white;
        display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 0.9rem;
    }
    .kpi-card {background: #ffffff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 1rem 1.1rem;}
    .kpi-label {font-size: 0.8rem; color: #6b7280; margin-bottom: 0.25rem;}
    .kpi-value {font-size: 1.6rem; font-weight: 700; color: #111827;}
    .pill {display: inline-block; padding: 0.2rem 0.65rem; border-radius: 999px; font-size: 0.8rem; font-weight: 600;}
    .pill-low {background: #dcfce7; color: #166534;}
    .pill-medium {background: #fef9c3; color: #854d0e;}
    .pill-high {background: #fee2e2; color: #991b1b;}
    .pill-scheduled {background: #dbeafe; color: #1e40af;}
    .emp-name {font-weight: 600; color: #1f2937; font-size: 0.92rem;}
    .emp-id {color: #9ca3af; font-size: 0.78rem;}
    .chat-bubble-in {background: #f3f4f6; border-radius: 10px; padding: 0.6rem 0.9rem; margin-bottom: 0.5rem;}
    .chat-bubble-out {background: #dbeafe; border-radius: 10px; padding: 0.6rem 0.9rem; margin-bottom: 0.5rem;}
    section[data-testid="stSidebar"] {background: #f9fafb; border-right: 1px solid #e5e7eb;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Data loading (cheap, needed before login to validate employee IDs)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Loading, please wait a moment...")
def load_employees():
    with open(DATA_PATH) as f:
        return json.load(f)


employees_raw = load_employees()
NAME_BY_ID = {e["employee_id"]: e.get("name", e["employee_id"]) for e in employees_raw}
VALID_EMP_IDS = set(NAME_BY_ID.keys())

# ---------------------------------------------------------------------------
# DEMO LOGIN (prototype only)
# Admin / Team Lead: fixed demo accounts.
# Employee: any real employee ID from the roster + shared demo password --
# stands in for each employee having their own company account.
# ---------------------------------------------------------------------------
FIXED_USERS = {
    "admin": {"password": "admin123", "role": "Admin / HR", "display_name": "Priya Menon", "initials": "PM"},
    "lead":  {"password": "lead123",  "role": "Team Lead",  "display_name": "Arjun Rao",   "initials": "AR"},
}
EMPLOYEE_DEMO_PASSWORD = "emp123"

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False


def login_screen():
    st.markdown(
        """
        <div style="text-align:center; margin-top: 3rem;">
            <div style="font-size:2rem; font-weight:800; color:#1f2937;">💬 PulseCheck</div>
            <div style="color:#6b7280; margin-bottom:2rem;">Employee wellbeing &amp; workload dashboard</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _, mid, _ = st.columns([1, 1.1, 1])
    with mid:
        with st.container(border=True):
            st.markdown("#### Sign in")
            with st.form("login_form"):
                username = st.text_input("Username (or your Employee ID, e.g. EMP003)")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Sign in", use_container_width=True)

            if submitted:
                uname = username.strip().lower()
                uname_upper = username.strip().upper()
                if uname in FIXED_USERS and FIXED_USERS[uname]["password"] == password:
                    u = FIXED_USERS[uname]
                    st.session_state.update(
                        logged_in=True, role=u["role"], display_name=u["display_name"],
                        initials=u["initials"], own_employee_id=None,
                    )
                    st.rerun()
                elif uname_upper in VALID_EMP_IDS and password == EMPLOYEE_DEMO_PASSWORD:
                    name = NAME_BY_ID[uname_upper]
                    initials = "".join(p[0] for p in name.split()[:2]).upper()
                    st.session_state.update(
                        logged_in=True, role="Employee", display_name=name,
                        initials=initials, own_employee_id=uname_upper,
                    )
                    st.rerun()
                else:
                    st.error("Incorrect username/employee ID or password.")

        with st.expander("Demo login credentials (for review purposes)"):
            st.markdown(
                f"""
                | Role | Username | Password |
                |---|---|---|
                | Admin / HR | `admin` | `admin123` |
                | Team Lead | `lead` | `lead123` |
                | Employee | any ID, e.g. `EMP003` | `{EMPLOYEE_DEMO_PASSWORD}` |

                Each of the 150 simulated employees ({', '.join(list(VALID_EMP_IDS)[:3])}, ...)
                can sign in with their own ID — this stands in for each employee having
                their own company account.
                """
            )


if not st.session_state.logged_in:
    login_screen()
    st.stop()

# ---------------------------------------------------------------------------
# Run the real pipeline over every employee (cached)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Loading, please wait a moment...")
def run_all_predictions(_employees):
    results = []
    for emp in _employees:
        r = predict_employee(emp)
        results.append({
            "employee_id": r["employee_id"],
            "name": emp.get("name", r["employee_id"]),
            "combined_score": r["rule_based_fusion"]["combined_score"],
            "risk_level": r["ml_prediction"]["predicted_risk"].capitalize(),
            "_full": r,
        })
    return results


results = run_all_predictions(employees_raw)
df = pd.DataFrame([{k: v for k, v in r.items() if k != "_full"} for r in results])


def pill(level: str) -> str:
    cls = {"Low": "pill-low", "Medium": "pill-medium", "High": "pill-high"}.get(level, "")
    return f'<span class="pill {cls}">{level}</span>'


@st.dialog("Send a check-in")
def send_checkin_dialog(emp_id: str, name: str):
    st.caption(
        f"Sending a private message to **{name}**. This is a general wellbeing check-in — "
        "not a mention of any score. They never see a number, only this message."
    )
    default_msg = (
        "Hi, just checking in — no specific reason, just wanted to see how things are going "
        "for you lately. Do you have 15 minutes this week for a quick chat?"
    )
    msg = st.text_area("Message", value=default_msg, height=110, label_visibility="collapsed")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Send", type="primary", use_container_width=True):
            store.send_message(emp_id, st.session_state.display_name, msg, msg_type="checkin")
            st.rerun()
    with c2:
        if st.button("Cancel", use_container_width=True):
            st.rerun()


@st.dialog("Message all High-risk employees")
def send_bulk_dialog(emp_ids: list):
    st.caption(
        f"This sends the **same** private wellbeing check-in to all **{len(emp_ids)}** "
        "employees currently flagged High risk. Each message looks identical and generic "
        "to the recipient — none of them see that they were part of a bulk send or why."
    )
    default_msg = (
        "Hi, just doing a round of check-ins with the team this week — no specific reason. "
        "How have things been going for you lately? Happy to grab 15 minutes if useful."
    )
    msg = st.text_area("Message", value=default_msg, height=110, label_visibility="collapsed")
    c1, c2 = st.columns(2)
    with c1:
        if st.button(f"Send to all {len(emp_ids)}", type="primary", use_container_width=True):
            store.send_bulk(emp_ids, st.session_state.display_name, msg, msg_type="checkin")
            st.rerun()
    with c2:
        if st.button("Cancel", use_container_width=True):
            st.rerun()


def employee_action_row(emp_id: str, name: str, risk_level: str, key_prefix: str):
    thread = store.get_thread(emp_id)
    sent_count = len([m for m in thread if m["type"] == "checkin"])
    meeting = store.latest_of_type(emp_id, "meeting_scheduled")

    c1, c2, c3 = st.columns([2.4, 1, 1.3])
    with c1:
        st.markdown(f'<span class="emp-name">{name}</span> <span class="emp-id">{emp_id}</span>', unsafe_allow_html=True)
        if meeting:
            st.markdown(f'<span class="pill pill-scheduled">📅 Meeting: {meeting["extra_date"]} {meeting["extra_time"]}</span>' if "extra_date" in meeting else "", unsafe_allow_html=True)
    with c2:
        st.markdown(pill(risk_level), unsafe_allow_html=True)
    with c3:
        if st.button("💬 Message", key=f"{key_prefix}_{emp_id}", use_container_width=True):
            send_checkin_dialog(emp_id, name)
        if sent_count:
            st.caption(f"✓ {sent_count} sent")


# ---------------------------------------------------------------------------
# Top header
# ---------------------------------------------------------------------------
hc1, hc2 = st.columns([3, 1])
with hc1:
    st.markdown(
        f'<div class="app-header"><div class="brand">💬 Pulse<span>Check</span></div>'
        f'<div class="user-chip"><div class="avatar">{st.session_state.initials}</div>'
        f'<div><b>{st.session_state.display_name}</b><br><span style="color:#6b7280;">{st.session_state.role}</span></div></div></div>',
        unsafe_allow_html=True,
    )
with hc2:
    st.write("")
    if st.button("Log out", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()

role = st.session_state.role

# ---------------------------------------------------------------------------
# ADMIN / HR VIEW
# ---------------------------------------------------------------------------
if role == "Admin / HR":
    st.subheader("Organization Overview")

    k1, k2, k3, k4 = st.columns(4)
    for col, label, value in zip(
        [k1, k2, k3, k4],
        ["Total Employees", "High Risk", "Medium Risk", "Low Risk"],
        [len(df), int((df.risk_level == "High").sum()), int((df.risk_level == "Medium").sum()), int((df.risk_level == "Low").sum())],
    ):
        with col:
            st.markdown(f'<div class="kpi-card"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div></div>', unsafe_allow_html=True)

    st.write("")
    st.markdown("##### Risk Distribution")
    risk_counts = df["risk_level"].value_counts().reindex(["Low", "Medium", "High"]).fillna(0)
    st.bar_chart(risk_counts, height=220)

    with st.expander("How is this calculated?"):
        st.markdown(
            """
            Each employee's risk level combines three signals — message tone, workload
            pattern, and their own weekly self-reported check-in — then a trained model
            classifies the result as Low, Medium, or High. Raw numeric scores aren't shown
            here since they aren't directly actionable — the risk level is what should
            prompt a conversation.
            """
        )

    st.write("")
    high_risk = df[df["risk_level"] == "High"]
    hdr_c1, hdr_c2 = st.columns([3, 1.4])
    with hdr_c1:
        st.markdown("##### Employees Needing Follow-Up")
    with hdr_c2:
        if len(high_risk) > 0 and st.button("📣 Message all High-risk", use_container_width=True):
            send_bulk_dialog(high_risk["employee_id"].tolist())

    needs_attention = df[df["risk_level"].isin(["Medium", "High"])].sort_values("combined_score", ascending=False)
    if needs_attention.empty:
        st.success("No employees currently flagged Medium or High risk.")
    else:
        for _, row in needs_attention.iterrows():
            employee_action_row(row["employee_id"], row["name"], row["risk_level"], key_prefix="admin")

    with st.expander(f"View all {len(df)} employees"):
        all_df = df[["name", "employee_id", "risk_level"]].copy()
        all_df["Risk"] = all_df["risk_level"].apply(pill)
        st.write(
            all_df[["name", "employee_id", "Risk"]].rename(columns={"name": "Name", "employee_id": "ID"}).to_html(escape=False, index=False),
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# TEAM LEAD VIEW
# ---------------------------------------------------------------------------
elif role == "Team Lead":
    st.subheader("My Team")
    st.caption("Scoped to your direct reports in a real deployment.")

    team_df = df.sample(n=min(10, len(df)), random_state=1).sort_values("combined_score", ascending=False)

    high_risk_team = team_df[team_df["risk_level"] == "High"]
    if len(high_risk_team) > 0:
        if st.button("📣 Message all High-risk on my team", use_container_width=False):
            send_bulk_dialog(high_risk_team["employee_id"].tolist())

    for _, row in team_df.iterrows():
        employee_action_row(row["employee_id"], row["name"], row["risk_level"], key_prefix="lead")

    if len(high_risk_team) == 0:
        st.success("No High-risk team members this period.")

# ---------------------------------------------------------------------------
# EMPLOYEE VIEW — chatbot-style check-in, no risk label ever shown
# ---------------------------------------------------------------------------
else:
    emp_id = st.session_state.own_employee_id
    st.subheader(f"Hi {st.session_state.display_name.split()[0]} 👋")

    # --- Weekly pulse-check chatbot ---
    st.markdown("##### Weekly check-in")
    already_answered = store.latest_of_type(emp_id, "pulse_response")
    with st.container(border=True):
        st.markdown('<div class="chat-bubble-in">🤖 <b>PulseBot:</b> How are you feeling about work this week?</div>', unsafe_allow_html=True)
        if already_answered:
            st.markdown(f'<div class="chat-bubble-out">You: {already_answered["text"]}</div>', unsafe_allow_html=True)
            st.caption("Thanks — your answer has been recorded for this week.")
        else:
            moods = ["😊 Great", "🙂 Good", "😐 Okay", "😟 Stressed", "😫 Overwhelmed"]
            cols = st.columns(len(moods))
            for col, mood in zip(cols, moods):
                with col:
                    if st.button(mood, use_container_width=True, key=f"mood_{mood}"):
                        store.add_response(emp_id, st.session_state.display_name, mood, msg_type="pulse_response")
                        st.rerun()

    # --- Inbox from manager/HR ---
    st.write("")
    st.markdown("##### Messages")
    thread = [m for m in store.get_thread(emp_id) if m["type"] in ("checkin", "meeting_scheduled")]
    if not thread:
        st.caption("No messages yet.")
    else:
        for i, m in enumerate(thread):
            if m["type"] == "checkin":
                with st.container(border=True):
                    st.markdown(f"**{m['from']}** · {m['time']}")
                    st.write(m["text"])
                    if st.button("📅 Schedule a meeting", key=f"sched_{i}"):
                        st.session_state[f"show_scheduler_{i}"] = True
                    if st.session_state.get(f"show_scheduler_{i}"):
                        d = st.date_input("Date", key=f"date_{i}")
                        t = st.time_input("Time", key=f"time_{i}")
                        if st.button("Confirm", key=f"confirm_{i}"):
                            store.add_response(
                                emp_id, st.session_state.display_name,
                                f"Meeting scheduled for {d} at {t}",
                                msg_type="meeting_scheduled",
                                extra={"extra_date": str(d), "extra_time": str(t)},
                            )
                            st.success("Meeting scheduled — your manager/HR will see this confirmed.")
                            st.session_state[f"show_scheduler_{i}"] = False
                            st.rerun()
            elif m["type"] == "meeting_scheduled":
                st.info(f"📅 {m['text']}")

    st.caption(
        "Your manager and HR only see that a check-in was sent and whether a meeting "
        "was scheduled — they don't see your mood answers or any risk score here."
    )
