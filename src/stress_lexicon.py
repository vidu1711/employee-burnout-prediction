"""
stress_lexicon.py
------------------
Workplace-stress vocabulary used on top of VADER, plus a cue detector that
explains *why* a message reads as stressed (so the UI can say "exhaustion,
workload" instead of just showing a number).

VADER is built for reviews and social media, so it misses a lot of everyday
workplace-stress wording ("swamped", "drowning", "crunch", "burnt out").
The word weights below extend its lexicon (VADER scale: -4 very negative ..
+4 very positive).
"""

import re

LEXICON_UPDATES = {
    # everyday scheduling words VADER treats as negative
    "cancel": 0.0, "cancelled": 0.0, "canceled": 0.0, "cancelling": 0.0, "miss": 0.0, "delay": -0.3, "delayed": -0.3,
    # exhaustion
    "exhausted": -2.6, "drained": -2.6, "burnout": -3.2, "burnt": -2.2, "burned": -1.8,
    "worn": -1.6, "fatigued": -2.2, "fatigue": -2.2, "tired": -1.8, "sleepy": -0.8,
    "exhausting": -2.4, "depleted": -2.4, "empty": -1.8,
    # overload
    "swamped": -2.2, "drowning": -2.6, "overwhelmed": -2.8, "overwhelming": -2.6,
    "overloaded": -2.4, "backlog": -1.0, "piling": -1.4, "buried": -1.8,
    "stretched": -1.4, "crunch": -1.8, "slammed": -1.8, "overworked": -2.6,
    # pressure / anxiety
    "deadline": -0.9, "deadlines": -1.1, "stressed": -2.4, "stress": -2.0, "stressful": -2.2,
    "anxious": -2.2, "anxiety": -2.2, "pressure": -1.4, "panic": -2.4, "urgent": -0.8,
    "escalation": -1.2, "escalated": -1.2, "worried": -1.6, "dread": -2.6, "dreading": -2.6,
    # detachment / hopelessness
    "pointless": -2.6, "numb": -2.4, "hopeless": -3.0, "disconnected": -2.0,
    "unmotivated": -2.2, "demotivated": -2.2, "detached": -1.8, "meaningless": -2.6,
    # frustration
    "fed": -0.4, "frustrated": -2.2, "frustrating": -2.2, "unfair": -1.8, "annoyed": -1.6,
    # protective / positive workplace words
    "productive": 2.0, "smooth": 1.6, "shipped": 1.4, "proud": 2.4, "grateful": 2.4,
    "energized": 2.4, "enjoyed": 2.0, "relaxed": 2.0, "balanced": 1.6, "manageable": 1.4,
    "on-track": 1.4, "unblocked": 1.4, "celebrate": 2.0, "excited": 2.2,
}

# cue name -> regex (word-boundary matched, case-insensitive)
CUE_PATTERNS = {
    "exhaustion": r"\b(exhaust\w*|drain\w*|tired|worn out|burn(?:t|ed)?[ -]?out|burnout|running on empty|no energy|fatigue\w*|depleted)\b",
    "overload": r"\b(too much|too many|can'?t keep up|cannot keep up|overwhelm\w*|swamped|buried|drowning|backlog|piling up|slammed|overloaded|overworked|stretched thin|behind on|busy week|so many (?:things|tasks|meetings)|long day|back[- ]to[- ]back|juggl\w+|how much longer i can|keep this pace|can'?t do this much longer|too much on my plate)\b",
    "deadline pressure": r"\b(deadlines?|due (?:today|tomorrow|tonight|friday|monday)|asap|urgent|last[- ]minute|crunch|escalat\w+)\b",
    "detachment": r"\b(pointless|meaningless|doesn'?t matter|don'?t care|numb|disconnected|going through the motions|what'?s the point|hopeless|dread\w*|unmotivated|demotivated)\b",
    "long hours": r"\b(late night|all[- ]nighter|no break|haven'?t (?:had a )?(?:break|slept)|working weekends?|until \d+ ?(?:am|pm)|midnight|every weekend|no time off)\b",
    "frustration": r"\b(frustrat\w+|fed up|sick of|annoyed|can'?t take|unfair)\b",
    "anxiety": r"\b(anxious|anxiety|panic\w*|worried|stressed|stress(?:ful)?)\b",
}
POSITIVE_PATTERN = r"\b(great|excited|happy|proud|grateful|productive|smooth|enjoyed|looking forward|energi[sz]ed|relaxed|on track|well done|thank(?:s| you))\b"
NEGATION = re.compile(r"\b(not|no|nothing|never|isn'?t|aren'?t|wasn'?t|don'?t|doesn'?t|didn'?t|without)\b")

_COMPILED = {k: re.compile(v, re.I) for k, v in CUE_PATTERNS.items()}
_POS = re.compile(POSITIVE_PATTERN, re.I)


def _negated(text: str, start: int) -> bool:
    """True if a negation word appears within ~3 words before position `start`."""
    window = text[max(0, start - 22):start].lower()
    return bool(NEGATION.search(window))


def find_cues(text: str) -> dict:
    """Return {'stress': [cue names], 'positive': [phrases]} for a message."""
    stress = []
    for name, rx in _COMPILED.items():
        for m in rx.finditer(text):
            if not _negated(text, m.start()):
                stress.append(name)
                break
    positive = [m.group(0).lower() for m in _POS.finditer(text) if not _negated(text, m.start())]
    return {"stress": stress, "positive": positive[:3]}
