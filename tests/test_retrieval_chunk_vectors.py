"""Tests for batched chunk vectors in hybrid retrieval scoring."""

from types import SimpleNamespace

from app.services.embedding_service import HashingEmbeddingProvider
from app.services.retrieval_scoring_scorer import HybridRetrievalScorer


class CountingProvider:
    """Embedding provider double that records every provider round trip."""

    def __init__(self, dimensions=8, fail=False):
        """Initialize the double with a fixed vector size."""
        self.dimensions = dimensions
        self.calls = []
        self.fail = fail

    def embed_texts(self, texts):
        """Return one deterministic vector per text and count the call."""
        self.calls.append(len(texts))
        if self.fail:
            raise RuntimeError("provider down")
        return [[float(len(text) % 5 + 1)] * self.dimensions for text in texts]

    def embed_text(self, text):
        """Embed one text through the batch method, as the real providers do."""
        return self.embed_texts([text])[0]


def _chunks(count, embedding=None):
    """Return lightweight chunk doubles with ids, text and an optional stored vector."""
    return [
        SimpleNamespace(id=index, text=f"Hydraulikpumpe Wartung {index}", embedding=embedding)
        for index in range(1, count + 1)
    ]


def test_missing_vectors_are_embedded_in_batches_instead_of_per_chunk(app):
    """Verify 250 candidates cost three provider calls, not 250."""
    provider = CountingProvider()
    scorer = HybridRetrievalScorer("hydraulik", query_vector=[1.0] * 8, embedding_provider=provider)
    chunks = _chunks(250)

    scorer.prime_chunk_vectors(chunks)
    similarities = [scorer._chunk_semantic_similarity(chunk, chunk.text) for chunk in chunks]

    assert provider.calls == [100, 100, 50]
    assert all(value > 0 for value in similarities)


def test_stored_vectors_with_matching_dimension_need_no_provider_call(app):
    """Verify stored chunk embeddings are reused when they fit the query vector."""
    provider = CountingProvider()
    scorer = HybridRetrievalScorer("hydraulik", query_vector=[1.0] * 8, embedding_provider=provider)
    chunks = _chunks(40, embedding=[0.5] * 8)

    scorer.prime_chunk_vectors(chunks)
    similarity = scorer._chunk_semantic_similarity(chunks[0], chunks[0].text)

    assert provider.calls == []
    assert similarity > 0.99


def test_stored_vectors_with_other_dimension_are_embedded_again(app):
    """Verify 384-d hashing vectors are not compared against a 1536-d query."""
    provider = CountingProvider(dimensions=1536)
    scorer = HybridRetrievalScorer(
        "hydraulik", query_vector=[1.0] * 1536, embedding_provider=provider
    )
    chunks = _chunks(3, embedding=[0.1] * 384)

    scorer.prime_chunk_vectors(chunks)

    assert provider.calls == [3]


def test_primed_similarity_matches_per_chunk_embedding(app):
    """Verify batching does not change the semantic score a chunk receives."""
    provider = HashingEmbeddingProvider()
    query = "Hydraulikpumpe verliert Druck an Presse 3"
    query_vector = provider.embed_text(query)
    chunk = SimpleNamespace(
        id=7, text="Druckverlust an der Hydraulikpumpe der Presse 3", embedding=None
    )

    unprimed = HybridRetrievalScorer(query, query_vector=query_vector, embedding_provider=provider)
    primed = HybridRetrievalScorer(query, query_vector=query_vector, embedding_provider=provider)
    primed.prime_chunk_vectors([chunk])

    assert primed._chunk_semantic_similarity(chunk, chunk.text) == unprimed._semantic_similarity(
        chunk.text
    )


def test_failed_batch_degrades_to_no_semantic_signal_without_retrying(app):
    """Verify a provider outage costs one call and scores semantics as zero."""
    provider = CountingProvider(fail=True)
    scorer = HybridRetrievalScorer("hydraulik", query_vector=[1.0] * 8, embedding_provider=provider)
    chunks = _chunks(30)

    scorer.prime_chunk_vectors(chunks)
    similarities = [scorer._chunk_semantic_similarity(chunk, chunk.text) for chunk in chunks]

    assert provider.calls == [30]
    assert similarities == [0.0] * 30
