"""
signal_workload.py
--------------------
Signal 2: Workload / calendar pattern analysis.

Uses meeting density (meetings per day) and after-hours work hours per week,
compared against each employee's own personal baseline from their earliest
weeks, since "too many meetings" is relative to a person's normal pattern,
not an absolute number. A sudden increase relative to one's own baseline is
a stronger burnout indicator than a fixed threshold.

Output: a 0-100 "workload risk" score per employee, higher = heavier/more
escalating workload.
"""

import numpy as np


def score_employee_workload(daily_meetings_per_week: list, after_hours_hours_per_week: list) -> dict:
    """
    daily_meetings_per_week: list of weeks, each a list of meeting counts per day
    after_hours_hours_per_week: list of after-hours hours, one value per week
    """
    weekly_meeting_totals = [sum(week) for week in daily_meetings_per_week]
    weekly_meeting_avg = [np.mean(week) for week in daily_meetings_per_week]

    n_weeks = len(weekly_meeting_totals)
    if n_weeks < 2:
        baseline_meetings = weekly_meeting_totals[0] if weekly_meeting_totals else 0
        baseline_afterhours = after_hours_hours_per_week[0] if after_hours_hours_per_week else 0
    else:
        # baseline = average of the first 2 weeks (employee's own "normal")
        baseline_meetings = float(np.mean(weekly_meeting_totals[:2]))
        baseline_afterhours = float(np.mean(after_hours_hours_per_week[:2]))

    recent_meetings = float(np.mean(weekly_meeting_totals[-2:]))
    recent_afterhours = float(np.mean(after_hours_hours_per_week[-2:]))

    # % increase over own baseline (guard against div-by-zero)
    meeting_increase_pct = ((recent_meetings - baseline_meetings) / baseline_meetings * 100
                             if baseline_meetings > 0 else 0)
    afterhours_increase_pct = ((recent_afterhours - baseline_afterhours) / baseline_afterhours * 100
                                if baseline_afterhours > 0 else (100 if recent_afterhours > 0 else 0))

    # absolute load also matters (someone with 8 meetings/day is at risk
    # regardless of baseline)
    absolute_meeting_load = min(100, (recent_meetings / 35) * 100)  # 35 meetings/wk (7/day) -> 100
    absolute_afterhours_load = min(100, (recent_afterhours / 10) * 100)  # 10 hrs/wk after-hours -> 100

    # relative escalation score (capped)
    relative_meeting_escalation = max(0, min(100, meeting_increase_pct))
    relative_afterhours_escalation = max(0, min(100, afterhours_increase_pct))

    # Blend: 50% absolute load, 50% escalation relative to own baseline
    workload_risk_score = round(
        0.25 * absolute_meeting_load
        + 0.25 * absolute_afterhours_load
        + 0.25 * relative_meeting_escalation
        + 0.25 * relative_afterhours_escalation,
        1,
    )
    workload_risk_score = max(0, min(100, workload_risk_score))

    trend = "stable"
    if meeting_increase_pct > 20 or afterhours_increase_pct > 20:
        trend = "escalating"
    elif meeting_increase_pct < -20 and afterhours_increase_pct < -20:
        trend = "easing"

    return {
        "workload_risk_score": workload_risk_score,
        "baseline_meetings_per_week": round(baseline_meetings, 1),
        "recent_meetings_per_week": round(recent_meetings, 1),
        "baseline_afterhours_per_week": round(baseline_afterhours, 1),
        "recent_afterhours_per_week": round(recent_afterhours, 1),
        "meeting_increase_pct": round(meeting_increase_pct, 1),
        "afterhours_increase_pct": round(afterhours_increase_pct, 1),
        "trend": trend,
    }


if __name__ == "__main__":
    # smoke test: escalating workload
    meetings = [[3, 2, 3, 2, 3], [3, 3, 2, 3, 2], [5, 6, 5, 7, 6], [6, 7, 6, 7, 7]]
    afterhours = [1, 0.5, 4, 6]
    print(score_employee_workload(meetings, afterhours))
