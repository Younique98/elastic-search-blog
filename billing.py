"""Stripe billing for the Elasticsearch Search Starter Kit — a one-time
digital-product purchase, not a subscription.

Plain Flask view functions in app.py call into this module (see the
"Starter Kit purchase" section of app.py) — there is no Next.js API-route
layer here, this is a server-rendered Flask app, so /stripe/checkout and
/stripe/webhook are just two more @app.route endpoints, the same shape
/admin's routes already use.

Same underlying Stripe pattern as the Next.js siblings this comes from
(BoardKit, AgentRadar, Milspouse Elevate) — a Stripe Checkout Session to
collect payment and a signature-verified webhook as the single source of
truth for "did this actually get paid" — adapted from their monthly
subscription shape to this product's one-time `mode: "payment"` price,
since the Starter Kit is bought once, not subscribed to. There's
therefore no Billing Portal route here either: that's for managing an
ongoing subscription (cancel, update card, see invoices), which doesn't
apply to a single purchase.
"""
import os

import stripe

# Named once, rather than inlined, so the price appears in exactly one
# place in code. This is what the landing page displays and what the
# Checkout Session's line item describes — the actual charge amount
# still lives on the Stripe Price object identified by STRIPE_PRICE_ID,
# so if that price ever changes in the Stripe Dashboard, update this to
# match.
STARTER_KIT_PRICE_USD = 49
STARTER_KIT_PRICE_LABEL = f'${STARTER_KIT_PRICE_USD}'
STARTER_KIT_PRODUCT_ID = 'elasticsearch-search-starter-kit'


def _configure():
    """Point the stripe SDK at the configured secret key. Called lazily,
    inside each route, rather than at import time — importing billing.py
    (e.g. from app.py at startup) must not require Stripe credentials to
    already be set, the same "degrade, don't crash on boot" posture the
    rest of this app already takes with Elasticsearch."""
    stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')


def is_configured():
    return bool(os.environ.get('STRIPE_SECRET_KEY') and os.environ.get('STRIPE_PRICE_ID'))


def create_checkout_session(success_url, cancel_url):
    """Start a one-time-payment Stripe Checkout session for the Starter
    Kit. No customer/account required up front — Stripe Checkout collects
    the buyer's email itself, and that's all fulfillment currently needs
    (see store.record_purchase, called from the webhook)."""
    _configure()
    price_id = os.environ.get('STRIPE_PRICE_ID')
    if not price_id:
        raise RuntimeError('STRIPE_PRICE_ID is not set')

    session = stripe.checkout.Session.create(
        mode='payment',
        line_items=[{'price': price_id, 'quantity': 1}],
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return session.url


def verify_webhook(payload, signature_header):
    """Verify a webhook request actually came from Stripe (HMAC-signed
    with STRIPE_WEBHOOK_SECRET) and return the parsed event. Raises
    stripe.error.SignatureVerificationError / ValueError on a bad or
    forged payload — callers must not act on the request body until this
    has returned successfully."""
    _configure()
    webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
    if not webhook_secret:
        # Treated the same as a bad signature by the caller (app.py's
        # stripe_webhook catches ValueError) — a webhook arriving before
        # STRIPE_WEBHOOK_SECRET is configured should 400, not 500.
        raise ValueError('STRIPE_WEBHOOK_SECRET is not set')
    return stripe.Webhook.construct_event(payload, signature_header, webhook_secret)
