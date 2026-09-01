![Screenshot 2024-10-16 at 2 17 11 PM](https://github.com/user-attachments/assets/4a4f3444-3c38-4981-b7b9-9d421ef6dad1)
![Screenshot 2024-10-16 at 2 16 54 PM](https://github.com/user-attachments/assets/68856874-a3db-40d7-81be-1e938f87ffbe)

# Elasticsearch Search - Flask Project

**Flask** project that demonstrates the implementation of various search techniques using **Elasticsearch**. It covers full-text keyword search, dense and sparse vector embedding searches, and result ranking using Elastic's **Reciprocal Rank Fusion (RRF)** algorithm.

## Overview

This project focuses on the following key search features:
- Performing **full-text keyword searches** on a dataset with optional filters.
- Generating, storing, and searching **dense vector embeddings** using a Machine Learning model.
- Utilizing the **ELSER model** to generate and search sparse vectors.
- Combining search results using **Elastic's Reciprocal Rank Fusion (RRF)** algorithm.

The project is **self-hosted** and runs locally via a connection to a self-hosted **Elasticsearch Docker Container**. It utilizes the **Flask** web framework to create a seamless and powerful search experience.

---

## Main Features

### 1. Elasticsearch Index Creation
- Created and optimized an Elasticsearch index to efficiently store and query data.

### 2. Full-Text Search Implementation
- Implemented **full-text search** using Elasticsearch queries.
- **Match Queries**: Used to find relevant documents across multiple fields.
- **Optimized Result Retrieval**: Tuned for quick and accurate retrieval of individual search results.

### 3. Multi-Field Search
- Configured Elasticsearch to perform searches across multiple fields simultaneously, enhancing the scope of search queries.

### 4. Pagination
- Implemented **pagination** to control the number of search results returned in smaller, manageable chunks (pages).

### 5. Boolean Queries & Filters
- **Boolean Queries**: Combined different queries (AND, OR, NOT) to refine search results.
- **Filtered Searches**: Incorporated range filters to further refine the search based on conditions such as dates, categories, or other numerical ranges.

### 6. Match-All Query
- Added support for **match-all queries**, retrieving all documents in the index.

### 7. Faceted Search
- Implemented **faceted search** in the left sidebar, allowing users to narrow down their searches based on predefined categories or attributes.

### 8. Term & Year Aggregations
- Added **Term Aggregations** for categorical data and **Year Aggregations** for date-based filtering, enhancing the precision of filtered searches.

---

## Running the Project

1. Have an Elasticsearch instance available (self-hosted via Docker, or Elastic Cloud) and note its URL or Cloud ID.
2. Clone the repository and navigate to the project directory.
3. Copy `.env.example` to `.env` and fill in `SECRET_KEY` (without it the app falls back to a random key that changes on every restart, invalidating any CSRF tokens in flight — set a real one before deploying) and your Elasticsearch connection details (`ES_URL`, or `ES_CLOUD_ID`/`ES_API_KEY` for Elastic Cloud).
4. `pip install -r requirements.txt`
5. `flask reindex` to load `data.json` into the Elasticsearch index.
6. `flask run`
7. Open the browser to view at http://localhost:5001/

Note: `FLASK_DEBUG` is intentionally not set in `.flaskenv`. The Werkzeug debugger it enables allows remote code execution if the app is ever exposed outside localhost — set it in your own shell for local debugging only, never in a committed file.
