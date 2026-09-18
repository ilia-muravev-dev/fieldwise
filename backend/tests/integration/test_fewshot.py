from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy.orm import Session

from fieldwise.db.models import GoldenLabel
from fieldwise.documents.service import create_document
from fieldwise.retrieval.embeddings import FakeEmbedder
from fieldwise.retrieval.fewshot import embed_documents, make_retriever, retrieve_examples
from fieldwise.schemas.registry import sync_builtins
from fieldwise.storage import LocalStorage

pytestmark = pytest.mark.integration


def _jpeg(seed: int) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (100 + seed, 100), (seed * 7 % 255, 50, 50)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _labelled(
    session: Session,
    storage: LocalStorage,
    *,
    name: str,
    split: str | None,
    text: str,
    seed: int,
    total: float,
) -> object:
    schema = sync_builtins(session)[0]
    document = create_document(
        session,
        storage,
        data=_jpeg(seed),
        name=name,
        source="cord" if split else "upload",
        split=split,
        external_id=name,
    )
    document.ocr_text = text
    document.ocr_status = "done"
    session.add(
        GoldenLabel(
            document_id=document.id,
            schema_id=schema.id,
            data={"total": total, "line_items": []},
            source="dataset",
        )
    )
    session.flush()
    return document


def test_retrieval_uses_similar_labelled_documents_and_never_the_test_split(
    session: Session, storage: LocalStorage
) -> None:
    schema = sync_builtins(session)[0]
    query = _labelled(
        session,
        storage,
        name="test/q",
        split="test",
        text="EGG TART 13,000 TOTAL 45,500 CASH",
        seed=1,
        total=45500,
    )
    twin = _labelled(
        session,
        storage,
        name="test/twin",
        split="test",
        text="EGG TART 13,000 TOTAL 45,500 CASH",
        seed=2,
        total=45500,
    )
    near = _labelled(
        session,
        storage,
        name="validation/near",
        split="validation",
        text="EGG TART 13,000 TOTAL 45,500 CARD",
        seed=3,
        total=45500,
    )
    far = _labelled(
        session,
        storage,
        name="validation/far",
        split="validation",
        text="Cheese Tart Rp58000 Subtotal Total Tax",
        seed=4,
        total=58000,
    )
    upload = _labelled(
        session,
        storage,
        name="upload/corrected",
        split=None,
        text="EGG TART 13,000 TOTAL 45,500",
        seed=5,
        total=45500,
    )

    assert embed_documents(session, FakeEmbedder()) == 5

    examples = retrieve_examples(session, query, schema, k=3)  # type: ignore[arg-type]

    ids = [e.document_id for e in examples]
    assert len(ids) == 3
    assert "test/q" not in ids
    assert "test/twin" not in ids  # the test split is structurally excluded
    assert ids[0] in {"validation/near", "upload/corrected"}  # most similar first
    assert ids[-1] == "validation/far"
    assert examples[0].output["total"] == 45500
    assert examples[0].ocr_text
    assert all(d is not None for d in (twin, near, far, upload))


def test_k_zero_and_missing_embedding(session: Session, storage: LocalStorage) -> None:
    schema = sync_builtins(session)[0]
    query = _labelled(
        session, storage, name="test/q", split="test", text="TOTAL 1", seed=9, total=1
    )
    _labelled(
        session, storage, name="validation/a", split="validation", text="TOTAL 1", seed=10, total=1
    )
    embed_documents(session, FakeEmbedder(), split="validation")

    assert retrieve_examples(session, query, schema, k=0) == []  # type: ignore[arg-type]
    assert retrieve_examples(session, query, schema, k=2) == []  # type: ignore[arg-type]  # query not embedded, no embedder
    retriever = make_retriever(session, schema, FakeEmbedder())
    assert [e.document_id for e in retriever(query, 2)] == ["validation/a"]  # type: ignore[arg-type]
