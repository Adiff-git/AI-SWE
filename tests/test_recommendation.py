import pytest
from fastapi.testclient import TestClient


def test_recommendations_placeholder(client: TestClient) -> None:
    response = client.post("/api/v1/recommendations", json={"user_id": "123", "limit": 10})
    assert response.status_code == 200
    assert response.json() == {"product_ids": [], "status": "not_implemented"}


@pytest.mark.parametrize(
    "payload",
    [{}, {"user_id": " "}, {"user_id": "123", "limit": 0}, {"user_id": "123", "limit": 101}],
)
def test_recommendation_validation(client: TestClient, payload: dict[str, object]) -> None:
    assert client.post("/api/v1/recommendations", json=payload).status_code == 422
