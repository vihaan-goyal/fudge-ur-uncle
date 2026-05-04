"""Shared pytest fixtures.

The big trick here: backend modules read DB_PATH from FUU_DB_PATH at import
time. We set the env var BEFORE importing anything else so the whole app
boots against a tmp DB instead of the real one.
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

# `backend/` needs to be on sys.path so `import server`, `import db` etc.
# resolve the way they do in production. The test harness runs from anywhere.
_BACKEND_DIR = Path(__file__).parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


@pytest.fixture(scope="session")
def _tmp_db_path():
    """Session-scoped tmp DB. Module-level so the app sees it from first import."""
    fd, path = tempfile.mkstemp(suffix=".sqlite", prefix="fuu-test-")
    os.close(fd)
    os.environ["FUU_DB_PATH"] = path
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture(scope="session")
def app(_tmp_db_path):
    """FastAPI app, importing only after FUU_DB_PATH is set."""
    # Import inside the fixture so the env var lands before db.py / alerts_router.py
    # capture their module-level paths.
    from server import app as fastapi_app
    from db import init_db
    init_db()
    return fastapi_app


@pytest.fixture()
def client(app):
    """TestClient bound to the app. Function-scoped so each test gets a clean instance."""
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c
