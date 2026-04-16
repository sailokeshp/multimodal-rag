from app.services import retrieval_service as retrieval_module


def test_should_embed_image_query_only_for_image_intent(monkeypatch):
    monkeypatch.setattr(
        retrieval_module.settings, "enable_image_embeddings", True, raising=False
    )
    monkeypatch.setattr(
        retrieval_module.settings, "image_query_embed_policy", "image_only", raising=False
    )

    svc = retrieval_module.RetrievalService(db=None)

    assert svc._should_embed_image_query("image") is True
    assert svc._should_embed_image_query("hybrid") is False
    assert svc._should_embed_image_query("summary") is False


def test_should_embed_image_query_for_every_query_when_policy_is_always(monkeypatch):
    monkeypatch.setattr(
        retrieval_module.settings, "enable_image_embeddings", True, raising=False
    )
    monkeypatch.setattr(
        retrieval_module.settings, "image_query_embed_policy", "always", raising=False
    )

    svc = retrieval_module.RetrievalService(db=None)

    assert svc._should_embed_image_query("hybrid") is True
    assert svc._should_embed_image_query("compare") is True
