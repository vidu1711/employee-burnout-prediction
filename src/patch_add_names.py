"""
patch_add_names.py
--------------------
One-time patch: adds a realistic "name" field to each employee in the
already-generated synthetic dataset, deterministically derived from their
employee_id (so it's stable across runs). Run once -- does not touch
scoring logic, features, or the trained model, since names don't affect
any of the three signals.
"""

import json
import hashlib
import os

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "synthetic_employees.json")

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Krishna",
    "Ishaan", "Rohan", "Karthik", "Aryan", "Dhruv", "Kabir", "Nikhil",
    "Ananya", "Diya", "Isha", "Kavya", "Meera", "Priya", "Riya", "Sneha",
    "Tanvi", "Anjali", "Divya", "Neha", "Pooja", "Shreya", "Swati",
]
LAST_NAMES = [
    "Sharma", "Verma", "Iyer", "Nair", "Menon", "Reddy", "Rao", "Gupta",
    "Patel", "Kulkarni", "Joshi", "Mehta", "Agarwal", "Pillai", "Desai",
    "Bhatt", "Chatterjee", "Banerjee", "Krishnan", "Pandey",
]


def name_for(emp_id: str) -> str:
    h = int(hashlib.md5(emp_id.encode()).hexdigest(), 16)
    first = FIRST_NAMES[h % len(FIRST_NAMES)]
    last = LAST_NAMES[(h // len(FIRST_NAMES)) % len(LAST_NAMES)]
    return f"{first} {last}"


def main():
    with open(DATA_PATH) as f:
        employees = json.load(f)

    for emp in employees:
        emp["name"] = name_for(emp["employee_id"])

    with open(DATA_PATH, "w") as f:
        json.dump(employees, f, indent=2)

    print(f"Patched {len(employees)} employees with names.")
    for e in employees[:5]:
        print(f"  {e['employee_id']}: {e['name']}")


if __name__ == "__main__":
    main()
