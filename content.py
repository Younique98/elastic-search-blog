"""File-backed content store for indexed documents.

data.json is the single source of truth for document content — the same
file the `flask reindex` CLI command bulk-loads into Elasticsearch. The
admin UI (see the /admin routes in app.py) reads and writes this file
directly so that a document created or edited through the browser is
immediately reflected both on disk and in the live Elasticsearch index,
without requiring a manual reindex. `flask reindex` remains available to
rebuild the index from scratch (e.g. after changing index settings/mappings).

Writes are atomic (write-to-temp-then-rename) so a crash mid-write can
never leave data.json truncated or corrupted, and are serialized with a
process-local lock so two concurrent admin requests can't interleave
writes and silently drop one of them.
"""
import json
import re
import threading
import uuid
from datetime import date
from pathlib import Path

DATA_FILE = Path(__file__).parent / 'data.json'
_lock = threading.Lock()


def slugify(text):
    slug = text.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = re.sub(r'-{2,}', '-', slug).strip('-')
    return slug or uuid.uuid4().hex[:8]


def _load():
    if not DATA_FILE.exists():
        return []
    with open(DATA_FILE, encoding='utf-8') as f:
        return json.load(f)


def _save(posts):
    tmp = DATA_FILE.with_suffix('.json.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(posts, f, indent=2, ensure_ascii=False)
        f.write('\n')
    tmp.replace(DATA_FILE)


def list_posts():
    """All posts, newest-updated first."""
    posts = _load()
    return sorted(posts, key=lambda p: p.get('updated_at', ''), reverse=True)


def get_post(post_id):
    for post in _load():
        if post.get('id') == post_id:
            return post
    return None


def _unique_slug(name, posts, exclude_id=None):
    base = slugify(name)
    existing = {p['id'] for p in posts if p.get('id') != exclude_id}
    slug = base
    n = 2
    while slug in existing:
        slug = f'{base}-{n}'
        n += 1
    return slug


def create_post(name, summary, content, category, tags):
    with _lock:
        posts = _load()
        today = date.today().isoformat()
        post = {
            'id': _unique_slug(name, posts),
            'name': name,
            'summary': summary,
            'content': content,
            'category': category,
            'tags': tags,
            'created_on': today,
            'updated_at': today,
            'url': None,
            'rolePermissions': ['member', 'nonmember', 'admin'],
        }
        posts.append(post)
        _save(posts)
        return post


def update_post(post_id, name, summary, content, category, tags):
    with _lock:
        posts = _load()
        for post in posts:
            if post.get('id') == post_id:
                post['name'] = name
                post['summary'] = summary
                post['content'] = content
                post['category'] = category
                post['tags'] = tags
                post['updated_at'] = date.today().isoformat()
                _save(posts)
                return post
        return None


def delete_post(post_id):
    with _lock:
        posts = _load()
        remaining = [p for p in posts if p.get('id') != post_id]
        if len(remaining) == len(posts):
            return False
        _save(remaining)
        return True
