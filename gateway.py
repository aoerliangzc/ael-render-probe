"""Authenticated fixed-target TCP bridge; upstream TLS remains end to end."""
import asyncio
import hmac
import os
import time

from aiohttp import WSMsgType, web
import server

DESTINATIONS = {
    "auth": ("auth.openai.com", 443),
    "codex": ("chatgpt.com", 443),
    "api": ("api.openai.com", 443),
}


async def home(request):
    return web.Response(text=server.PAGE, content_type="text/html", headers={"Cache-Control": "no-store"})


async def health(request):
    return web.json_response({"status": "ok", "bridge_enabled": len(request.app["secret"]) >= 32})


def cached_probe():
    with server.LOCK:
        if server.CACHE["result"] is None or time.monotonic() - server.CACHE["time"] > 60:
            server.CACHE["result"] = {name: server.probe(url) for name, url in server.TARGETS.items()}
            server.CACHE["time"] = time.monotonic()
        return server.CACHE["result"]


async def check(request):
    result = await asyncio.to_thread(cached_probe)
    return web.json_response(result, headers={"Cache-Control": "no-store"})


async def tunnel(request):
    secret = request.app["secret"]
    if len(secret) < 32:
        raise web.HTTPServiceUnavailable(text="bridge_not_configured")
    if not hmac.compare_digest(request.headers.get("Authorization", ""), "Bearer " + secret):
        raise web.HTTPUnauthorized(text="authentication_required")
    target = DESTINATIONS.get(request.match_info["target"])
    if target is None:
        raise web.HTTPForbidden(text="target_not_allowed")
    if request.app["active"] >= 3:
        raise web.HTTPTooManyRequests(text="connection_limit")
    request.app["active"] += 1
    writer = None
    ws = None
    tasks = []
    try:
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(*target), 10)
        except (OSError, asyncio.TimeoutError):
            raise web.HTTPBadGateway(text="upstream_unreachable") from None
        ws = web.WebSocketResponse(max_msg_size=1024*1024, heartbeat=None)
        await ws.prepare(request)
        await ws.send_json({"connected": True})

        async def upstream_to_ws():
            while True:
                chunk = await asyncio.wait_for(reader.read(32768), 900)
                if not chunk:
                    return
                await ws.send_bytes(chunk)

        async def ws_to_upstream():
            async for message in ws:
                if message.type == WSMsgType.BINARY:
                    writer.write(message.data)
                    await writer.drain()
                elif message.type not in (WSMsgType.PING, WSMsgType.PONG):
                    return

        tasks = [asyncio.create_task(upstream_to_ws()), asyncio.create_task(ws_to_upstream())]
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        return ws
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if writer:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
        if ws:
            await ws.close()
        request.app["active"] -= 1


def make_app(secret=None):
    app = web.Application(client_max_size=1024*1024)
    app["secret"] = secret if secret is not None else os.environ.get("AEL_TUNNEL_SECRET", "")
    app["active"] = 0
    app.add_routes([web.get("/", home), web.get("/health", health),
                    web.get("/check", check), web.get("/tunnel/{target}", tunnel)])
    return app


if __name__ == "__main__":
    web.run_app(make_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "10000")), access_log=None)
