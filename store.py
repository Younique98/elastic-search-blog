"""SQLite-backed storage for the two small, write-light record types this
monetization work needs: newsletter subscribers and Starter Kit
purchases. Neither belongs in Elasticsearch:

- Elasticsearch (`my_documents`, via search.py/content.py) is this app's
  *content* index — it's rebuilt wholesale by `flask reindex` (delete
  the index, reload every document from data.json) and is tuned for
  full-text relevance ranking, not for "does this email already exist"
  or "record this purchase exactly once". Putting subscriber emails or
  purchase records in that same index would mean a routine content
  reindex could wipe them, and email-uniqueness would depend on
  eventually-consistent search-side dedup instead of a real constraint.
- A dedicated Postgres server is the shape this pattern uses in its
  Next.js/Prisma siblings, but standing up and operating a second
  service just to hold a couple of low-volume tables contradicts this
  repo's own "no unnecessary services" stance (the whole product exists
  so teams *don't* have to add a second database next to Elasticsearch).

SQLite is the actual fit: no server to run, ships in the standard
library, and gives real UNIQUE constraints/transactions for the two
things that need them — one row per subscriber email, and a purchase
row written exactly once per completed Stripe Checkout session. The
file lives outside version control (see .gitignore), created
automatically by init_db() the same way Search.__init__ auto-heals a
missing Elasticsearch index.
"""
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_FILE = Path(os.environ.get('STORE_DB_PATH') or (Path(__file__).parent / 'store.db'))


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Create tables if they don't already exist. Safe to call on every
    app startup."""
    with _connect() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS subscribers (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                subscribed_at TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS purchases (
                id TEXT PRIMARY KEY,
                product TEXT NOT NULL,
                email TEXT NOT NULL,
                stripe_checkout_session_id TEXT NOT NULL UNIQUE,
                stripe_customer_id TEXT,
                amount_total_cents INTEGER,
                currency TEXT,
                purchased_at TEXT NOT NULL,
                fulfilled INTEGER NOT NULL DEFAULT 0
            )
        ''')


# ---------------------------------------------------------------------------
# Newsletter subscribers
# ---------------------------------------------------------------------------

def add_subscriber(email):
    """Insert a new subscriber. Returns True if a new row was added,
    False if that email was already subscribed (checked via the UNIQUE
    constraint, so two concurrent submits of the same address can't
    double-insert) — both are a "success" from the visitor's point of
    view, so the caller should show the same confirmation either way."""
    email = email.strip().lower()
    try:
        with _connect() as conn:
            conn.execute(
                'INSERT INTO subscribers (id, email, subscribed_at) VALUES (?, ?, ?)',
                (uuid.uuid4().hex, email, datetime.now(timezone.utc).isoformat()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def count_subscribers():
    with _connect() as conn:
        row = conn.execute('SELECT COUNT(*) AS n FROM subscribers').fetchone()
    return row['n']


# ---------------------------------------------------------------------------
# Starter Kit purchases
# ---------------------------------------------------------------------------

def record_purchase(*, product, email, stripe_checkout_session_id,
                     stripe_customer_id, amount_total_cents, currency):
    """Record a completed one-time purchase from the Stripe webhook.
    Idempotent on stripe_checkout_session_id: Stripe can and does retry
    webhook deliveries, so a duplicate checkout.session.completed for a
    session already recorded is a silent no-op rather than a second
    purchase row. Returns True if a new row was inserted, False if this
    session was already recorded."""
    try:
        with _connect() as conn:
            conn.execute(
                'INSERT INTO purchases '
                '(id, product, email, stripe_checkout_session_id, '
                ' stripe_customer_id, amount_total_cents, currency, purchased_at) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (uuid.uuid4().hex, product, email.strip().lower(),
                 stripe_checkout_session_id, stripe_customer_id,
                 amount_total_cents, currency,
                 datetime.now(timezone.utc).isoformat()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def list_unfulfilled_purchases():
    """Purchases Erica still needs to manually email the download link
    for — the fulfillment mechanism described in the PR: no automated
    delivery yet, just a durable, queryable record of who paid."""
    with _connect() as conn:
        rows = conn.execute(
            'SELECT * FROM purchases WHERE fulfilled = 0 ORDER BY purchased_at ASC'
        ).fetchall()
    return [dict(r) for r in rows]
