"""Shared Backend HTTP client, without assuming any Backend endpoint paths."""

import httpx

from ai_service.core.config import Settings


class BackendResponseTooLarge(ValueError):
    """A Backend response exceeds the read-only integration envelope."""


async def read_backend_response(response: httpx.Response) -> bytes:
    """Bound decoded bytes, including chunked/compressed responses."""
    body = bytearray()
    async for chunk in response.aiter_bytes():
        body.extend(chunk)
        if len(body) > 65_536:
            raise BackendResponseTooLarge
    return bytes(body)


async def _raise_for_status(response: httpx.Response) -> None:
    """Raise HTTPStatusError on unsuccessful responses, including redirects."""
    if not response.is_success:
        # HTTPX closes a streamed response when a hook raises. Preserve a bounded
        # error body on the exception so callers can distinguish a product 404
        # from a proxy/missing-route 404 without a second request.
        headers = httpx.Headers(response.headers)
        # read_backend_response already decodes compression. A reconstructed
        # response must not decode it again or retain the compressed byte length.
        headers.pop("content-encoding", None)
        headers.pop("content-length", None)
        error = httpx.Response(
            response.status_code,
            headers=headers,
            content=await read_backend_response(response),
            request=response.request,
        )
        error.raise_for_status()


def create_backend_client(
    settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    """Create a pool owned and closed by the application lifespan.

    Construction makes no network request. Integrations reuse app.state.backend_client
    with fixed relative paths. HTTPX status/transport exceptions remain explicit;
    feature adapters map them to safe domain outcomes. Transport injection is for
    deterministic HTTP tests, never a model-controlled argument.
    """
    return httpx.AsyncClient(
        base_url=str(settings.backend_api_base_url),
        timeout=httpx.Timeout(settings.backend_api_timeout),
        event_hooks={"response": [_raise_for_status]},
        follow_redirects=False,
        transport=transport,
    )
