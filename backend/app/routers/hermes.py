from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.auth import require_session

router = APIRouter()

_HOP_BY_HOP_HEADERS = {
    "host",
    "content-length",
    "connection",
    "transfer-encoding",
}


@router.api_route(
    "/hermes/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def hermes_proxy(
    path: str,
    request: Request,
    _session: Annotated[dict[str, str], Depends(require_session)],
) -> Response:
    if request.headers.get("upgrade", "").lower() == "websocket":
        raise HTTPException(
            status_code=501,
            detail="hermes websockets not proxied; native views coming in Phase 2",
        )

    settings = request.app.state.settings
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS
    }
    url = httpx.URL(f"{settings.hermes_admin_url.rstrip('/')}/{path}").copy_with(
        query=request.url.query.encode("utf-8")
    )
    async with httpx.AsyncClient(timeout=None) as client:
        upstream = await client.request(
            request.method,
            url,
            content=await request.body(),
            headers=headers,
        )
    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )
