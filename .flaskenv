FLASK_RUN_PORT=5001

# FLASK_DEBUG is intentionally NOT set here. Enabling it turns on the
# Werkzeug interactive debugger, which allows arbitrary remote code
# execution if this app is ever reachable from outside localhost.
# For local development only, export it in your own shell/.env instead
# of committing it: FLASK_DEBUG=1 flask run
