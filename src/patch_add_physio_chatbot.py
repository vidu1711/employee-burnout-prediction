"""
patch_add_physio_chatbot.py
-----------------------------
One-time patch: adds two new synthetic signals to every employee in
data/synthetic_employees.json, without touching the existing three:

  physio_readings   14 days of morning / afternoon / evening device check-ins
                    (heart rate in bpm, skin conductance in raw ADC units)
  chatbot_weekly    6 weeks of messages the employee typed to the chatbot

HONEST NOTE ABOUT THIS DATA: the effect sizes below (how far heart rate and
skin conductance rise for a stressed person) are ASSUMPTIONS chosen to be
plausible, not measured values. With real sensors they must be re-estimated.
A realistic share of employees (about 30%) has no device readings at all, and
about 25% never use the chatbot, so the model also learns to cope with missing
signals.

Design choice: stress shows up mostly in the LAST 3 DAYS (a recent change),
and only weakly in the older days that form the personal baseline.

Deterministic (own random generator), safe to run again: it overwrites its own fields.
"""

import json
import os
import random

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "synthetic_employees.json")

# (mean, sd) of the change in heart rate (bpm) and the relative change in skin conductance
HR_SHIFT = {"low": (1.0, 4.0), "medium": (6.0, 5.0), "high": (14.0, 6.0)}
GSR_SHIFT = {"low": (0.03, 0.12), "medium": (0.15, 0.18), "high": (0.40, 0.22)}
OLD_DAYS_SHARE = 0.3        # older days only carry 30% of the effect

CHAT = {
    "low": ["Can you show me my schedule for tomorrow?", "Find me a free hour on Thursday.",
            "Thanks, that was really helpful.", "What's on my calendar today?",
            "Doing well, just checking how my week looks."],
    "medium": ["I have a lot of meetings this week, can you help me find some free time?",
               "Feeling a bit stretched, is there any way to lighten Wednesday?",
               "I'm tired today but managing.", "Too many things at once, I need to prioritise.",
               "Long day again, back to back calls."],
    "high": ["I feel completely overwhelmed and I'm exhausted all the time.",
             "I dread opening my inbox, there is just too much and I can't keep up.",
             "I can't cope with this workload anymore, I'm drained.",
             "Nothing feels worth the effort, I'm just going through the motions.",
             "I haven't had a proper break in weeks and I'm running on empty."],
}
SLOTS = ["morning", "afternoon", "evening"]


def build(emp, rng):
    state = emp["true_burnout_state"]
    # ---- device readings
    readings = []
    if rng.random() < 0.70:                       # 70% of employees use the device
        hr_base = min(90, max(56, rng.gauss(72, 6)))
        gsr_base = min(650, max(250, rng.gauss(420, 70)))
        adherence = rng.uniform(0.5, 0.85)
        for days_ago in range(13, -1, -1):
            for slot in SLOTS:
                if rng.random() > adherence:
                    continue
                share = 1.0 if days_ago < 3 else OLD_DAYS_SHARE
                hr = hr_base + share * rng.gauss(*HR_SHIFT[state]) + rng.gauss(0, 2.0)
                gsr = gsr_base * (1 + share * rng.gauss(*GSR_SHIFT[state]) + rng.gauss(0, 0.04))
                readings.append({"days_ago": days_ago + rng.random() * 0.8, "slot": slot,
                                 "hr": round(hr, 1), "gsr": round(gsr, 1)})
    emp["physio_readings"] = readings

    # ---- chatbot conversations
    weekly = []
    uses_bot = rng.random() < 0.75
    for w in range(6):
        msgs = []
        if uses_bot:
            this_state = state
            if rng.random() < 0.15:
                this_state = rng.choice(["low", "medium", "high"])
            n = rng.choice([0, 1, 1, 2, 3])
            msgs = rng.sample(CHAT[this_state], k=min(n, len(CHAT[this_state])))
        weekly.append({"week": w + 1, "messages": msgs})
    emp["chatbot_weekly"] = weekly


def main():
    with open(DATA_PATH) as f:
        employees = json.load(f)
    rng = random.Random(20261006)
    for emp in employees:
        build(emp, rng)
    with open(DATA_PATH, "w") as f:
        json.dump(employees, f, indent=2)
    with_dev = sum(1 for e in employees if e["physio_readings"])
    with_bot = sum(1 for e in employees if any(w["messages"] for w in e["chatbot_weekly"]))
    print(f"Patched {len(employees)} employees: {with_dev} with device readings, {with_bot} with chatbot messages.")


if __name__ == "__main__":
    main()
