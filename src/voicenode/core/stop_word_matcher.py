"""Stop-word detection during TTS playback."""
import re


class StopWordMatcher:
    """Match text against hard-coded stop-word list."""

    STOP_WORDS = ["wait", "stop", "hold on", "cancel", "no", "nope", "never mind"]

    def __init__(self):
        # Build regex: whole-word matching, case-insensitive
        escaped_words = [re.escape(word) for word in self.STOP_WORDS]
        pattern = r"\b(" + "|".join(escaped_words) + r")\b"
        self.pattern = re.compile(pattern, re.IGNORECASE)

    def match(self, text: str) -> str | None:
        """Return matched keyword (original case from list) or None."""
        m = self.pattern.search(text)
        if m:
            matched_text = m.group(1).lower()
            # Return original case from STOP_WORDS list
            for word in self.STOP_WORDS:
                if word.lower() == matched_text:
                    return word
        return None
