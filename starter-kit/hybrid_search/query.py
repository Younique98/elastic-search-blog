"""Query builders for hybrid (BM25 + semantic) search.

This is a direct generalization of the query-building functions in the
parent repo's ``app.py`` (``_lexical_query``, ``_semantic_query``, and
the ``retriever``/``rrf`` block in ``handle_search``) — same query
shapes, same fallback branch, with the blog's specific field names
(``name``, ``summary``) replaced by configurable arguments so this works
against any document schema.

Nothing here talks to Elasticsearch directly except ``search()``, which
just calls ``es.search(**kwargs)`` with whatever ``build_hybrid_search_kwargs``
built — every other function here is a pure dict builder, which is what
makes them unit-testable without a real cluster (see tests/test_query_builder.py).
"""


def build_lexical_query(query_text, *, fields=('title^2', 'content'),
                         fuzziness='AUTO', filters=None):
    """The BM25 half of hybrid search: a standard `multi_match` full-text
    query. `fuzziness='AUTO'` tolerates small typos. Falls back to
    `match_all` when there's no query text, so an empty search still
    returns a (filtered, if any) result set instead of matching nothing.

    `fields` takes Elasticsearch's `field^boost` syntax — boost the
    fields that matter more for relevance in your schema (a title/name
    field, typically) the same way the parent blog boosts `name^2`.
    """
    must = (
        {
            'multi_match': {
                'query': query_text,
                'fields': list(fields),
                'fuzziness': fuzziness,
            }
        }
        if query_text else {'match_all': {}}
    )
    return {'bool': {'must': must, **(filters or {})}}


def build_semantic_query(query_text, *, semantic_field='content_semantic',
                          filters=None):
    """The semantic half: a `semantic` query against a `semantic_text`
    field. Elasticsearch embeds `query_text` with the same inference
    endpoint the field was indexed with and matches by vector similarity
    — your application never computes or handles a vector directly.
    Only valid against a cluster where `semantic_enabled` is True (see
    HybridSearchClient.create_index); build_hybrid_search_kwargs below
    is what decides whether to call this at all.
    """
    must = (
        {'semantic': {'field': semantic_field, 'query': query_text}}
        if query_text else {'match_all': {}}
    )
    return {'bool': {'must': must, **(filters or {})}}


def build_hybrid_search_kwargs(query_text, *, semantic_enabled,
                                fields=('title^2', 'content'),
                                semantic_field='content_semantic',
                                filters=None, size=10,
                                rank_window_size=50, rank_constant=20,
                                extra=None):
    """The actual decision point of this whole kit: build the keyword
    arguments to pass to `es.search(**kwargs)`.

    When `semantic_enabled` is True, returns a `retriever` block that
    runs BOTH the lexical and semantic queries above as `standard`
    sub-retrievers and merges their rankings with Reciprocal Rank Fusion
    (RRF) — one query, one round trip, one index. That merge is what
    "hybrid search" actually means here: a document can rank well
    because it matches the words in the query (lexical) or because it
    means the same thing without using those words (semantic), and RRF
    combines both signals into a single ranked list without you having
    to hand-weight lexical vs. semantic scores yourself.

    When `semantic_enabled` is False — no inference endpoint on this
    cluster (see HybridSearchClient.create_index) — returns a plain
    `query` block using only the lexical query. This is the fallback
    path: same function, same call site, a working (if less capable)
    result set instead of an exception. This is also the branch you want
    covered by a unit test with no Elasticsearch running at all (see
    tests/test_query_builder.py) — it's the one query-shape difference
    that's easy to break without noticing, since it only manifests on a
    cluster without ELSER deployed.

    `rank_window_size` / `rank_constant` are RRF's two tuning knobs:
    `rank_window_size` is how many results *each* sub-retriever
    considers before merging (raise it if relevant documents are ranked
    outside the top results by one retriever but not the other);
    `rank_constant` controls how much weight a result's rank position
    carries in the fused score (Elasticsearch's own default is 60; this
    kit uses 20, the same value the parent blog runs in production,
    which favors documents that rank well in either retriever over ones
    that rank only moderately in both — tune per your own relevance
    testing, this isn't a value to treat as fixed).

    `extra` merges in anything else `es.search()` accepts — `highlight`,
    `aggs`, `sort`, and so on — so callers aren't limited to what this
    function anticipates.
    """
    kwargs = dict(size=size)
    if semantic_enabled:
        kwargs['retriever'] = {
            'rrf': {
                'retrievers': [
                    {'standard': {
                        'query': build_lexical_query(
                            query_text, fields=fields, filters=filters,
                        ),
                    }},
                    {'standard': {
                        'query': build_semantic_query(
                            query_text, semantic_field=semantic_field, filters=filters,
                        ),
                    }},
                ],
                'rank_window_size': rank_window_size,
                'rank_constant': rank_constant,
            }
        }
    else:
        kwargs['query'] = build_lexical_query(query_text, fields=fields, filters=filters)

    if extra:
        kwargs.update(extra)
    return kwargs


def search(client, index_name, query_text, **kwargs):
    """Convenience wrapper: build the right query kwargs for `client`'s
    current `semantic_enabled` state and run it. Equivalent to:

        kwargs = build_hybrid_search_kwargs(query_text, semantic_enabled=client.semantic_enabled, **kwargs)
        return client.es.search(index=index_name, **kwargs)

    Most callers want this; the builder functions above are exposed
    separately mainly so they can be unit-tested (and reused) without an
    Elasticsearch client at all.
    """
    search_kwargs = build_hybrid_search_kwargs(
        query_text, semantic_enabled=client.semantic_enabled, **kwargs
    )
    return client.es.search(index=index_name, **search_kwargs)
