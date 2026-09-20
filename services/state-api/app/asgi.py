"""The state-api process as deployed: every route in ``app.main``, behind the Host check, the access guard and the body limit.

``services/state-api/Dockerfile`` runs ``uvicorn app.asgi:app``. Each wrapper is
its own small module and covers routes registered anywhere, outermost first:

1. ``HostGuard`` (``app/host_guard.py``): the Host names the API answers to;
2. ``AccessGuard`` (``app/access_guard.py``): who may make changes;
3. ``BodyLimit`` (``app/body_limit.py``): how large a change's body may be.

Tests that import ``app.main.app`` exercise the routes without them;
``tests/test_access_guard.py`` pins the Dockerfile to this entry point.
"""

from app.access_guard import AccessGuard
from app.body_limit import BodyLimit
from app.host_guard import HostGuard
from app.main import app as routes

app = HostGuard(AccessGuard(BodyLimit(routes)))
