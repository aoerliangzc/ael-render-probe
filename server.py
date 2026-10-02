"""Anonymous, fixed-target network probe. No account or token processing."""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TARGETS = {
    "oauth_endpoint": "https://auth.openai.com/oauth/token",
    "codex_models": "https://chatgpt.com/backend-api/codex/models",
    "api_models": "https://api.openai.com/v1/models",
}
LOCK = threading.Lock()
CACHE = {"time": 0.0, "result": None}
PAGE = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AEL 网络测试</title><style>body{font:16px system-ui;max-width:800px;
margin:40px auto;padding:20px}button{padding:12px 20px}pre{white-space:pre-wrap;
background:#f3f4f6;padding:20px}</style><h1>Render 出口连通性测试</h1>
<p>无需登录，不输入密码或令牌。测试仅发送固定地址的匿名 GET 请求。</p>
<button id="run">开始测试</button><pre id="out">等待测试</pre>
<p>401/405 通常表示端点可达；403 需结合错误类型判断。
网络可达不代表账号授权或模型调用成功。</p><script>
document.getElementById('run').onclick=async()=>{
const btn=document.getElementById('run'),out=document.getElementById('out');
btn.disabled=true;out.textContent='检测中，最多约 30 秒…';
try{const r=await fetch('/check',{cache:'no-store'});
out.textContent=JSON.stringify(await r.json(),null,2);}
catch(e){out.textContent='请求未完成，请检查部署日志或稍后重试。';}
finally{btn.disabled=false;}};</script></html>"""


def probe(url):
    started = time.monotonic()
    request = urllib.request.Request(url, headers={"User-Agent": "AEL-Network-Probe/1.0"})
    try:
        try:
            response = urllib.request.urlopen(request, timeout=8)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            body = response.read(32768).decode("utf-8", "replace")
            error_code = None
            try:
                error = json.loads(body).get("error")
                if isinstance(error, dict):
                    value = error.get("code")
                    if isinstance(value, str) and len(value) < 100:
                        error_code = value
            except (ValueError, AttributeError):
                pass
            return {
                "http_status": response.code,
                "tls_verified": True,
                "region_denial": "unsupported_country_region_territory" in body.lower(),
                "cloudflare_challenge": (
                    response.headers.get("cf-mitigated") == "challenge"
                    or "cf-chl-" in body or "just a moment" in body.lower()
                ),
                "error_code": error_code,
                "seconds": round(time.monotonic() - started, 2),
            }
    except Exception as exc:
        # Do not expose raw exception text, upstream bodies, headers, or credentials.
        return {"http_status": None, "error_type": type(exc).__name__,
                "seconds": round(time.monotonic() - started, 2)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, code, content_type, data):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            self.respond(200, "text/html; charset=utf-8", PAGE.encode())
        elif path == "/health":
            self.respond(200, "application/json", b'{"status":"ok"}')
        elif path == "/check":
            with LOCK:
                if CACHE["result"] is None or time.monotonic() - CACHE["time"] > 60:
                    CACHE["result"] = {name: probe(url) for name, url in TARGETS.items()}
                    CACHE["time"] = time.monotonic()
                data = json.dumps(CACHE["result"], ensure_ascii=False).encode()
            self.respond(200, "application/json; charset=utf-8", data)
        else:
            self.respond(404, "application/json", b'{"error":"not_found"}')


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"AEL network probe listening on 0.0.0.0:{port}", flush=True)
    server.serve_forever()
