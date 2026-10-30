"""
generate_dataset.py
--------------------
Builds a synthetic but realistic dataset of employee communications,
calendar/workload patterns, and weekly pulse-check responses.

Why synthetic: there is no real company data available at the student-project
stage (no consenting organization, no IT access). This mirrors how the
project's speech Q&A already explains the data source honestly.

Each simulated employee is generated from a hidden "true burnout state"
(Low / Medium / High) which drives all three signals probabilistically,
so the final dataset has a realistic, learnable, non-trivial relationship
between the three signals and the eventual label.
"""

import json
import random
import os

random.seed(42)

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(OUT_DIR, exist_ok=True)

N_EMPLOYEES = 150
WEEKS = 6

# ---------------------------------------------------------------------------
# Message banks per burnout state (used to build realistic weekly messages)
# ---------------------------------------------------------------------------
MESSAGES = {
    "low": [
        "Had a productive day, finished everything on my list.",
        "Great sprint planning meeting, feeling good about the roadmap.",
        "Shipped the feature today, team worked really well together.",
        "Looking forward to the weekend after a solid week.",
        "Caught up on all my emails, nothing urgent pending.",
        "Really enjoyed the brainstorming session this morning.",
        "Things are on track, no blockers this week.",
        "Happy with how the demo went today.",
    ],
    "medium": [
        "Pretty busy week, a lot of meetings back to back.",
        "Trying to keep up with the backlog, slowly getting there.",
        "Bit tired today but managed to finish the main task.",
        "Workload has picked up, hoping it settles down soon.",
        "Long day, but we got the release out.",
        "Feeling a little stretched thin this sprint.",
        "Need to prioritize better, too many things at once.",
        "Okay day, nothing major, just a lot to juggle.",
    ],
    "high": [
        "I'm exhausted, I can't keep up with this workload anymore.",
        "Nothing I do seems to matter anymore, just feels pointless.",
        "I feel completely drained, haven't had a proper break in weeks.",
        "I'm so tired all the time, dreading coming to work now.",
        "I can't focus on anything today, just feel numb.",
        "This is too much, I don't know how much longer I can keep this pace.",
        "I feel disconnected from the team lately, just going through the motions.",
        "Another late night, I'm running on empty at this point.",
    ],
}

# ---------------------------------------------------------------------------
# Pulse-check phrasing per state
# ---------------------------------------------------------------------------
PULSE_OPTIONS = {
    "low": [("great", 5), ("good", 4)],
    "medium": [("okay", 3), ("stressed", 2)],
    "high": [("stressed", 2), ("overwhelmed", 1)],
}


def sample_true_state():
    """Roughly realistic org distribution: most people are fine."""
    r = random.random()
    if r < 0.55:
        return "low"
    elif r < 0.85:
        return "medium"
    else:
        return "high"


def generate_employee(emp_id):
    true_state = sample_true_state()

    # --- Signal 1: weekly messages (message tone / semantic signal) ---
    weekly_messages = []
    for week in range(WEEKS):
        # occasionally drift state slightly week to week for realism
        state_this_week = true_state
        if random.random() < 0.15:
            states = ["low", "medium", "high"]
            state_this_week = random.choice(states)
        n_msgs = random.randint(2, 4)
        msgs = random.sample(
            MESSAGES[state_this_week], k=min(n_msgs, len(MESSAGES[state_this_week]))
        )
        weekly_messages.append({"week": week + 1, "messages": msgs})

    # --- Signal 2: workload / calendar pattern ---
    base_meetings = {"low": 3, "medium": 5, "high": 7}[true_state]
    base_afterhours = {"low": 0.5, "medium": 2, "high": 5}[true_state]
    daily_meetings = []
    for week in range(WEEKS):
        week_days = [
            max(0, round(random.gauss(base_meetings, 1.2))) for _ in range(5)
        ]
        daily_meetings.append(week_days)
    after_hours_hours_per_week = [
        max(0, round(random.gauss(base_afterhours, 1.5), 1)) for _ in range(WEEKS)
    ]

    # --- Signal 3: weekly pulse-check (self-reported) ---
    pulse_checks = []
    for week in range(WEEKS):
        state_this_week = true_state
        if random.random() < 0.1:
            states = ["low", "medium", "high"]
            state_this_week = random.choice(states)
        label, val = random.choice(PULSE_OPTIONS[state_this_week])
        missed = random.random() < 0.08  # occasionally skip the check-in
        pulse_checks.append(
            {"week": week + 1, "missed": missed, "label": label if not missed else None,
             "value": val if not missed else None}
        )

    return {
        "employee_id": f"EMP{emp_id:03d}",
        "true_burnout_state": true_state,  # ground truth, used only for training/eval
        "weekly_messages": weekly_messages,
        "daily_meetings_per_week": daily_meetings,
        "after_hours_hours_per_week": after_hours_hours_per_week,
        "pulse_checks": pulse_checks,
    }


def main():
    employees = [generate_employee(i + 1) for i in range(N_EMPLOYEES)]

    out_path = os.path.join(OUT_DIR, "synthetic_employees.json")
    with open(out_path, "w") as f:
        json.dump(employees, f, indent=2)

    # quick distribution summary
    from collections import Counter
    dist = Counter(e["true_burnout_state"] for e in employees)
    print(f"Generated {len(employees)} employees -> {out_path}")
    print(f"True state distribution: {dict(dist)}")


if __name__ == "__main__":
    main()
