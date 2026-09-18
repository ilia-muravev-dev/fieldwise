import math

from fieldwise.db.models import EMBEDDING_DIM
from fieldwise.retrieval.embeddings import FakeEmbedder


def test_fake_embedder_is_deterministic_and_unit_length() -> None:
    embedder = FakeEmbedder()
    [a, b, c] = embedder.embed(["TOTAL 45,500 CASH", "TOTAL 45,500 CASH", "Cheese Tart Rp58000"])
    assert len(a) == EMBEDDING_DIM
    assert a == b
    assert math.isclose(sum(x * x for x in a), 1.0, rel_tol=1e-6)
    similar = sum(x * y for x, y in zip(a, b, strict=True))
    different = sum(x * y for x, y in zip(a, c, strict=True))
    assert similar > different
    assert embedder.embed([]) == []
