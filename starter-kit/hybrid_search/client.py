"""Connection + index setup for hybrid (BM25 + semantic) search.

This mirrors the connection and index-creation logic in the parent
repo's ``search.py`` almost exactly — that code is the proof this
pattern runs in production, so this file deliberately doesn't deviate
from it — but with the blog-specific bits removed: no ``data.json``
auto-reindex-on-missing-index, no document ``id``-as-Elasticsearch-``_id``
convention baked in, no admin-panel document CRUD helpers. Just: connect,
and create an index whose text field is set up for hybrid search.
"""
import os

from elasticsearch import Elasticsearch


class HybridSearchClient:
    """Wraps an Elasticsearch client plus the one piece of state that
    matters for this pattern: whether the connected cluster actually has
    a usable inference endpoint, and therefore whether search() should
    run the hybrid (BM25 + semantic) retriever or fall back to
    lexical-only.

    Connection details are read from the environment (see .env.example
    in this directory) rather than passed as constructor arguments in
    the example app, for the same reason as the parent repo: credentials
    and cluster IDs should never end up hardcoded or committed.
    """

    def __init__(self, *, es_url=None, cloud_id=None, api_key=None,
                 username=None, password=None, inference_id=None):
        es_url = es_url or os.environ.get('ES_URL', 'http://localhost:9200')
        cloud_id = cloud_id or os.environ.get('ES_CLOUD_ID')
        api_key = api_key or os.environ.get('ES_API_KEY')
        username = username or os.environ.get('ES_USERNAME')
        password = password or os.environ.get('ES_PASSWORD')

        # `.elser-2-elasticsearch` is Elastic's built-in sparse-embedding
        # inference endpoint — preconfigured on Elastic Cloud and
        # Serverless, so hybrid search works with zero extra ML setup on
        # those. A self-managed cluster without an ML node, or one
        # running a version older than 8.15, won't have it; see
        # create_index() below for what happens then.
        self.inference_id = inference_id or os.environ.get(
            'ES_INFERENCE_ID', '.elser-2-elasticsearch'
        )
        # Set by create_index(). Read this after calling it to decide
        # whether to build a hybrid or lexical-only query (see query.py).
        self.semantic_enabled = False

        client_kwargs = {}
        if api_key:
            client_kwargs['api_key'] = api_key
        elif username and password:
            client_kwargs['basic_auth'] = (username, password)

        if cloud_id:
            self.es = Elasticsearch(cloud_id=cloud_id, **client_kwargs)
        else:
            self.es = Elasticsearch(es_url, **client_kwargs)

    def create_index(self, index_name, *, semantic_field='content_semantic'):
        """Create (recreating if it already exists) an index whose
        ``semantic_field`` is mapped as ``semantic_text`` pointing at
        this client's inference endpoint — the field Elasticsearch
        computes embeddings for automatically, on both index and query.

        Falls back to a plain index (no semantic field) if the cluster
        can't support ``semantic_text`` on this inference endpoint,
        instead of raising. ``self.semantic_enabled`` reflects which
        mode is now live; check it before building queries (or just call
        ``search()``, which checks it for you — see query.py).

        This is the one function in the kit you're most likely to adapt:
        swap the mapping's other fields (title, tags, timestamps, ...)
        for your own document shape. ``semantic_field`` only needs to
        exist and be typed correctly — everything else about your index
        is yours to define.
        """
        self.es.indices.delete(index=index_name, ignore_unavailable=True)
        try:
            self.es.indices.create(
                index=index_name,
                mappings={
                    'properties': {
                        semantic_field: {
                            'type': 'semantic_text',
                            'inference_id': self.inference_id,
                        },
                    },
                },
            )
            self.semantic_enabled = True
        except Exception:
            self.es.indices.create(index=index_name)
            self.semantic_enabled = False
        return self.semantic_enabled

    def index_documents(self, index_name, documents, *, id_field='id',
                         text_field='content', semantic_field='content_semantic'):
        """Bulk-index documents, copying ``text_field`` into
        ``semantic_field`` on each one so Elasticsearch has something to
        embed — but only when ``semantic_enabled`` is True. On a
        lexical-only cluster this is a no-op copy that's simply never
        read, since the field isn't in the mapping as ``semantic_text``.

        ``refresh='wait_for'`` (not the default, up-to-1s-later async
        refresh) so documents indexed by a script or a cold start are
        immediately searchable — worth the small latency cost for a
        starter kit or a batch job; drop it for high-volume production
        indexing where an occasional refresh delay is fine and bulk
        throughput matters more (see the "indexing lag under load" note
        in this kit's README).
        """
        operations = []
        for doc in documents:
            operations.append({'index': {'_index': index_name, '_id': doc[id_field]}})
            if self.semantic_enabled:
                doc = dict(doc)
                doc[semantic_field] = doc.get(text_field, '')
            operations.append(doc)
        return self.es.bulk(operations=operations, refresh='wait_for')
