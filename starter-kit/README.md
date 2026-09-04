# Elasticsearch Search Starter Kit

A reference implementation of real hybrid search — BM25 lexical + semantic
vector, merged with Reciprocal Rank Fusion, in one Elasticsearch index —
with automatic fallback to lexical-only search when no inference endpoint
is available. This is the exact pattern running the production blog this
kit was extracted from ([`search.py`](../search.py) and the
`_lexical_query` / `_semantic_query` / RRF-retriever code in
[`app.py`](../app.py) at the repo root) — not a tutorial written
separately from what actually ships.

## The problem this solves

The default answer to "we want semantic search" is: keep Elasticsearch (or
whatever you already use for full-text search) for lexical matching, and
add a *second* system — Pinecone, Qdrant, Weaviate, pgvector-as-its-own-service
— for vector/semantic matching. That decision quietly creates:

- **A duplicate ETL pipeline.** Every document now has to be written to
  two places, kept in sync, and reconciled when one write succeeds and
  the other fails.
- **Data silos and consistency drift.** The vector store's copy of a
  document and the search index's copy can disagree — deleted-but-not-yet-purged,
  updated-in-one-but-not-the-other — and nothing forces them back in sync.
- **Multi-hop queries stitched together in application code.** "Hybrid
  search" becomes: query system A, query system B, fetch both result
  sets, merge and re-rank them yourself, usually with an ad hoc scoring
  formula that's never been tuned against real relevance data. That
  merge step runs in your request path, adds a second network round
  trip, and is exactly the kind of thing that gets slow and flaky under
  load precisely when search matters most.

Elasticsearch (8.15+, or Elastic Cloud/Serverless) can do the semantic
half itself: a `semantic_text` field type that computes embeddings
in-cluster via a built-in inference endpoint (ELSER by default — a
sparse embedding model, no external API key or hosted model required),
queried with a `semantic` query clause. Run that alongside a normal BM25
query as two `standard` sub-retrievers under one `rrf` retriever, and you
get hybrid search as a single query against a single index. No second
system, no duplicate pipeline, no drift.

## What's in this kit

```
starter-kit/
  hybrid_search/          # the reusable package — no Flask dependency
    client.py             #   connect, create the hybrid-search index mapping
    query.py              #   build lexical / semantic / RRF-hybrid queries
  example_app/            # minimal Flask app wiring hybrid_search together
    app.py
    templates/search.html
    data/sample_documents.json
  tests/                  # unit tests, no Elasticsearch cluster required
    test_client.py
    test_query_builder.py
  requirements.txt
  .env.example
```

`hybrid_search/` is the actual product: a small, framework-agnostic
package (import it from a Flask view, a Django view, a script, a
background job — it only imports `elasticsearch-py`) with three moving
parts:

- **`HybridSearchClient.create_index()`** — creates an index with a
  `semantic_text` field pointed at your inference endpoint. If the
  cluster can't support that (no ML node, no ELSER deployed, a version
  too old), it catches the failure and creates a plain index instead,
  setting `semantic_enabled = False` rather than raising.
- **`build_hybrid_search_kwargs()`** — the query builder. Given
  `semantic_enabled` (read from the client above), returns either an
  `rrf` retriever block running both a lexical and a semantic
  sub-retriever, or a plain lexical `query` block. Same call site, two
  possible shapes, decided by one boolean.
- **`search()`** — a thin convenience wrapper that reads a client's
  `semantic_enabled` state and calls `es.search()` with the right kwargs.

`example_app/` is not the product — it's the smallest possible proof
that the three pieces above actually work together end to end: one
Flask route, one search form, six sample documents about search/infra
concepts (deliberately including a couple where the right answer to a
conceptual query doesn't share any exact words with the query — that's
what a working semantic retriever should surface and a lexical-only
fallback should miss).

## What's deliberately NOT in this kit

Stripped out relative to the blog it came from, on purpose: no admin
panel, no authentication, no post rendering/routing, no highlighting,
no faceted aggregations, no `more_like_this`, no database beyond
Elasticsearch itself. Those are real things the parent app has, but
they're blog concerns, not hybrid-search concerns — adding them back
here would make this harder to read as a reference, not more useful as
one.

## Setup

### 1. Get an Elasticsearch cluster

**Elastic Cloud or Serverless** — the ELSER inference endpoint
(`.elser-2-elasticsearch`) is preconfigured. Hybrid search works with
zero extra ML setup; grab your Cloud ID and an API key from the
Elastic Cloud console.

**Local Elasticsearch with Docker** (single node, for trying this kit
out — not a production topology):

```bash
docker run -d --name es-starter-kit \
  -p 9200:9200 \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  -e "ES_JAVA_OPTS=-Xms1g -Xmx1g" \
  docker.elastic.co/elasticsearch/elasticsearch:8.17.2
```

A self-managed single-node cluster like this has **no ML node and no
ELSER deployed by default** — `create_index()` will hit the fallback
branch and you'll get lexical-only search, correctly, not an error.
That's the fallback path working as designed, not a broken setup. To
get real hybrid search locally you need to deploy an inference endpoint
yourself (`PUT _inference/sparse_embedding/.elser-2-elasticsearch` with
an ML-node-capable cluster) — worth doing once to see hybrid search
actually run, but Elastic Cloud/Serverless is the realistic path for
running this in anger, not a bare local Docker container.

### 2. Configure and install

```bash
cd starter-kit
cp .env.example .env    # fill in ES_URL or ES_CLOUD_ID + ES_API_KEY
pip install -r requirements.txt
```

### 3. Run the example app

```bash
cd example_app
python app.py
```

Open `http://localhost:5050/`. It seeds the index from
`data/sample_documents.json` on first run and tells you at startup
whether it came up in hybrid or lexical-only mode. Try a lexical query
("reciprocal rank fusion") and a conceptual one ("why is my search
slow") — the conceptual query only surfaces the connection-pool-exhaustion
document via the semantic half of the query, since it shares almost no
exact words with it.

### 4. Run the tests

```bash
cd starter-kit
pytest tests/
```

13 tests, all mocked against a fake Elasticsearch client — no cluster
required. They check two things specifically: that the RRF retriever
block is actually built correctly when semantic search is available,
and that the exact same call falls back to a plain lexical query
(never raises, never references the semantic field) when it isn't.

### 5. Using this in your own project

`hybrid_search/` has no dependency on `example_app/` or on Flask. Copy
the directory into your project, `pip install elasticsearch`, and:

```python
from hybrid_search import HybridSearchClient, search

client = HybridSearchClient()          # reads ES_URL/ES_CLOUD_ID/etc. from env
client.create_index('my_index')        # sets client.semantic_enabled
client.index_documents('my_index', my_docs)  # my_docs: list of dicts with an 'id' and 'content'

response = search(client, 'my_index', 'why is search slow')
```

Swap in your own document shape by passing `fields=[...]` to `search()`
(or directly to `build_hybrid_search_kwargs`) — the kit's `title`/`content`
field names are just the sample app's schema, not a requirement.

## Common pitfalls

**RAM overhead.** ELSER is a real model running on your cluster's ML
node(s), not a lightweight side effect of indexing. Budget a
dedicated ML node with a few GB of headroom beyond what your data
nodes need — under-provisioning it is the most common reason people
report semantic search being "too slow to use," when the actual
problem is the inference endpoint starving for memory, not the query
itself.

**Indexing lag under load.** Every document write to a `semantic_text`
field triggers an inference call before the document is actually
indexed — that's slower than a plain lexical field write, by
construction. On a large bulk load this can create a visible lag
between "the API call returned" and "the document is actually
searchable," worse than lexical-only indexing. `HybridSearchClient.index_documents()`
uses `refresh='wait_for'` for correctness in the example app (and in
tests) — drop that for high-throughput production indexing, where
occasionally serving a slightly-stale search result is a better
trade-off than blocking every write on a refresh.

**Why not just run two systems anyway "for now"?** It's tempting to
treat a vector database as the fast path and Elasticsearch as legacy
lexical search you'll migrate off eventually. In practice that
"eventually" is where the real costs show up: two write paths to keep
correct under partial failure, two systems to monitor and page on, and
an application-code merge step that has to be re-tuned by hand every
time relevance looks wrong — versus RRF, which Elasticsearch runs for
you, tuned by two numbers (`rank_window_size`, `rank_constant`) instead
of a bespoke scoring function. If you already operate Elasticsearch,
the honest comparison isn't "vector DB vs. nothing" — it's "one
inference endpoint to configure vs. a second production system to run
forever."

## Realistic expectations

This is a reference implementation to adapt, not a drop-in library or a
managed service. It has no auth, no rate limiting, no production
deployment tooling, no support contract, and the sample data is six
short paragraphs, not a real corpus. What it *does* give you: a query
structure and a fallback pattern that took real iteration to get right
on a production system, unit tests that pin down exactly what "hybrid"
and "fallback" mean in code (not just in a diagram), and a working
example you can run today to see it in front of you before you build
your own.
