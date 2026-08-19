"""Small-talk detection.

Single responsibility: decide whether a user message is pure conversational
input (greeting/thanks/acknowledgment) that must never trigger tool calls.
"""

CONVERSATIONAL = {
    "hi", "hello", "hey", "yo", "sup", "howdy", "hii", "hiii", "heya",
    "whats up", "what's up", "wassup", "how are you", "how is it going",
    "good morning", "good afternoon", "good evening",
    "thanks", "thank you", "ty", "thx", "cheers",
    "ok", "okay", "cool", "nice", "great", "awesome", "sounds good",
    "bye", "goodbye", "see you", "good night",
    "who are you", "what are you", "what can you do", "help",
}


def is_conversational(text: str) -> bool:
    """Return True when a user message is pure small talk needing no tools."""
    normalized = text.strip().lower()
    for ch in ".,!?;:":
        normalized = normalized.replace(ch, "")
    normalized = " ".join(normalized.split())
    return normalized in CONVERSATIONAL
