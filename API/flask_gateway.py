import requests
from flask import Flask, Response, request

app = Flask(__name__)

TARGET_URL = "https://api.cohere.com/v2/chat"

HOP_BY_HOP_REQUEST_HEADERS = {
    "host", "content-length", "transfer-encoding", "connection",
    "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "upgrade",
}

HOP_BY_HOP_RESPONSE_HEADERS = {
    "transfer-encoding", "content-encoding", "content-length", "connection",
}


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response


@app.route("/health", methods=["GET"])
def health():
    """Liveness probe for hosting providers (Render/Railway/Fly/etc.)."""
    return {"status": "ok", "target": TARGET_URL}, 200


@app.route("/v2/chat", methods=["POST", "OPTIONS"])
def proxy_chat():
    if request.method == "OPTIONS":
        return "", 204

    body = request.get_data()

    # Forward headers (excluding hop-by-hop)
    headers = {}
    for key, value in request.headers.items():
        if key.lower() not in HOP_BY_HOP_REQUEST_HEADERS:
            headers[key] = value

    # Forward cookies
    cookies = dict(request.cookies)

    upstream = requests.post(
        TARGET_URL,
        headers=headers,
        cookies=cookies,
        data=body,
        stream=True,
        timeout=(10, 300),
    )

    # Filter response headers
    response_headers = {}
    for key, value in upstream.headers.items():
        if key.lower() not in HOP_BY_HOP_RESPONSE_HEADERS:
            response_headers[key] = value

    def sse_events():
        buffer = ""
        try:
            for chunk in upstream.iter_content(chunk_size=None, decode_unicode=True):
                if not chunk:
                    continue
                buffer += chunk
                while "\n\n" in buffer:
                    event, buffer = buffer.split("\n\n", 1)
                    if event.strip():
                        yield event + "\n\n"
            if buffer.strip():
                yield buffer + "\n\n"
        finally:
            upstream.close()

    response_headers["Cache-Control"] = "no-cache"
    response_headers["X-Accel-Buffering"] = "no"

    return Response(
        sse_events(),
        status=upstream.status_code,
        headers=response_headers,
        mimetype="text/event-stream",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
