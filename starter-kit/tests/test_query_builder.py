"""Unit tests for hybrid_search/query.py — no Elasticsearch cluster
required. These exist specifically to prove, mechanically, the two
claims this kit's whole pitch rests on:

1. When semantic search is available, a single query actually runs BOTH
   BM25 lexical and semantic retrieval, merged with RRF, against ONE
   index — not two systems stitched together in application code.
2. When it isn't (no inference endpoint on this cluster), the exact
   same call site produces a plain lexical query instead of raising —
   the fallback promised in the README and on the /starter-kit page
   actually happens rather than being aspirational.

Run from starter-kit/: `pytest tests/`
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from hybrid_search.query import (  # noqa: E402
    build_hybrid_search_kwargs,
    build_lexical_query,
    build_semantic_query,
    search,
)


def test_lexical_query_uses_multi_match_with_fuzziness():
    q = build_lexical_query('why is search slow', fields=['title^2', 'content'])
    assert q == {
        'bool': {
            'must': {
                'multi_match': {
                    'query': 'why is search slow',
                    'fields': ['title^2', 'content'],
                    'fuzziness': 'AUTO',
                }
            },
        }
    }


def test_lexical_query_empty_string_matches_all():
    q = build_lexical_query('', fields=['title'])
    assert q['bool']['must'] == {'match_all': {}}


def test_lexical_query_merges_filters():
    filters = {'filter': [{'term': {'category.keyword': 'infra'}}]}
    q = build_lexical_query('cache', filters=filters)
    assert q['bool']['filter'] == filters['filter']


def test_semantic_query_uses_semantic_field():
    q = build_semantic_query('why is search slow', semantic_field='content_semantic')
    assert q['bool']['must'] == {
        'semantic': {'field': 'content_semantic', 'query': 'why is search slow'}
    }


def test_hybrid_kwargs_when_semantic_enabled_builds_rrf_retriever():
    """The core claim: with semantic_enabled=True, one call produces one
    retriever block running BOTH a lexical and a semantic sub-retriever,
    merged with RRF — not two separate queries a caller has to run and
    stitch together itself."""
    kwargs = build_hybrid_search_kwargs(
        'why is search slow', semantic_enabled=True, size=10,
    )

    assert 'query' not in kwargs
    retriever = kwargs['retriever']['rrf']
    assert retriever['rank_window_size'] == 50
    assert retriever['rank_constant'] == 20

    sub_retrievers = retriever['retrievers']
    assert len(sub_retrievers) == 2

    lexical, semantic = sub_retrievers
    assert 'multi_match' in lexical['standard']['query']['bool']['must']
    assert 'semantic' in semantic['standard']['query']['bool']['must']
    assert kwargs['size'] == 10


def test_hybrid_kwargs_falls_back_to_lexical_only_when_semantic_disabled():
    """The fallback claim: with semantic_enabled=False (no inference
    endpoint on this cluster), the SAME function returns a plain lexical
    query instead of a retriever block — and, crucially, does not raise
    or reference the semantic field at all."""
    kwargs = build_hybrid_search_kwargs(
        'why is search slow', semantic_enabled=False, size=10,
    )

    assert 'retriever' not in kwargs
    assert 'multi_match' in kwargs['query']['bool']['must']
    assert kwargs['size'] == 10


def test_hybrid_kwargs_passes_through_extra_kwargs():
    kwargs = build_hybrid_search_kwargs(
        'cache', semantic_enabled=False,
        extra={'highlight': {'fields': {'content': {}}}},
    )
    assert kwargs['highlight'] == {'fields': {'content': {}}}


def test_search_wrapper_calls_es_with_index_and_semantic_state():
    """End-to-end (mocked): search() should read the client's
    semantic_enabled flag and pass an index + the right kwargs to
    es.search — proving the query-building logic is actually wired to
    the client rather than only unit-testable in isolation."""
    fake_client = MagicMock()
    fake_client.semantic_enabled = True
    fake_client.es.search.return_value = {'hits': {'hits': []}}

    search(fake_client, 'my_documents', 'why is search slow', size=5)

    fake_client.es.search.assert_called_once()
    _, call_kwargs = fake_client.es.search.call_args
    assert call_kwargs['index'] == 'my_documents'
    assert 'retriever' in call_kwargs
    assert call_kwargs['size'] == 5


def test_search_wrapper_falls_back_when_client_has_no_semantic():
    fake_client = MagicMock()
    fake_client.semantic_enabled = False
    fake_client.es.search.return_value = {'hits': {'hits': []}}

    search(fake_client, 'my_documents', 'why is search slow')

    _, call_kwargs = fake_client.es.search.call_args
    assert 'retriever' not in call_kwargs
    assert 'query' in call_kwargs
