import os
import re
import secrets

from dotenv import load_dotenv
from flask import Flask, Response, render_template, request, send_from_directory, url_for
from flask_wtf import CSRFProtect

from search import Search

load_dotenv()

app = Flask(__name__)

# SECRET_KEY signs the CSRF token below and any future session/cookie data.
# It must come from the environment, never be hardcoded in source. In
# production, set SECRET_KEY explicitly (see .env.example) so sessions
# survive restarts and stay valid across multiple worker processes; the
# random fallback below only exists so local development doesn't crash
# when the variable is unset, and a new one is generated (invalidating
# any outstanding tokens) every time the process restarts.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
if not os.environ.get('SECRET_KEY'):
    app.logger.warning(
        'SECRET_KEY is not set; using a random, ephemeral key for this '
        'process. Set SECRET_KEY in the environment before deploying.'
    )

csrf = CSRFProtect(app)

es = Search()

SITE_NAME = 'Elastic Search Blog'
SITE_DESCRIPTION = (
    'An Elasticsearch-powered blog search and discovery platform built '
    'with Flask, demonstrating full-text keyword search, boolean '
    'filtering, faceted navigation, and result ranking.'
)


@app.get('/')
def index():
    return render_template(
        'index.html',
        page_title=f'{SITE_NAME} – Search Engineering & Career Articles',
        meta_description=(
            'Search articles on software engineering careers, coding '
            'bootcamps, and tech industry topics, powered by an '
            'Elasticsearch full-text search index.'
        ),
    )


@app.post('/')
def handle_search():
    query = request.form.get('query', '')
    filters, parsed_query = extract_filters(query)
    from_ = request.form.get('from_', type=int, default=0)
    
    if parsed_query:
        search_query = {
            'must': {
                'multi_match': {
                    'query': parsed_query,
                    'fields': ['name', 'summary', 'content'],
                }
            }
        }
    else:
        search_query = {
            'must': {
                'match_all': {}
            }
        }
        
    results = es.search(
        query={
            'bool': {
                **search_query,
                **filters
            }
        },
        aggs={
            'category-agg': {
                'terms': {
                    'field': 'category.keyword',
                }
            },
            'year-agg': {
                'date_histogram': {
                    'field': 'updated_at',
                    'calendar_interval': 'year',
                    'format': 'yyyy',
                },
            },
        },
        size=5,
        from_=from_
    )
    aggs = {
        'Category': {
            bucket['key']: bucket['doc_count']
            for bucket in results['aggregations']['category-agg']['buckets']
        },
        'Year': {
            bucket['key_as_string']: bucket['doc_count']
            for bucket in results['aggregations']['year-agg']['buckets']
            if bucket['doc_count'] > 0
        },
    }
    
    return render_template(
        'index.html', results=results['hits']['hits'],
        query=query, from_=from_,
        total=results['hits']['total']['value'], aggs=aggs,
        page_title=f'{SITE_NAME} – Search Engineering & Career Articles',
        meta_description=(
            f'{results["hits"]["total"]["value"]} article'
            f'{"s" if results["hits"]["total"]["value"] != 1 else ""} found'
            f' for "{query}" in the Elasticsearch-powered article index.'
            if query else
            'Browse all indexed articles on software engineering careers, '
            'coding bootcamps, and tech industry topics.'
        ),
    )

# retrieve the document by its id
@app.get('/document/<id>')
def get_document(id):
    document = es.retrieve_document(id)
    title = document['_source']['name']
    summary = document['_source'].get('summary', SITE_DESCRIPTION)
    paragraphs = document['_source']['content'].split('\n')
    return render_template(
        'document.html', title=title, paragraphs=paragraphs,
        page_title=f'{title} – {SITE_NAME}',
        meta_description=summary,
    )


@app.get('/robots.txt')
def robots_txt():
    lines = [
        'User-agent: *',
        'Allow: /',
        '',
        f'Sitemap: {url_for("sitemap_xml", _external=True)}',
        '',
    ]
    return Response('\n'.join(lines), mimetype='text/plain')


@app.get('/llms.txt')
def llms_txt():
    return send_from_directory(app.root_path, 'llms.txt', mimetype='text/plain')


@app.get('/sitemap.xml')
def sitemap_xml():
    pages = [{
        'loc': url_for('index', _external=True),
        'changefreq': 'weekly',
        'priority': '1.0',
    }]
    try:
        results = es.search(query={'match_all': {}}, size=1000)
        for hit in results['hits']['hits']:
            source = hit['_source']
            pages.append({
                'loc': url_for('get_document', id=hit['_id'], _external=True),
                'lastmod': source.get('updated_at') or source.get('created_on'),
                'changefreq': 'monthly',
                'priority': '0.7',
            })
    except Exception:
        # If Elasticsearch is unreachable, still serve a valid sitemap
        # containing at least the homepage rather than a 500.
        app.logger.exception('Could not list documents for sitemap.xml')
    xml = render_template('sitemap.xml', pages=pages)
    return Response(xml, mimetype='application/xml')

# expose method through flask and registers the func as a custom command
# can run 'flask reindex' in the terminal to regenerate the index
@app.cli.command()
def reindex():
    """Regenerate the Elasticsearch index."""
    response = es.reindex()
    items = response['items']
    took = response['took']
    print(f'Index with {len(items)} documents created in {took} milliseconds.')
    
""" extract_filters accepts query and returns tuple with the filters then modified query"""    
def extract_filters(query):
    filters = []
    
    filter_regex = r'category:([^\s]+)\s*'
    m = re.search(filter_regex, query)
    if m:
        filters.append({
            'term': {
                'category.keyword': {
                    'value': m.group(1)
                }
            }
        })
        query = re.sub(filter_regex, '', query).strip()
        
    filter_regex = r'year:([^\s]+)\s*'
    m = re.search(filter_regex, query)
    if m:
        filters.append({
            'range': {
                'updated_at': {
                    'gte': f'{m.group(1)}||/y',
                    'lte': f'{m.group(1)}||/y',
                }
            },
        })
        query = re.sub(filter_regex, '', query).strip()
    
    return {'filter': filters}, query