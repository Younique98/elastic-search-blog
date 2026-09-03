"""Hosted Postgres storage for newsletter subscribers and Starter Kit
purchases.

This started as a local SQLite file. That was wrong for how this repo
actually deploys: `vercel.json` routes every request to a single Python
serverless function (`api/index.py`), and Vercel Python functions don't
guarantee a persistent local filesystem across separate invocations —
two requests can (and, on Vercel, typically do) land on different
execution environments. A SQLite file written during one request is not
reliably there for the next one, which means subscriber signups and
purchase records would be silently lost in production. That's not a
"revisit when it needs to scale" problem, it's a "probably already
broken as deployed" one.

Postgres — specifically Neon via Vercel's native Storage integration —
is the fix, and it's the same pattern already used across Erica's other
repos for exactly this kind of durable, low-volume relational data:
Vercel provisions it and injects `DATABASE_URL` into the function's
environment automatically, so there's no separate service to hand-wire.

This still isn't Elasticsearch, for the same reason as the original
design note here: `my_documents` is this app's *content* index, deleted
and rebuilt wholesale by `flask reindex`, and not where auth/commerce
records with real uniqueness requirements belong.

Every function here opens its own short-lived connection rather than
holding one at module scope — the right shape for a serverless function
that may run cold on every request, versus a long-lived server process
that would instead want a pool.
"""
import logging
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


def is_configured():
    return bool(os.environ.get('DATABASE_URL'))


@contextmanager
def _connect():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise RuntimeError(
            'DATABASE_URL is not set — newsletter signups and Starter Kit '
            'purchases cannot be read or written until it is configured '
            '(see .env.example). This does not affect the rest of the '
            'site, which has no other dependency on this module.'
        )
    # A short connect_timeout so a misconfigured/unreachable database
    # fails fast with a clear error instead of hanging a request for the
    # platform's full function timeout.
    conn = psycopg2.connect(database_url, connect_timeout=5)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables if they don't already exist. Safe to call on every
    cold start — CREATE TABLE IF NOT EXISTS is a no-op once they exist,
    the same idea as Search.__init__'s auto-heal for the Elasticsearch
    index. A no-op (with a logged warning) if DATABASE_URL isn't set
    yet, so a deployment missing it still boots — newsletter/Starter Kit
    routes will error when actually used, everything else works."""
    if not is_configured():
        logger.warning(
            'DATABASE_URL is not set; newsletter signups and Starter Kit '
            'purchases will fail until it is configured.'
        )
        return
    with _connect() as conn, conn.cursor() as cur:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS subscribers (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                subscribed_at TIMESTAMPTZ NOT NULL
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS purchases (
                id TEXT PRIMARY KEY,
                product TEXT NOT NULL,
                email TEXT NOT NULL,
                stripe_checkout_session_id TEXT NOT NULL UNIQUE,
                stripe_customer_id TEXT,
                amount_total_cents INTEGER,
                currency TEXT,
                purchased_at TIMESTAMPTZ NOT NULL,
                fulfilled BOOLEAN NOT NULL DEFAULT FALSE
            )
        ''')


# ---------------------------------------------------------------------------
# Newsletter subscribers
# ---------------------------------------------------------------------------

def add_subscriber(email):
    """Insert a new subscriber. Returns True if a new row was added,
    False if that email was already subscribed. ON CONFLICT DO NOTHING
    makes this atomic against a race between two concurrent submits of
    the same address — Postgres itself decides, not a
    check-then-insert in application code."""
    email = email.strip().lower()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            'INSERT INTO subscribers (id, email, subscribed_at) '
            'VALUES (%s, %s, %s) ON CONFLICT (email) DO NOTHING',
            (uuid.uuid4().hex, email, datetime.now(timezone.utc)),
        )
        return cur.rowcount > 0


def count_subscribers():
    with _connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM subscribers')
        return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Starter Kit purchases
# ---------------------------------------------------------------------------

def record_purchase(*, product, email, stripe_checkout_session_id,
                     stripe_customer_id, amount_total_cents, currency):
    """Record a completed one-time purchase from the Stripe webhook.
    Idempotent on stripe_checkout_session_id (via ON CONFLICT DO
    NOTHING): Stripe can and does retry webhook deliveries, so a
    duplicate checkout.session.completed for a session already recorded
    is a no-op rather than a second purchase row or a second delivery
    email. Returns True if a new row was inserted, False if this session
    was already recorded."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            'INSERT INTO purchases '
            '(id, product, email, stripe_checkout_session_id, '
            ' stripe_customer_id, amount_total_cents, currency, purchased_at) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s, %s) '
            'ON CONFLICT (stripe_checkout_session_id) DO NOTHING',
            (uuid.uuid4().hex, product, email.strip().lower(),
             stripe_checkout_session_id, stripe_customer_id,
             amount_total_cents, currency, datetime.now(timezone.utc)),
        )
        return cur.rowcount > 0


def list_unfulfilled_purchases():
    """Purchases Erica still needs to check on — kept even now that
    delivery emails are automated (see notifications.py), since a
    purchase with no STARTER_KIT_FILE_URL set yet still needs a human to
    follow up within the promised 24 hours."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                'SELECT * FROM purchases WHERE fulfilled = FALSE '
                'ORDER BY purchased_at ASC'
            )
            return [dict(row) for row in cur.fetchall()]
