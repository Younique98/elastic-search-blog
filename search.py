import json
from pprint import pprint
import os
import time

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

load_dotenv()


class Search:
    def __init__(self):
        self.es = Elasticsearch('http://localhost:9200')  # <-- connection options need to be added here
        client_info = self.es.info()
        print('Connected to Elasticsearch!')
        pprint(client_info.body)

# create_index first deletes an index then ignores unavailable prevents call from failing when index name is not found and creates a new index with the same name
    def create_index(self):
        self.es.indices.delete(index='my_documents', ignore_unavailable=True)
        self.es.indices.create(index='my_documents')
        
    def insert_document(self, document):
        return self.es.index(index='my_documents', body = document)
    
# use the bulk insertion feature of the Elasticsearch service to reduce performance cost with each API call and avoid rate limits
# this method accepts a list of documents and inserts them separately into the Elasticsearch index
    def insert_documents(self, documents):
        operations = []
        for document in documents:
            operations.append({'index': {'_index': 'my_documents'}})
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