"""Count multipart bytes before Starlette spools uploads to disk."""
from starlette.datastructures import Headers
from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse

from app.core.config import get_settings


class UploadBodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != "/api/videos/upload":
            return await self.app(scope, receive, send)
        limit = get_settings().max_upload_bytes + 1024 * 1024
        response = JSONResponse({"detail": "upload exceeds configured limit"}, status_code=413)
        try:
            declared = int(Headers(scope=scope).get("content-length", "0"))
        except ValueError:
            declared = 0
        if declared > limit:
            return await response(scope, receive, send)
        total = 0
        exceeded = False
        disconnected = False

        async def limited_receive():
            nonlocal total, exceeded, disconnected
            message = await receive()
            if message["type"] == "http.disconnect":
                disconnected = True
                raise MultiPartException("upload client disconnected")
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > limit:
                    exceeded = True
                    # Starlette closes all multipart temporary files on this exception.
                    raise MultiPartException("upload exceeds configured limit")
            return message

        async def limited_send(message):
            if not exceeded and not disconnected:
                await send(message)

        try:
            await self.app(scope, limited_receive, limited_send)
        except MultiPartException:
            if not exceeded and not disconnected:
                raise
        if exceeded:
            await response(scope, receive, send)
