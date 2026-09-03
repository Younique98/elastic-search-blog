# RetrievalKit

> Self-hostable hybrid search and RAG retrieval infrastructure for engineering teams building AI agents and RAG pipelines — running entirely on the Elasticsearch cluster you already operate. No second vector database, no external embedding service, no new infra to adopt.

## The problem

Every team building a RAG pipeline or an AI agent needs retrieval, and the default answer today is "add a vector database" — Pinecone, Qdrant, Weaviate — next to whatever search or storage infrastructure already exists. That's a second system to operate, a second place data can drift out of sync, and a second bill. Teams that already run Elasticsearch for logs, product search, or general full-text search are paying for retrieval capability twice: once for BM25 search they already have, and again for semantic/vector search bolted on separately.

## What RetrievalKit does instead

RetrievalKit runs hybrid retrieval — BM25 lexical search and semantic search — as a single query against a single Elasticsearch index, using Elasticsearch's own built-in inference API to compute embeddings server-side. There is no separate embedding service to call, no vectors to manage in application code, and no second database. If a team already has Elasticsearch, RetrievalKit is the difference between "buy a vector database" and "turn on a feature."

Concretely:

- **Hybrid retrieval** — a query runs as two retrievers (BM25 `multi_match` and Elasticsearch's `semantic` query type) merged with Reciprocal Rank Fusion, so results are ranked well whether the match is lexical (the query contains the right words) or conceptual (it doesn't, but means the same thing).
- **Zero external ML dependency** — embeddings are computed by Elasticsearch's built-in inference endpoint (ELSER by default), not a model your application downloads, hosts, or calls out to. This is what makes it self-hostable in practice, not just in theory.
- **Graceful degradation** — if a cluster has no inference endpoint available (older version, no ML node), RetrievalKit automatically falls back to lexical-only search instead of refusing to run.
- **Faceted filtering and highlighting** — category/tag/date filters and matched-term highlighting work the same way whether the underlying match was lexical or semantic.
- **A lightweight admin panel** — create, edit, and delete indexed documents from an authenticated `/admin` panel; every save re-embeds and re-indexes immediately.

## Try it

The homepage runs a live search against a sample engineering-documentation corpus (incident response, API design, deployment, security, and similar topics) so you can see hybrid retrieval work on a real query before pointing it at your own data — try a conceptual query like `why do requests fail under load` and note that it can surface the right document without needing to share any of its exact words.

## Stack

- Backend: Python, Flask, Flask-Login (single-admin authentication), Flask-WTF (forms/CSRF)
- Retrieval: Elasticsearch — `retriever`-based hybrid search (RRF across a `standard` BM25 retriever and a `standard` retriever against a `semantic_text` field), term/range filters, terms and date-histogram aggregations, highlighting, `more_like_this` for related-document surfacing
- Templates: Jinja2

## Running the project

1. Have an Elasticsearch instance available (self-hosted via Docker, or Elastic Cloud/Serverless) and note its URL or Cloud ID. Elastic Cloud and Serverless ship the `.elser-2-elasticsearch` inference endpoint preconfigured — hybrid search works out of the box. A self-managed cluster without an ML node will still run, in lexical-only mode.
2. Clone the repository and navigate to the project directory.
3. `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and fill in:
   - `SECRET_KEY` (without it the app falls back to a random key that changes on every restart, invalidating CSRF tokens and admin sessions in flight — set a real one before deploying).
   - Your Elasticsearch connection details (`ES_URL`, or `ES_CLOUD_ID`/`ES_API_KEY` for Elastic Cloud).
   - `ADMIN_USERNAME` and `ADMIN_PASSWORD_HASH` for the admin panel — generate the hash with `flask hash-password 'your-chosen-password'` (never put the plaintext password itself in `.env`).
5. `flask reindex` to load `data.json` into the Elasticsearch index (this also runs the embedding step for every document, via Elasticsearch's inference endpoint).
6. `flask run`
7. Open the browser at http://localhost:5001/ for the demo search, or http://localhost:5001/admin/login to manage documents.

Note: `FLASK_DEBUG` is intentionally not set in `.flaskenv`. The Werkzeug debugger it enables allows remote code execution if the app is ever exposed outside localhost — set it in your own shell for local debugging only, never in a committed file.
