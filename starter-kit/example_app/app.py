"""Minimal end-to-end example: hybrid_search wired into a tiny Flask app.

This is deliberately small — one search form, one route, no admin panel,
no auth, no post rendering, no database beyond Elasticsearch itself. Its
only job is to show every piece of hybrid_search/ called in the order a
real app would call them:

  1. Connect (HybridSearchClient).
  2. Create the index with the hybrid-search mapping (create_index).
  3. Index some documents (index_documents).
  4. Search, letting the client's semantic_enabled state decide whether
     to run the hybrid retriever or the lexical-only fallback (search).

Run it:

    cd starter-kit/example_app
    pip install -r ../requirements.txt
    cp ../.env.example ../.env   # then fill in your ES connection details
    python app.py

On first run it seeds the index from data/sample_documents.json (a
handful of short docs about — appropriately — search infrastructure) and
starts a dev server at http://localhost:5050/. Try a lexical query like
"reciprocal rank fusion" and then a conceptual one like "why is my search
slow" — the second only surfaces the right document when
semantic_enabled is True (i.e. your cluster has a usable inference
endpoint; see the parent README for what that requires).
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, render_template, request

# Import hybrid_search from the sibling package directory without
# requiring `pip install -e .` — keeps "clone and run" friction-free for
# a starter kit. A real project would more likely install this package
# properly (see the parent README's "using this in your own project").
sys.path.insert(0, str(Path(__file__).parent.parent))
from hybrid_search import HybridSearchClient, search  # noqa: E402

load_dotenv(Path(__file__).parent.parent / '.env')

INDEX_NAME = 'starter_kit_example'
DATA_FILE = Path(__file__).parent / 'data' / 'sample_documents.json'

app = Flask(__name__)
client = HybridSearchClient()


def seed_if_missing():
    """Create the index and load the sample documents, but only if the
    index doesn't already exist — so restarting the dev server doesn't
    re-embed everything on every reload. Delete the index manually (or
    call client.create_index(INDEX_NAME) yourself) to force a reseed
    after changing the sample data or the mapping."""
    if client.es.indices.exists(index=INDEX_NAME):
        # Index already exists — but semantic_enabled is instance state,
        # set only by create_index(), so it still needs to be inferred
        # from the existing mapping for the fallback logic to work
        # correctly across restarts.
        mapping = client.es.indices.get_mapping(index=INDEX_NAME)
        properties = mapping[INDEX_NAME]['mappings'].get('properties', {})
        client.semantic_enabled = (
            properties.get('content_semantic', {}).get('type') == 'semantic_text'
        )
        return

    client.create_index(INDEX_NAME)
    with open(DATA_FILE) as f:
        documents = json.load(f)
    response = client.index_documents(INDEX_NAME, documents)
    failed = [item for item in response.get('items', [])
              if item.get('index', {}).get('error')]
    if failed:
        print(f'{len(failed)} document(s) failed to index: {failed[:3]}')
    mode = 'hybrid (BM25 + semantic)' if client.semantic_enabled else 'lexical-only (fallback)'
    print(f'Seeded {len(documents)} documents into "{INDEX_NAME}" — search mode: {mode}')


@app.get('/')
def index():
    query_text = request.args.get('q', '')
    results = []
    if query_text:
        response = search(client, INDEX_NAME, query_text, size=10)
        results = response['hits']['hits']
    return render_template(
        'search.html',
        query_text=query_text,
        results=results,
        semantic_enabled=client.semantic_enabled,
    )


if __name__ == '__main__':
    seed_if_missing()
    app.run(port=int(os.environ.get('PORT', 5050)), debug=False)
