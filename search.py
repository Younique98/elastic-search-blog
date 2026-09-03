import json
from pprint import pprint
import os
import time

from dotenv import load_dotenv
from elasticsearch import Elasticsearch, NotFoundError

load_dotenv()


class Search:
    def __init__(self):
        # Connection details come from the environment (see .env.example)
        # rather than being hardcoded, so credentials/cloud IDs never end up
        # committed to source control and the app can point at a different
        # cluster per environment without a code change.
        es_url = os.environ.get('ES_URL', 'http://localhost:9200')
        es_cloud_id = os.environ.get('ES_CLOUD_ID')
        es_api_key = os.environ.get('ES_API_KEY')
        es_username = os.environ.get('ES_USERNAME')
        es_password = os.environ.get('ES_PASSWORD')

        # The inference endpoint that computes semantic embeddings for the
        # `content_semantic` field, entirely inside the cluster — no
        # external embedding model, API key, or vector database required.
        # `.elser-2-elasticsearch` is Elastic's built-in sparse-embedding
        # endpoint, preconfigured on Elastic Cloud and Serverless. A
        # self-managed cluster without an ML node (or an older version)
        # won't have it; see the fallback in create_index() below.
        self.inference_id = os.environ.get('ES_INFERENCE_ID', '.elser-2-elasticsearch')
        # Set once create_index() runs, so search() knows whether it's safe
        # to add the semantic retriever or whether this cluster can only
        # do lexical (BM25) search.
        self.semantic_enabled = False

        client_kwargs = {}
        if es_api_key:
            client_kwargs['api_key'] = es_api_key
        elif es_username and es_password:
            client_kwargs['basic_auth'] = (es_username, es_password)

        if es_cloud_id:
            self.es = Elasticsearch(cloud_id=es_cloud_id, **client_kwargs)
        else:
            self.es = Elasticsearch(es_url, **client_kwargs)

        client_info = self.es.info()
        print('Connected to Elasticsearch!')
        pprint(client_info.body)

    # create_index first deletes an index then ignores unavailable prevents call from failing when index name is not found and creates a new index with the same name
    #
    # Tries to create the index with `content_semantic` mapped as
    # `semantic_text` (hybrid lexical+semantic retrieval, the actual
    # product). If the cluster can't support that — no ML node, no
    # `.elser-2-elasticsearch` endpoint, or a pre-8.15 version — falls back
    # to a plain index so the app still runs in BM25-only mode instead of
    # refusing to start. semantic_enabled reflects which mode is live.
    def create_index(self):
        self.es.indices.delete(index='my_documents', ignore_unavailable=True)
        try:
            self.es.indices.create(
                index='my_documents',
                mappings={
                    'properties': {
                        'content_semantic': {
                            'type': 'semantic_text',
                            'inference_id': self.inference_id,
                        },
                    },
                },
            )
            self.semantic_enabled = True
        except Exception:
            print(
                f'Could not create the index with semantic_text on '
                f'inference endpoint "{self.inference_id}" — falling back '
                f'to lexical-only search. Set ES_INFERENCE_ID if this '
                f'cluster uses a different endpoint id, or deploy '
                f'.elser-2-elasticsearch (Elastic Cloud/Serverless has it '
                f'preconfigured).'
            )
            self.es.indices.create(index='my_documents')
            self.semantic_enabled = False

    def _prepare(self, document):
        """Attach the field the semantic retriever reads from. A shallow
        copy so callers' dicts (e.g. content.py's in-memory posts) aren't
        mutated by a side effect of indexing them."""
        if not self.semantic_enabled:
            return document
        doc = dict(document)
        doc['content_semantic'] = doc.get('content', '')
        return doc

    # Every document is indexed with its own stable `id` (see content.py)
    # as the Elasticsearch document _id, rather than letting Elasticsearch
    # auto-assign one. That keeps /document/<id> URLs (and anything that
    # links or bookmarks them, including sitemap.xml) valid across
    # `flask reindex` runs and across admin edits, instead of changing on
    # every reindex the way an auto-generated id would.
    def index_document(self, document):
        return self.es.index(
            index='my_documents', id=document['id'], document=self._prepare(document)
        )

    def delete_document(self, id):
        try:
            return self.es.delete(index='my_documents', id=id)
        except NotFoundError:
            return None

# use the bulk insertion feature of the Elasticsearch service to reduce performance cost with each API call and avoid rate limits
# this method accepts a list of documents and inserts them separately into the Elasticsearch index
    def insert_documents(self, documents):
        operations = []
        for document in documents:
            operations.append({'index': {'_index': 'my_documents', '_id': document['id']}})
            operations.append(self._prepare(document))
        return self.es.bulk(operations=operations)

# to regenerate the index
    def reindex(self):
        self.create_index()
        with open('data.json', 'rt') as f:
            documents = json.loads(f.read())
        return self.insert_documents(documents)

    def search(self, **query_args):
        return self.es.search(index='my_documents', **query_args)

    # renders individual documents
    def retrieve_document(self, id):
        return self.es.get(index='my_documents', id=id)

    # "More like this" — Elasticsearch scores every other document in the
    # index by textual similarity to the given one, which is how the
    # document page's "Related articles" section is generated without any
    # manual tagging/curation work from whoever is writing posts.
    def more_like_this(self, id, size=3):
        return self.es.search(
            index='my_documents',
            query={
                'more_like_this': {
                    'fields': ['name', 'summary', 'content'],
                    'like': [{'_index': 'my_documents', '_id': id}],
                    'min_term_freq': 1,
                    'min_doc_freq': 1,
                }
            },
            size=size,
        )