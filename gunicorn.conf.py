"""Gunicorn settings for running project-tracker in production.

Gunicorn executes this file on start (``gunicorn -c gunicorn.conf.py``). The bind
address comes from ``PROJECT_TRACKER_HOST`` and ``PROJECT_TRACKER_PORT``, which the
systemd unit loads from its environment file; see docs/deployment.md. Every setting
used here is described at https://gunicorn.org/reference/settings/.
"""

import os

DEFAULT_HOST = "127.0.0.1"
# Chosen to stay clear of the other services on the home server.
DEFAULT_PORT = 8002


def _port_from_env() -> int:
    """Return PROJECT_TRACKER_PORT as an int, or DEFAULT_PORT if it is unset."""
    raw = os.environ.get("PROJECT_TRACKER_PORT", "").strip()
    if not raw:
        return DEFAULT_PORT
    if not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise ValueError(
            f"PROJECT_TRACKER_PORT must be a number from 1 to 65535, got {raw!r}"
        )
    return int(raw)


_host = os.environ.get("PROJECT_TRACKER_HOST", "").strip() or DEFAULT_HOST

# The app factory; Gunicorn calls it once per worker.
wsgi_app = "project_tracker:create_app()"
bind = [f"{_host}:{_port_from_env()}"]
# One user and SQLite: two sync workers are plenty, and one can serve while the
# other restarts.
workers = 2
# "-" sends both logs to stdout/stderr, which systemd stores in the journal.
accesslog = "-"
errorlog = "-"
# The runtime control socket (gunicornc) is not used; disabling it stops
# Gunicorn trying to create ~/.gunicorn/ in a sandbox where it cannot write.
control_socket_disable = True
