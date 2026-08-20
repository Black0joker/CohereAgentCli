# Hosting the Cohere SSE proxy (`flask_gateway.py`)

This gateway forwards `POST /v2/chat` to `https://api.cohere.com/v2/chat` and
relays the SSE stream back to the caller. Point the agent at it by setting an
entry's `apiUrl` in `tokens.json` to the hosted base URL (the Cohere SDK then
calls `{apiUrl}/v2/chat`).

The Flask `app` object is exposed at module level, so it is ready for any
WSGI host. It also exposes `GET /health` for provider liveness probes.

## Run locally (quick test)
```bash
pip install -r API/requirements.txt
python API/flask_gateway.py            # serves on 0.0.0.0:8000
```
Then set `"apiUrl": "http://127.0.0.1:8000"` in `tokens.json`.

## PythonAnywhere
1. Upload `flask_gateway.py` to your home dir.
2. Web tab -> Add a new web app -> Manual configuration -> Python 3.x.
3. Edit the WSGI file:
   ```python
   import sys
   sys.path.insert(0, "/home/<user>")
   from flask_gateway import app as application
   ```
4. Set `"apiUrl": "https://<user>.pythonanywhere.com"` in `tokens.json`.

## Render / Railway / Fly.io
- Build: `pip install -r API/requirements.txt`
- Start: `gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 8 --timeout 300 "flask_gateway:app"`
- Health check path: `/health`
- Set `"apiUrl": "https://<your-service-url>"` in `tokens.json`.

## Notes
- The gateway streams SSE; do not put a buffering proxy in front of it
  (it already sets `X-Accel-Buffering: no` for nginx).
- Forwarded headers exclude hop-by-hop headers; cookies are passed through.
- CORS is wide open (`*`) so browser-based clients can call it.
