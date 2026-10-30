"""
nlp_dates.py -- small, dependency-free parsers for "tomorrow at 3pm for 45 minutes".
Used by the offline assistant and by chatbot tool arguments.
"""

import re
from datetime import date, datetime, timedelta

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WD_SHORT = {"mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3, "fri": 4, "sat": 5, "sun": 6}
MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"])}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def parse_date(text: str, today: date):
    """Return a date or None."""
    t = (text or "").lower()
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    if re.search(r"\bday after tomorrow\b", t):
        return today + timedelta(days=2)
    if re.search(r"\btomorrow\b|\btmrw\b|\btmr\b", t):
        return today + timedelta(days=1)
    if re.search(r"\btoday\b|\btonight\b|\bthis (morning|afternoon|evening)\b", t):
        return today
    # "12 oct", "12th of october", "oct 12"
    mon = "|".join(sorted(MONTHS, key=len, reverse=True))
    m = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({mon})\b", t) or None
    if m:
        day, month = int(m.group(1)), MONTHS[m.group(2)]
    else:
        m2 = re.search(rf"\b({mon})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", t)
        day, month = (int(m2.group(2)), MONTHS[m2.group(1)]) if m2 else (None, None)
    if day:
        try:
            d = date(today.year, month, day)
            if d < today - timedelta(days=30):
                d = date(today.year + 1, month, day)
            return d
        except ValueError:
            return None
    # weekday names
    m = re.search(r"\b(next\s+|this\s+|on\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tues?|wed|thu(?:rs?)?|fri|sat|sun)\b", t)
    if m:
        word = m.group(2)
        idx = WEEKDAYS.index(word) if word in WEEKDAYS else WD_SHORT.get(word)
        if idx is not None:
            if (m.group(1) or "").strip() == "next":
                return _monday(today) + timedelta(days=7 + idx)
            delta = (idx - today.weekday()) % 7
            return today + timedelta(days=delta)
    return None


def parse_range_word(text: str):
    """'this week' / 'next week' / None"""
    t = (text or "").lower()
    if re.search(r"\bnext week\b", t):
        return "next_week"
    if re.search(r"\bthis week\b|\bthe week\b|\bmy week\b|\bweek\b", t):
        return "this_week"
    return None


def parse_time(text: str):
    """Return (hour, minute) or None."""
    t = (text or "").lower()
    if re.search(r"\bnoon\b", t):
        return (12, 0)
    m = re.search(r"\b(\d{1,2}):(\d{2})\s*(am|pm|a\.m\.|p\.m\.)?", t)
    if m:
        h, mi, ap = int(m.group(1)), int(m.group(2)), (m.group(3) or "")[:1]
        if mi < 60 and h <= 24:
            if ap == "p" and h < 12:
                h += 12
            if ap == "a" and h == 12:
                h = 0
            if not ap and 1 <= h <= 7:
                h += 12
            return (h % 24, mi)
    m = re.search(r"\b(\d{1,2})(?:\.(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", t)
    if m:
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)[:1]
        if 1 <= h <= 12:
            if ap == "p" and h < 12:
                h += 12
            if ap == "a" and h == 12:
                h = 0
            return (h, mi)
    m = re.search(r"\b(?:at|around|by|@)\s*(\d{1,2})\b(?!\s*(?:min|hour|hr|h\b|st|nd|rd|th|:))", t)
    if m:
        h = int(m.group(1))
        if 1 <= h <= 7:
            h += 12
        if 8 <= h <= 23:
            return (h, 0)
    return None


def parse_duration(text: str):
    """Minutes or None."""
    t = (text or "").lower()
    if re.search(r"\bhalf an hour\b|\bhalf hour\b", t):
        return 30
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*(hours?|hrs?|h)\b", t)
    if m:
        return int(float(m.group(1)) * 60)
    m = re.search(r"\b(\d{1,3})\s*(minutes?|mins?|m)\b", t)
    if m:
        return int(m.group(1))
    if re.search(r"\ban hour\b|\bone hour\b", t):
        return 60
    return None


def hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")
