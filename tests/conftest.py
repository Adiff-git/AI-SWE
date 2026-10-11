from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from ai_service.main import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    async def reject_backend_request(*args: object, **kwargs: object) -> httpx.Response:
        pytest.fail("Scaffold endpoints must not call the Backend")

    monkeypatch.setattr(httpx.AsyncClient, "request", reject_backend_request)
    with TestClient(app) as test_client:
        yield test_client
