import os
import tempfile
from pathlib import Path

# Must be set before app modules load, so tests can't touch the real database or real services.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp, 'test.db').as_posix()}"
os.environ["HIBP_API_KEY"] = "test-key"
os.environ["OLLAMA_URL"] = "http://127.0.0.1:1"
os.environ["LLM_AUTO_SETUP"] = "false"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as test_client:
        yield test_client
