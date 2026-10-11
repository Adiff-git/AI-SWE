import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("session_id", [None, "session-123"])
def test_chat_placeholder(client: TestClient, session_id: str | None) -> None:
    response = client.post(
        "/api/v1/chat",
        json={"message": "Recommend a laptop for programming", "session_id": session_id},
    )
    assert response.status_code == 200
    assert response.json() == {
        "status": "not_implemented",
        "message": "AI shopping assistance is not implemented yet.",
        "session_id": session_id,
    }


@pytest.mark.parametrize("payload", [{}, {"message": " "}, {"message": "x" * 4001}])
def test_chat_validation(client: TestClient, payload: dict[str, object]) -> None:
    assert client.post("/api/v1/chat", json=payload).status_code == 422
