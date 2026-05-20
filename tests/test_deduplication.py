from src.core.dedupe import dedupe
from src.core.schema import StructuredPost, VerificationTags


def _post(post_id, text, url):
    return StructuredPost(
        post_id=post_id, text=text, url=url, provider_name="mock",
        verification=VerificationTags(),
    )


def test_dedupe_by_url():
    a = _post("1", "alpha", "https://x.com/a/1")
    b = _post("2", "alpha repeated wording slightly", "https://x.com/a/1")  # same url
    c = _post("3", "different content", "https://x.com/c/3")
    out = dedupe([a, b, c])
    assert len(out) == 2
    assert {p.post_id for p in out} == {"1", "3"}


def test_dedupe_by_content_hash():
    a = _post("1", "Same exact body", "https://x.com/a/1")
    b = _post("2", "Same exact body", "https://x.com/b/2")  # different url, same body
    out = dedupe([a, b])
    assert len(out) == 1


def test_dedupe_preserves_order():
    a = _post("1", "alpha", "https://x.com/a/1")
    b = _post("2", "beta", "https://x.com/b/2")
    out = dedupe([a, b])
    assert [p.post_id for p in out] == ["1", "2"]
