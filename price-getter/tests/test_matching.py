import pytest

from price_getter.matching import EmbeddingModelUnavailable, encode_texts


def test_encode_without_extra_raises() -> None:
    # sentence-transformers is an optional extra; without it the lazy import
    # must fail with a helpful error, not an ImportError traceback
    try:
        import sentence_transformers  # noqa: F401

        pytest.skip("matching extra installed; nothing to test")
    except ImportError:
        pass

    with pytest.raises(EmbeddingModelUnavailable):
        encode_texts(["2L 2% milk"])
