"""Unit tests for hybrid_search/client.py's create_index fallback —
mocked Elasticsearch client, no real cluster. Proves the same "degrade,
don't crash" behavior this pattern relies on: a cluster that can't
create a semantic_text field (no ML node, no inference endpoint, an
older version) still ends up with a working index and
semantic_enabled=False, instead of create_index() raising.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from hybrid_search.client import HybridSearchClient  # noqa: E402


def _client_with_mocked_es():
    client = HybridSearchClient.__new__(HybridSearchClient)
    client.inference_id = '.elser-2-elasticsearch'
    client.semantic_enabled = False
    client.es = MagicMock()
    return client


def test_create_index_success_sets_semantic_enabled_true():
    client = _client_with_mocked_es()
    client.es.indices.create.return_value = {'acknowledged': True}

    result = client.create_index('my_index')

    assert result is True
    assert client.semantic_enabled is True
    # Only the semantic_text mapping attempt should have run — no
    # fallback plain-index create call alongside it.
    assert client.es.indices.create.call_count == 1
    _, kwargs = client.es.indices.create.call_args
    mapping = kwargs['mappings']['properties']['content_semantic']
    assert mapping['type'] == 'semantic_text'
    assert mapping['inference_id'] == '.elser-2-elasticsearch'


def test_create_index_falls_back_on_failure():
    """When the semantic_text mapping create call raises (cluster has no
    usable inference endpoint), create_index must catch it and retry
    with a plain index instead of propagating the exception."""
    client = _client_with_mocked_es()
    client.es.indices.create.side_effect = [
        Exception('inference endpoint not found'),
        {'acknowledged': True},
    ]

    result = client.create_index('my_index')

    assert result is False
    assert client.semantic_enabled is False
    assert client.es.indices.create.call_count == 2
    # The second (fallback) call must be a plain index create — no
    # mappings kwarg at all.
    _, second_call_kwargs = client.es.indices.create.call_args
    assert 'mappings' not in second_call_kwargs


def test_index_documents_adds_semantic_field_only_when_enabled():
    client = _client_with_mocked_es()
    client.semantic_enabled = True
    client.es.bulk.return_value = {'items': []}

    client.index_documents('my_index', [{'id': '1', 'content': 'hello world'}])

    _, kwargs = client.es.bulk.call_args
    operations = kwargs['operations']
    # [action, document, action, document, ...]
    document = operations[1]
    assert document['content_semantic'] == 'hello world'


def test_index_documents_skips_semantic_field_when_disabled():
    client = _client_with_mocked_es()
    client.semantic_enabled = False
    client.es.bulk.return_value = {'items': []}

    client.index_documents('my_index', [{'id': '1', 'content': 'hello world'}])

    _, kwargs = client.es.bulk.call_args
    document = kwargs['operations'][1]
    assert 'content_semantic' not in document
