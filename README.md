![Screenshot 2024-10-16 at 2 17 11 PM](https://github.com/user-attachments/assets/4a4f3444-3c38-4981-b7b9-9d421ef6dad1)
![Screenshot 2024-10-16 at 2 16 54 PM](https://github.com/user-attachments/assets/68856874-a3db-40d7-81be-1e938f87ffbe)
# Elasticsearch Search

This directory contains a starter Flask project.

How to perform full-text keyword searches on a dataset, optionally with filters
How to generate, store and search dense vector embeddings using a Machine Learning model
How to use the ELSER model to generate and search sparse vectors
How to combine search results from the methods listed above using Elastic's Reciprocal Rank Fusion (RRF) algorithm

This is being self-hosted and run on your locally via a connection to a Self-Hosted Elasticsearch Docker Container

Utilized the Flask web framework

Main Features
Created an Elasticsearch Index
Implemented Full-Text search
Including Elasticsearch Queries, Match Queries
Optimized to Retrieve Individual Results
Searching Multiple Fields
Pagination to control requests in smaller chunks/pages
Filters using Boolean Queries and filtered searches and range filters
Utlized the match-all query
Addition of Faceted Search in left sidebar
Term Aggregations
Year Aggregations