"""Single-admin authentication for the /admin content-management UI.

This is a self-hosted, single-operator product (one site owner running
their own search-and-content layer), not a multi-tenant SaaS, so there is
one admin account, configured entirely through the environment — never
hardcoded, never stored in data.json alongside post content. See
.env.example for ADMIN_USERNAME / ADMIN_PASSWORD_HASH, and run
`flask hash-password` to generate the hash from a plaintext password
without ever typing the plaintext into a config file.

Built on Flask-Login (rather than a NextAuth-style provider, which is a
Next.js/JS-framework pattern) because this is a server-rendered Flask
app — Flask-Login's session-cookie + @login_required model is the
idiomatic fit here.
"""
import os

from flask_login import LoginManager, UserMixin
from werkzeug.security import check_password_hash

login_manager = LoginManager()
login_manager.login_view = 'admin_login'
login_manager.login_message = 'Please log in to access the admin area.'
login_manager.login_message_category = 'info'

ADMIN_ID = 'admin'


class AdminUser(UserMixin):
    """The single admin account. Flask-Login requires an object with an
    id, not a bare username, so this small wrapper is that object."""
    id = ADMIN_ID


@login_manager.user_loader
def load_user(user_id):
    if user_id == ADMIN_ID:
        return AdminUser()
    return None


def verify_admin_credentials(username, password):
    """Check a submitted username/password against the env-configured
    admin account. Returns False (never raises) for any misconfiguration
    so a missing/blank ADMIN_PASSWORD_HASH fails closed instead of
    granting access."""
    expected_username = os.environ.get('ADMIN_USERNAME')
    expected_hash = os.environ.get('ADMIN_PASSWORD_HASH')
    if not expected_username or not expected_hash:
        return False
    if username != expected_username:
        return False
    try:
        return check_password_hash(expected_hash, password)
    except (TypeError, ValueError):
        return False
