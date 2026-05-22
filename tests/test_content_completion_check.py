"""content_generator._looks_complete — truncation detector."""
from src.core.content_generator import _looks_complete


def test_complete_english_sentence():
    assert _looks_complete("This is a complete sentence.") is True


def test_complete_japanese_sentence():
    assert _looks_complete("これは完結した文章です。") is True


def test_complete_question():
    assert _looks_complete("Is this complete?") is True


def test_complete_japanese_question():
    assert _looks_complete("これは完結？") is True


def test_complete_with_exclamation():
    assert _looks_complete("Yes!") is True


def test_truncated_mid_sentence():
    assert _looks_complete("the conversation cuts off mid") is False


def test_truncated_mid_quote():
    assert _looks_complete("She said 'this is") is False


def test_truncated_after_open_paren():
    assert _looks_complete("This sentence ends with an (open") is False


def test_empty_text_is_complete():
    assert _looks_complete("") is True
    assert _looks_complete("   \n   ") is True


def test_trailing_whitespace_stripped():
    assert _looks_complete("Done.   \n\n") is True
    assert _looks_complete("Incomplete\n\n") is False
