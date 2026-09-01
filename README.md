![Screenshot 2024-10-16 at 2 17 11 PM](https://github.com/user-attachments/assets/4a4f3444-3c38-4981-b7b9-9d421ef6dad1)
![Screenshot 2024-10-16 at 2 16 54 PM](https://github.com/user-attachments/assets/68856874-a3db-40d7-81be-1e938f87ffbe)

# Elastic Search Blog

A self-hostable, **Elasticsearch-powered search-and-discovery layer** for a blog or documentation site — the kind of relevance-ranked, typo-tolerant, faceted search you'd normally pay a hosted SaaS product like Algolia for, running entirely on infrastructure you control.

**Why this instead of a SQL `LIKE '%query%'` search?** A substring match can only tell you whether a word is *present* — it can't rank results by relevance, tolerate a typo, highlight what matched, or let visitors filter by category/tag/year. Elasticsearch does all of that natively; this project wires it up behind a small Flask app so you don't have to.

**Who it's for:** bloggers, small documentation sites, and content platforms that want real search over their own content without adopting a hosted SaaS search vendor or standing up a heavier search infrastructure than they need — and are willing to run (or already run) Elasticsearch.

---

## Features

### Search
- **Relevance-ranked full-text search** across title, summary, and body via a boosted, fuzzy `multi_match` query — typos and near-matches still find the right article.
- **Matched-term highlighting** in results (`<mark>` around what matched), safely HTML-escaped so indexed content can never reintroduce markup/script injection.
- **Faceted filtering** by category, tag, and year, both via the sidebar and inline query syntax (`category:job interviews`, `tag:python`, `year:2024`).
- **Related articles** on every post, generated with Elasticsearch's `more_like_this` — no manual tagging or curation required.
- **Pagination** over large result sets.

### Content management
- An authenticated `/admin` panel (single self-hosted admin account) to create, edit, and delete posts — no more hand-editing `data.json` and re-running `flask reindex` for every change.
- Every save writes through to `data.json` (the durable content store) and updates the live Elasticsearch index immediately.

### Production-readiness
- CSRF protection, environment-configured secrets/credentials (nothing hardcoded), and no debug mode by default.
- `robots.txt`, `sitemap.xml` (generated live from the index), and `llms.txt` for search engines and AI crawlers.
- Per-page titles and meta descriptions; WCAG AA-checked templates.

---

## Running the Project

1. Have an Elasticsearch instance available (self-hosted via Docker, or Elastic Cloud) and note its URL or Cloud ID.
2. Clone the repository and navigate to the project directory.
3. `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and fill in:
   - `SECRET_KEY` (without it the app falls back to a random key that changes on every restart, invalidating CSRF tokens and admin sessions in flight — set a real one before deploying).
   - Your Elasticsearch connection details (`ES_URL`, or `ES_CLOUD_ID`/`ES_API_KEY` for Elastic Cloud).
   - `ADMIN_USERNAME` and `ADMIN_PASSWORD_HASH` for the admin panel — generate the hash with `flask hash-password 'your-chosen-password'` (never put the plaintext password itself in `.env`).
5. `flask reindex` to load `data.json` into the Elasticsearch index.
6. `flask run`
7. Open the browser at http://localhost:5001/ for the site, or http://localhost:5001/admin/login to manage posts.

Note: `FLASK_DEBUG` is intentionally not set in `.flaskenv`. The Werkzeug debugger it enables allows remote code execution if the app is ever exposed outside localhost — set it in your own shell for local debugging only, never in a committed file.
