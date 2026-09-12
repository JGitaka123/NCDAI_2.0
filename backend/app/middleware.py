"""Bound untrusted request bytes before JSON parsing and secure every API response."""
import asyncio
import logging
import re
from starlette.responses import JSONResponse


class SecurityEnvelope:
    def __init__(self, app, *, secure: bool = False, max_body_bytes: int = 1_048_576):
        self.app = app
        self.secure = secure
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        response_started = False

        async def secured_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = list(message.get("headers", []))
                headers.extend([(b"cache-control", b"no-store"),
                                (b"x-content-type-options", b"nosniff"),
                                (b"referrer-policy", b"no-referrer"),
                                (b"x-frame-options", b"DENY"),
                                (b"permissions-policy", b"camera=(), microphone=(), geolocation=()")])
                if self.secure:
                    headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                message = {**message, "headers": headers}
            await send(message)

        async def reject(code, detail):
            await JSONResponse({"detail": detail}, status_code=code)(scope, receive, secured_send)

        async def invoke(next_receive):
            try:
                await self.app(scope, next_receive, secured_send)
            except Exception as exc:
                if response_started:
                    raise
                # Exception messages/tracebacks may contain SQL bind values or
                # clinical input. Emit only a classification, never its text.
                logging.getLogger("ncdai.security").error("Unhandled API error (%s); details withheld", type(exc).__name__)
                await reject(500, "Unexpected server error; retry safely or contact support")

        headers = scope.get("headers", [])
        hosts = [v.decode("latin1") for k, v in headers if k.lower() == b"host"]
        # A Host value must not change the parsed request path or authority.
        if len(hosts) != 1 or not re.fullmatch(r"(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:]+\])(?::[0-9]{1,5})?", hosts[0]):
            return await reject(400, "Invalid Host header")
        lengths = [v for k, v in headers if k.lower() == b"content-length"]
        if len(lengths) > 1 or (lengths and not re.fullmatch(rb"[0-9]{1,12}", lengths[0])):
            return await reject(400, "Invalid Content-Length header")
        if lengths and int(lengths[0]) > self.max_body_bytes:
            return await reject(413, "Request body exceeds the supported limit")
        if scope["method"] in {"POST", "PUT", "PATCH", "DELETE"}:
            chunks = []
            size = 0
            try:
                async with asyncio.timeout(15):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        size += len(chunk)
                        if size > self.max_body_bytes:
                            return await reject(413, "Request body exceeds the supported limit")
                        chunks.append(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                return await reject(408, "Request body delivery timed out")
            body = b"".join(chunks)
            delivered = False

            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            return await invoke(bounded_receive)
        return await invoke(receive)
