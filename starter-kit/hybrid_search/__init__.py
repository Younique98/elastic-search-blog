"""hybrid_search — a small, framework-agnostic package that does ONE
thing: real hybrid search (BM25 lexical + semantic vector) against a
single Elasticsearch index, using Elasticsearch's own built-in inference
API for embeddings, with automatic fallback to lexical-only search when
no inference endpoint is available.

This is the same pattern that runs the production blog this kit was
extracted from (see ``search.py`` and the ``_lexical_query`` /
``_semantic_query`` / hybrid-retriever code in ``app.py`` at the repo
root) — generalized so it isn't tied to that blog's post schema, admin
panel, or Flask routes. Nothing here imports Flask; ``example_app/``
shows one way to wire it into a web app, but ``hybrid_search`` itself
works the same way from a CLI script, a Django view, or a background job.

Two things intentionally are NOT in this package, on purpose:

- A vector database client. There isn't one. The whole point of this
  pattern is that Elasticsearch computes and stores the embeddings
  itself (via ``semantic_text`` + an inference endpoint), so there is no
  second system, no duplicate ETL pipeline, and no application-code
  logic to keep two stores' embeddings in sync with each other.
- An embedding model or API client. Elasticsearch calls its own
  configured inference endpoint (ELSER by default) internally when you
  index or query a ``semantic_text`` field. Your application code never
  computes, stores, or sends a vector.
"""

from .client import HybridSearchClient
from .query import build_hybrid_search_kwargs, build_lexical_query, build_semantic_query

__all__ = [
    'HybridSearchClient',
    'build_hybrid_search_kwargs',
    'build_lexical_query',
    'build_semantic_query',
]
