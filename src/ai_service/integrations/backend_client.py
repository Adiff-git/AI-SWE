"""Shared Backend HTTP client, without assuming any Backend endpoint paths."""

import httpx

from ai_service.core.config import Settings


async def _raise_for_status(response: httpx.Response) -> None:
    """Raise HTTPStatusError on unsuccessful responses, including redirects."""
    response.raise_for_status()


def create_backend_client(settings: Settings) -> httpx.AsyncClient:
    """Create a pool owned and closed by the application lifespan.

    Construction makes no network request. Future integrations should reuse
    app.state.backend_client with team-agreed relative paths. HTTPStatusError,
    TimeoutException and RequestError remain explicit HTTPX exceptions; callers
    must map them to their agreed API error contract when integration is added.
    """
    return httpx.AsyncClient(
        base_url=str(settings.backend_api_base_url),
        timeout=httpx.Timeout(settings.backend_api_timeout),
        event_hooks={"response": [_raise_for_status]},
        follow_redirects=False,
    )
