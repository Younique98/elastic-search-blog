import os
import re
import secrets

import click
from dotenv import load_dotenv
from elasticsearch import NotFoundError
from flask import (
    Flask, Response, abort, flash, redirect, render_template, request,
    send_from_directory, url_for,
)
from flask_login import (
    current_user, login_required, login_user, logout_user,
)
from flask_wtf import CSRFProtect
from markupsafe import Markup, escape
from werkzeug.security import generate_password_hash

import content
from auth import AdminUser, login_manager, verify_admin_credentials
from forms import LoginForm, PostForm
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
login_manager.init_app(app)

es = Search()

SITE_NAME = 'RetrievalKit'
SITE_TAGLINE = 'Hybrid search & RAG retrieval on the Elasticsearch you already run'
SITE_DESCRIPTION = (
    'RetrievalKit is self-hostable hybrid retrieval infrastructure for '
    'engineering teams building RAG pipelines and AI agents on '
    'Elasticsearch — combining BM25 lexical search with semantic '
    'retrieval via Elasticsearch’s built-in inference, so you don’t '
    'adopt a second vector database next to the search cluster you '
    'already operate.'
)

# Elasticsearch highlighting wraps matched terms with these markers. They
# are unusual control characters, never real article text, so after the
# whole fragment is HTML-escaped (defeating any XSS in the underlying
# content) they can be safely swapped for literal <mark> tags without
# reopening the escaping that was just done. See highlighted_field() below
# and the note in the original security audit about |safe/Markup() usage.
_HL_OPEN, _HL_CLOSE = '', ''


def highlighted_field(hit, field, fallback):
    """Return a Markup-safe, HTML-escaped rendering of a search hit's
    field, with any Elasticsearch-matched terms wrapped in <mark>."""
    fragments = hit.get('highlight', {}).get(field)
    text = fragments[0] if fragments else fallback
    safe_text = str(escape(text))
    safe_text = safe_text.replace(_HL_OPEN, '<mark>').replace(_HL_CLOSE, '</mark>')
    return Markup(safe_text)


# ---------------------------------------------------------------------------
# Public site
# ---------------------------------------------------------------------------

@app.get('/')
def index():
    return render_template(
        'index.html',
        page_title=f'{SITE_NAME} – {SITE_TAGLINE}',
        meta_description=SITE_DESCRIPTION,
    )


def _lexical_query(parsed_query, filters):
    must = (
        {
            'multi_match': {
                'query': parsed_query,
                'fields': ['name^2', 'summary', 'content'],
                'fuzziness': 'AUTO',
            }
        }
        if parsed_query else {'match_all': {}}
    )
    return {'bool': {'must': must, **filters}}


def _semantic_query(parsed_query, filters):
    must = (
        {'semantic': {'field': 'content_semantic', 'query': parsed_query}}
        if parsed_query else {'match_all': {}}
    )
    return {'bool': {'must': must, **filters}}


@app.post('/')
def handle_search():
    query = request.form.get('query', '')
    filters, parsed_query = extract_filters(query)
    from_ = request.form.get('from_', type=int, default=0)

    search_kwargs = dict(
        highlight={
            'pre_tags': [_HL_OPEN],
            'post_tags': [_HL_CLOSE],
            'fields': {
                'name': {'number_of_fragments': 0},
                'summary': {'number_of_fragments': 0},
            },
        },
        aggs={
            'category-agg': {
                'terms': {
                    'field': 'category.keyword',
                }
            },
            'tag-agg': {
                'terms': {
                    'field': 'tags.keyword',
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
        from_=from_,
    )

    try:
        if es.semantic_enabled:
            # Hybrid retrieval: BM25 lexical relevance and Elasticsearch's
            # built-in semantic retrieval, merged with Reciprocal Rank Fusion.
            # This is the actual product — a query like "why do requests
            # start failing under load" should surface a doc about connection
            # pool exhaustion even if it never says "requests" or "failing".
            results = es.search(
                retriever={
                    'rrf': {
                        'retrievers': [
                            {'standard': {'query': _lexical_query(parsed_query, filters)}},
                            {'standard': {'query': _semantic_query(parsed_query, filters)}},
                        ],
                        'rank_window_size': 50,
                        'rank_constant': 20,
                    }
                },
                **search_kwargs,
            )
        else:
            # This cluster has no semantic inference endpoint available (see
            # the fallback in Search.create_index) — lexical-only, same as
            # before.
            results = es.search(
                query=_lexical_query(parsed_query, filters),
                **search_kwargs,
            )
    except Exception:
        # Search is the entire point of this app, but a cluster hiccup
        # (unreachable, index missing/still building, a transient 5xx)
        # shouldn't take down the whole page with a raw 500 — every other
        # ES call in this app already degrades gracefully (see
        # get_document's related-articles guard and sitemap_xml), this
        # was the one gap.
        app.logger.exception('Search failed for query %r', query)
        flash(
            'Search is temporarily unavailable. This usually means the '
            'index is still being built, or the Elasticsearch cluster is '
            'unreachable — try again in a moment.',
            'danger',
        )
        return render_template(
            'index.html', results=None, query=query, from_=from_,
            total=0, aggs={}, search_failed=True,
            page_title=f'{SITE_NAME} – {SITE_TAGLINE}',
            meta_description=SITE_DESCRIPTION,
        )

    for hit in results['hits']['hits']:
        hit['display_name'] = highlighted_field(hit, 'name', hit['_source']['name'])
        hit['display_summary'] = highlighted_field(hit, 'summary', hit['_source']['summary'])

    aggs = {
        'Category': {
            bucket['key']: bucket['doc_count']
            for bucket in results['aggregations']['category-agg']['buckets']
        },
        'Tag': {
            bucket['key']: bucket['doc_count']
            for bucket in results['aggregations']['tag-agg']['buckets']
        },
        'Year': {
            bucket['key_as_string']: bucket['doc_count']
            for bucket in results['aggregations']['year-agg']['buckets']
            if bucket['doc_count'] > 0
        },
    }

    total = results['hits']['total']['value']
    return render_template(
        'index.html', results=results['hits']['hits'],
        query=query, from_=from_,
        total=total, aggs=aggs,
        page_title=f'{SITE_NAME} – {SITE_TAGLINE}',
        meta_description=(
            f'{total} document{"s" if total != 1 else ""} found for '
            f'"{query}" via hybrid lexical and semantic retrieval.'
            if query else
            'Browse every indexed document, faceted by category, tag, '
            'and year.'
        ),
    )


# retrieve the document by its id
@app.get('/document/<id>')
def get_document(id):
    try:
        document = es.retrieve_document(id)
    except NotFoundError:
        abort(404)
    title = document['_source']['name']
    summary = document['_source'].get('summary', SITE_DESCRIPTION)
    paragraphs = document['_source']['content'].split('\n')

    related = []
    try:
        related_results = es.more_like_this(id, size=3)
        related = related_results['hits']['hits']
    except Exception:
        # Related articles are a nice-to-have, not core to the page —
        # never let an Elasticsearch hiccup take down the whole article.
        app.logger.exception('Could not fetch related articles for %s', id)

    return render_template(
        'document.html', title=title, paragraphs=paragraphs, related=related,
        page_title=f'{title} – {SITE_NAME}',
        meta_description=summary,
    )


@app.errorhandler(404)
def not_found(error):
    return render_template(
        '404.html',
        page_title=f'Page Not Found – {SITE_NAME}',
        meta_description='The page you requested could not be found.',
    ), 404


@app.get('/robots.txt')
def robots_txt():
    lines = [
        'User-agent: *',
        'Allow: /',
        'Disallow: /admin',
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


# ---------------------------------------------------------------------------
# Admin: content management
#
# A single self-hosted admin account (see auth.py) manages posts through
# these routes. Every write goes to content.py's data.json-backed store
# first (the durable source of truth) and is then pushed into
# Elasticsearch immediately so search results stay current without
# requiring a manual `flask reindex`. If Elasticsearch is temporarily
# unreachable, the save to disk still succeeds and the admin is warned
# that a reindex will be needed once it's back, rather than losing the
# edit.
# ---------------------------------------------------------------------------

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))

    form = LoginForm()
    error = None
    if form.validate_on_submit():
        if verify_admin_credentials(form.username.data, form.password.data):
            login_user(AdminUser())
            next_url = request.args.get('next')
            return redirect(next_url or url_for('admin_dashboard'))
        error = 'Incorrect username or password.'

    return render_template(
        'admin/login.html', form=form, error=error,
        page_title=f'Admin Login – {SITE_NAME}',
        meta_description='Sign in to manage RetrievalKit’s indexed documents.',
    )


@app.post('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


@app.get('/admin')
@login_required
def admin_dashboard():
    posts = content.list_posts()
    return render_template(
        'admin/dashboard.html', posts=posts,
        page_title=f'Manage Posts – {SITE_NAME}',
        meta_description='Create, edit, and remove RetrievalKit’s indexed documents.',
    )


def _es_reindex_warning(post_id, action):
    app.logger.exception(
        'Could not sync post %s to Elasticsearch after %s', post_id, action
    )
    flash(
        f'Post saved, but the search index could not be updated ({action}). '
        'Run `flask reindex` once Elasticsearch is reachable so this '
        'change shows up in search.',
        'warning',
    )


@app.route('/admin/posts/new', methods=['GET', 'POST'])
@login_required
def admin_new_post():
    form = PostForm()
    if form.validate_on_submit():
        tags = [t.strip() for t in form.tags.data.split(',') if t.strip()]
        post = content.create_post(
            name=form.name.data, summary=form.summary.data,
            content=form.content.data, category=form.category.data,
            tags=tags,
        )
        try:
            es.index_document(post)
        except Exception:
            _es_reindex_warning(post['id'], 'create')
        else:
            flash(f'Published “{post["name"]}”.', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template(
        'admin/post_form.html', form=form, mode='new', post=None,
        page_title=f'New Post – {SITE_NAME}',
        meta_description='Add a new document to the RetrievalKit index.',
    )


@app.route('/admin/posts/<id>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_post(id):
    post = content.get_post(id)
    if post is None:
        abort(404)

    form = PostForm()
    if request.method == 'GET':
        form.name.data = post['name']
        form.summary.data = post['summary']
        form.content.data = post['content']
        form.category.data = post['category']
        form.tags.data = ', '.join(post.get('tags') or [])

    if form.validate_on_submit():
        tags = [t.strip() for t in form.tags.data.split(',') if t.strip()]
        updated = content.update_post(
            id, name=form.name.data, summary=form.summary.data,
            content=form.content.data, category=form.category.data,
            tags=tags,
        )
        try:
            es.index_document(updated)
        except Exception:
            _es_reindex_warning(id, 'edit')
        else:
            flash(f'Saved “{updated["name"]}”.', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template(
        'admin/post_form.html', form=form, mode='edit', post=post,
        page_title=f'Edit “{post["name"]}” – {SITE_NAME}',
        meta_description=f'Edit the RetrievalKit document “{post["name"]}”.',
    )


@app.post('/admin/posts/<id>/delete')
@login_required
def admin_delete_post(id):
    post = content.get_post(id)
    deleted = content.delete_post(id)
    if deleted:
        try:
            es.delete_document(id)
        except Exception:
            _es_reindex_warning(id, 'delete')
        else:
            name = post['name'] if post else id
            flash(f'Deleted “{name}”.', 'success')
    else:
        flash('That post no longer exists.', 'warning')
    return redirect(url_for('admin_dashboard'))


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

# expose method through flask and registers the func as a custom command
# can run 'flask reindex' in the terminal to regenerate the index
@app.cli.command()
def reindex():
    """Regenerate the Elasticsearch index from data.json."""
    response = es.reindex()
    items = response['items']
    took = response['took']
    print(f'Index with {len(items)} documents created in {took} milliseconds.')


@app.cli.command('hash-password')
@click.argument('password')
def hash_password(password):
    """Hash a password for ADMIN_PASSWORD_HASH in .env.

    Usage: flask hash-password 'your-chosen-password'
    Never commit the plaintext password or store it anywhere but your
    own terminal history/password manager — only the printed hash goes
    in .env.
    """
    print(generate_password_hash(password))


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

    filter_regex = r'tag:([^\s]+)\s*'
    m = re.search(filter_regex, query)
    if m:
        filters.append({
            'term': {
                'tags.keyword': {
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
