"""Test stop-word detection during TTS playback."""
from voicenode.core.stop_word_matcher import StopWordMatcher


def test_match_single_word():
    """Match 'wait' in isolation."""
    matcher = StopWordMatcher()
    assert matcher.match("wait") == "wait"


def test_match_case_insensitive():
    """Match 'WAIT', 'Wait', 'wAiT'."""
    matcher = StopWordMatcher()
    assert matcher.match("WAIT") == "wait"
    assert matcher.match("Wait") == "wait"
    assert matcher.match("wAiT") == "wait"


def test_match_in_sentence():
    """Match 'wait' in 'I said wait a second'."""
    matcher = StopWordMatcher()
    assert matcher.match("I said wait a second") == "wait"


def test_no_false_positive_substring():
    """Don't match 'stop' in 'desktop' (word boundary test)."""
    matcher = StopWordMatcher()
    assert matcher.match("desktop") is None


def test_match_all_stop_words():
    """Match each stop word in the list."""
    matcher = StopWordMatcher()
    for word in matcher.STOP_WORDS:
        assert matcher.match(word) == word, f"Failed to match '{word}'"


def test_match_multi_word_stop_word():
    """Match 'hold on' (multi-word stop-word)."""
    matcher = StopWordMatcher()
    assert matcher.match("hold on please") == "hold on"
    assert matcher.match("can you hold on") == "hold on"


def test_return_none_no_match():
    """Return None when no stop-word found."""
    matcher = StopWordMatcher()
    assert matcher.match("hello world") is None
    assert matcher.match("please continue") is None
