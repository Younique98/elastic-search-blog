"""Vercel entrypoint.

Vercel's Functions mechanism requires a declared function file to live
inside api/ — a root-level app.py doesn't qualify even when explicitly
named in vercel.json's `functions` block (confirmed by the deployment
error: "doesn't match any Serverless Functions inside the `api`
directory"). Rather than move the whole application under api/ (which
would break app.py's sibling imports — auth.py, content.py, search.py,
forms.py — and its templates/static lookups, both of which resolve
relative to app.py's own file location), this just re-exports the real
Flask app object so Vercel has a valid entrypoint inside api/ while
everything else about the app's layout is untouched.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import app  # noqa: E402
