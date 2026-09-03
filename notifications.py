"""Transactional email via Resend — same service already wired into
Erica's Windless Technologies repo for its contact form, reused here for
the one transactional email this app needs: confirming a Starter Kit
purchase and delivering the download link.

The delivery *mechanism* is built now, deliberately ahead of the kit's
actual contents existing yet. STARTER_KIT_FILE_URL (see .env.example) is
unset today, so every email currently sends the "we'll follow up within
24 hours" variant below — nothing here needs to change, in code or in
this module, once Erica finishes the kit and sets that one env var; the
next purchase's email will just include the real link.
"""
import logging
import os

import resend

logger = logging.getLogger(__name__)

STARTER_KIT_PRODUCT_NAME = 'Elasticsearch Search Starter Kit'

_DEFAULT_FROM = 'RetrievalKit <onboarding@resend.dev>'


def is_configured():
    return bool(os.environ.get('RESEND_API_KEY'))


def _from_address():
    return os.environ.get('RESEND_FROM_EMAIL', _DEFAULT_FROM)


def send_starter_kit_purchase_email(to_email):
    """Send the post-purchase confirmation/delivery email. Never raises —
    a Resend outage or missing API key must not turn a successful,
    already-recorded Stripe payment into a 500 on the webhook (Stripe
    would just retry the whole event). Returns True if an email was
    actually sent, False otherwise (not configured, or the send failed);
    callers should log the False case, not surface it to the buyer."""
    if not is_configured():
        return False

    download_url = os.environ.get('STARTER_KIT_FILE_URL')
    if download_url:
        delivery_html = (
            f'<p>Your download is ready: '
            f'<a href="{download_url}">{STARTER_KIT_PRODUCT_NAME}</a>.</p>'
        )
        delivery_text = f'Your download: {download_url}'
    else:
        # The kit's contents aren't finished yet — say so honestly
        # instead of sending a broken or empty link. As soon as
        # STARTER_KIT_FILE_URL is set, this branch stops being taken and
        # every subsequent purchase email includes the real link, with
        # no code change required.
        delivery_html = (
            '<p>Your purchase is confirmed — we\'ll send your download '
            'link within 24 hours.</p>'
        )
        delivery_text = (
            'Your purchase is confirmed — we\'ll send your download link '
            'within 24 hours.'
        )

    try:
        resend.api_key = os.environ['RESEND_API_KEY']
        resend.Emails.send({
            'from': _from_address(),
            'to': to_email,
            'subject': f'Your {STARTER_KIT_PRODUCT_NAME} purchase',
            'html': (
                f'<p>Thanks for buying the {STARTER_KIT_PRODUCT_NAME}.</p>'
                f'{delivery_html}'
            ),
            'text': (
                f'Thanks for buying the {STARTER_KIT_PRODUCT_NAME}.\n\n'
                f'{delivery_text}'
            ),
        })
        return True
    except Exception:
        logger.exception('Could not send Starter Kit purchase email to %s', to_email)
        return False
