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
    def create_index(self):
        self.es.indices.delete(index='my_documents', ignore_unavailable=True)
        self.es.indices.create(index='my_documents')

    # Every document is indexed with its own stable `id` (see content.py)
    # as the Elasticsearch document _id, rather than letting Elasticsearch
    # auto-assign one. That keeps /document/<id> URLs (and anything that
    # links or bookmarks them, including sitemap.xml) valid across
    # `flask reindex` runs and across admin edits, instead of changing on
    # every reindex the way an auto-generated id would.
    def index_document(self, document):
        return self.es.index(
            index='my_documents', id=document['id'], document=document
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
            operations.append(document)
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