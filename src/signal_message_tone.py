"""
signal_message_tone.py
-----------------------
Signal 1: Message tone / semantic analysis.

NOTE ON MODEL CHOICE:
The committed project stack names Hugging Face transformer models
(distilbert-base-uncased-finetuned-sst-2-english for sentiment,
all-MiniLM-L6-v2 for semantic embeddings). This sandbox's network
cannot reach huggingface.co to download them, so this module uses:

  - VADER (lexicon-based sentiment) for polarity scoring
  - TF-IDF + cosine similarity (scikit-learn) against a small reference
    set of burnout-language phrases, as a lightweight stand-in for
    semantic embedding similarity

Both run fully offline with no model download. The transformer models
remain the documented target architecture for a real deployment with
full internet/model access; this module is a functionally equivalent,
honestly-labeled substitute for the prototype stage.

Output: a 0-100 "message tone risk" score per employee per week, where
higher = more burnout-indicative language.
"""

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

from stress_lexicon import LEXICON_UPDATES, find_cues

_analyzer = SentimentIntensityAnalyzer()
# teach VADER everyday workplace-stress wording it does not know
_analyzer.lexicon.update(LEXICON_UPDATES)

# Small reference set of canonical burnout-indicative phrases used for the
# semantic-similarity signal (stand-in for embedding-based similarity).
BURNOUT_REFERENCE_PHRASES = [
    "I am exhausted and cannot keep up with this workload",
    "I feel completely drained and numb",
    "nothing I do seems to matter anymore",
    "I am running on empty and dreading work",
    "I can't focus and feel disconnected from my team",
    "I haven't had a proper break in weeks",
    "too many deadlines and I am completely overwhelmed",
    "working late every night and weekends, no time to rest",
    "I am so stressed and anxious about everything at work",
    "I am burnt out and just going through the motions",
    "drowning in tasks, the backlog keeps piling up",
    "I dread opening my inbox, there is just too much",
]

_vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True).fit(
    BURNOUT_REFERENCE_PHRASES + [
        "great meeting today, looking forward to the next sprint",
        "finished my tasks, the release went smoothly",
    ]
)
_reference_matrix = _vectorizer.transform(BURNOUT_REFERENCE_PHRASES)


def _semantic_similarity_score(text: str) -> float:
    """Returns 0-1: how semantically close text is to burnout-indicative language."""
    vec = _vectorizer.transform([text])
    sims = cosine_similarity(vec, _reference_matrix)
    return float(np.max(sims)) if sims.size else 0.0


def score_message(text: str) -> dict:
    """Score a single message. Returns sentiment compound (-1..1) and semantic sim (0..1)."""
    sentiment = _analyzer.polarity_scores(text)["compound"]
    semantic = _semantic_similarity_score(text)
    cues = find_cues(text)
    # per-message risk (0-100). Neutral wording sits low (a plain "what time is the
    # standup?" should not look stressed); negative sentiment, closeness to burnout
    # language and each distinct stress cue push it up, positive wording pulls it down.
    neg, pos = max(0.0, -sentiment), max(0.0, sentiment)
    sentiment_risk = 100 * neg * 0.9 + 6 - 6 * pos
    risk = 0.6 * sentiment_risk + 0.4 * semantic * 100
    risk += min(40, 22 * len(cues["stress"]))
    risk -= min(10, 3 * len(cues["positive"]))
    risk = max(0.0, min(100.0, risk))
    return {"text": text, "sentiment_compound": sentiment, "semantic_similarity": semantic,
            "stress_cues": cues["stress"], "positive_cues": cues["positive"],
            "risk": round(risk, 1)}


def stress_label(risk: float) -> str:
    """Plain-language label for a 0-100 tone risk value."""
    if risk >= 54:
        return "stressed"
    if risk >= 23:
        return "tense"
    return "calm"


def score_week(messages: list) -> dict:
    """Aggregate a week's messages into one tone-risk score (0-100, higher = more risk)."""
    if not messages:
        return {"tone_risk_score": None, "avg_sentiment": None, "avg_semantic_sim": None, "n_messages": 0}

    scored = [score_message(m) for m in messages]
    avg_sentiment = float(np.mean([s["sentiment_compound"] for s in scored]))
    avg_semantic = float(np.mean([s["semantic_similarity"] for s in scored]))

    # week score = average of the per-message risks (see score_message)
    tone_risk_score = round(float(np.mean([s["risk"] for s in scored])), 1)
    tone_risk_score = max(0, min(100, tone_risk_score))

    return {
        "tone_risk_score": tone_risk_score,
        "avg_sentiment": round(avg_sentiment, 3),
        "avg_semantic_sim": round(avg_semantic, 3),
        "n_messages": len(messages),
    }


def score_employee_messages(weekly_messages: list) -> dict:
    """weekly_messages: list of {week, messages}. Returns per-week scores + overall trend."""
    weekly_scores = []
    for wk in weekly_messages:
        result = score_week(wk["messages"])
        result["week"] = wk["week"]
        weekly_scores.append(result)

    valid = [w["tone_risk_score"] for w in weekly_scores if w["tone_risk_score"] is not None]
    overall = round(float(np.mean(valid)), 1) if valid else None

    # trend: is risk increasing over recent weeks? (simple slope sign)
    trend = "stable"
    if len(valid) >= 3:
        first_half = np.mean(valid[: len(valid) // 2])
        second_half = np.mean(valid[len(valid) // 2:])
        if second_half - first_half > 5:
            trend = "worsening"
        elif first_half - second_half > 5:
            trend = "improving"

    return {"weekly_scores": weekly_scores, "overall_tone_risk": overall, "trend": trend}


if __name__ == "__main__":
    # quick smoke test
    sample = [
        "I am so exhausted I can't focus on anything anymore",
        "Great meeting today, looking forward to the next sprint",
    ]
    for m in sample:
        print(m, "->", score_message(m))
