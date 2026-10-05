"""Rule-based symptom-checker chatbot.

The conversation has three stages. Each one asks a follow-up question, and the
reply is chosen from how many user turns have happened, the severity words found
in the conversation, and the ML model's predicted condition. The model's
confidence is used to decide how strongly the bot should recommend a doctor.
"""
import random

from model import predict

SEVERE_WORDS = ["severe", "unbearable", "cant move", "fainted", "very heavy", "weeks", "daily"]
MODERATE_WORDS = ["painful", "recurring", "every month", "affecting", "missing work", "bad"]

FOLLOW_UP_QUESTIONS = [
    "I hear you. How long have you been experiencing this?",
    "Thanks for sharing. Is this something that happens regularly or just recently?",
    "I understand. Would you say this is affecting your daily life or is it manageable?",
    "Got it. Are these symptoms getting worse over time, or staying about the same?",
]


def _user_messages(messages):
    return [m["content"] for m in messages if m.get("role") == "user"]


def get_bot_response(messages, pipeline):
    """Return a dict with ``reply``, ``severity`` and, when relevant, ``condition``."""
    user_texts = _user_messages(messages)
    last_text = user_texts[-1].lower() if user_texts else ""
    history = " ".join(text.lower() for text in user_texts)
    num_turns = len(user_texts)

    is_severe = any(word in history for word in SEVERE_WORDS)
    is_moderate = any(word in history for word in MODERATE_WORDS)

    prediction = predict(last_text or "unknown", pipeline)
    condition = prediction["condition"]
    confidence = prediction["confidence"]
    tips = prediction["condition_info"].get("tips", [])

    if num_turns == 1:
        return {"reply": random.choice(FOLLOW_UP_QUESTIONS), "severity": "mild", "show_condition": False}

    if num_turns == 2:
        if is_severe:
            return {
                "reply": f"That sounds quite difficult. Based on what you've described, it could be worth looking into {condition}. Are these symptoms affecting your daily activities?",
                "severity": "moderate", "show_condition": True,
                "condition": condition, "confidence": confidence,
            }
        tip = tips[0] if tips else "drink plenty of water and rest well"
        return {
            "reply": f"That sounds manageable for now. A simple tip: {tip}. Have you noticed if your symptoms are worse at any particular time of the month?",
            "severity": "mild", "show_condition": False,
        }

    # three or more user turns
    if is_severe or (confidence > 60 and is_moderate):
        return {
            "reply": f"Based on everything you've described, the symptoms are consistent with {condition}. Given that they seem to be affecting your daily life, I'd recommend seeing a gynaecologist. Would you like me to generate a health summary for your doctor?",
            "severity": "severe", "show_condition": True,
            "condition": condition, "confidence": confidence, "suggest_report": True,
        }
    if confidence > 60:
        tip = tips[1] if len(tips) > 1 else (tips[0] if tips else "tracking your symptoms for 2 more weeks")
        return {
            "reply": f"Your symptoms sound like they could be related to {condition} — but they seem mild right now. Try: {tip}. If things don't improve, consider seeing a doctor.",
            "severity": "moderate", "show_condition": True,
            "condition": condition, "confidence": confidence,
        }
    tip1 = tips[0] if tips else "stay hydrated"
    tip2 = tips[1] if len(tips) > 1 else "get enough sleep"
    return {
        "reply": f"Your symptoms are worth monitoring but don't seem alarming right now. Some things that often help: {tip1}, and {tip2}. Keep tracking how you feel.",
        "severity": "mild", "show_condition": False,
    }
