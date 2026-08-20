> ⚠️ **Cohere models are useless and they are very stupid in reasoning and tools calling.**

---

# CohereAgentCli

A small autonomous coding agent CLI powered by **Cohere Command** (`chat_stream`
+ native tool use). It reads, writes, searches, and verifies files in your
workspace, runs shell commands, retries on rate limits, streams its reasoning,
and reports token consumption - all from your terminal.

Run it with: `python agent.py`

## Features

- **Streaming chat** - answers stream to the console as they arrive, with a
  styled UI (colors, per-step tool display, thinking preview).
- **Tool use** - 15 tools: filesystem access (`read_file`, `write_file`,
  `replace`, `list_directory`, `glob`, `grep_search`), command execution
  (`run_shell_command` foreground/background, `kill_process`,
  `list_background_processes`, `read_background_output`), Python execution
  (`code_interpreter`), web lookup (`google_web_search`, `web_fetch`),
  planning mode, and user interaction.
- **OS-aware system prompt** - automatically instructs the model to use
  PowerShell commands on Windows and bash/POSIX commands on Linux/macOS.
- **Model thinking** - reasoning (`thinking`) stream events are displayed
  separately from the final answer.
- **Rate-limit handling** - on HTTP 429 the agent waits out the full
  one-minute trial-key window (or honors `Retry-After`) and retries; other
  transient errors (5xx, network) use capped exponential backoff.
- **Credential rotation** - credentials live in `tokens.json` as
  `[{token, apiUrl}]` entries; the agent rotates to the next entry after
  every 18 API calls, and immediately when a call fails (e.g. a 429 rate
  limit or a request exceeding the 5-second client timeout), retrying with
  fresh credentials before falling back to waiting.
- **Retry discipline** - identical retries of failed tool calls are flagged
  with the original error plus a directive to change strategy.
- **Small-talk routing** - greetings and chit-chat skip tool schemas entirely.
- **File-only logging** - every turn, tool call, error, and traceback is
  written to `logs/agent.log` (rotating 1 MB x 3); the console stays clean.
- **Token usage** - each turn ends with a summary parsed from the
  `message-end` event (input / output / reasoning / cached tokens).

## Requirements

- Python 3.9+
- [cohere](https://pypi.org/project/cohere/) SDK v5+

```bash
pip install cohere
```

## Setup

### 1. Get your Cohere API key

You need a Cohere account first:

1. Register a free account at
   <https://dashboard.cohere.com/welcome/register>.
2. After signing in, open the **API Keys** page in the dashboard
   (<https://dashboard.cohere.com/api-keys>) and create a **Trial key**.
3. Copy the generated key (it starts with `cohere_`).

Trial keys are free and limited to 20 API calls/minute; the agent handles
the resulting 429 responses automatically by waiting for the next window.

### 2. Configure the project

1. Copy the example credentials file:

   ```bash
   cp tokens_example.json tokens.json
   ```

2. Put one or more API keys in `tokens.json` (never commit this file - it
   is git-ignored). Each entry is a `{token, apiUrl}` pair; leave `apiUrl`
   empty to use the official Cohere endpoint:

   ```json
   [
     {"token": "cohere_xxxxxxxxxxxxxxxxxxxxxxxx", "apiUrl": ""},
     {"token": "cohere_yyyyyyyyyyyyyyyyyyyyyyyy", "apiUrl": "https://your-proxy.example.com/"}
   ]
   ```

   The agent rotates to the next entry after every 18 API requests.

## Usage

```bash
python agent.py
```

Then type your request. Example session:

```
you ❯ Use list_directory on "." and reply with the entry count.

  | thinking: The user wants me to list the directory and count...

  ◆ step 1
    ⚙ list_directory {"path": "."}
    ✓ 21 entries (0.00s)

agent ❯ 21

  ◈ tokens: 5,325 in | 371 out | 324 reasoning | 2,656 cached
```

Type `exit` or `quit` to leave.

### Chat sessions

Conversations are persisted automatically (one JSON file per chat under `chats/`,
git-ignored) and survive restarts. Slash commands manage them:

| Command | Effect |
|---|---|
| `/new [name]` | Save the current chat (if it has history) and start a fresh one. Without a name, the chat is auto-named from its first message at first save. |
| `/chats` | List saved chats, most recent first, with position numbers. The active chat is marked with `*`. |
| `/switch <ref>` | Switch to a saved chat. `<ref>` is a position number from `/chats`, a full name, or a unique name prefix. The current chat is saved first. |
| `/remove <ref>` | Delete a saved chat (same `<ref>` rules). Removing the active chat starts a fresh one. |
| `/help` | Show these commands. |

Chat history (including tool calls/results) is stored verbatim except the system prompt,
which is re-injected on load.

## Building a standalone exe

```bash
python -m PyInstaller agent.spec --noconfirm
```

Produces `dist/agent.exe` (one-file console app). Put `tokens.json` NEXT TO the
exe - credentials are loaded from the exe's own directory regardless of the
working directory. The agent's workspace is still the directory it is launched
from, so `cd` where you want it to work and run the exe from there.

## Project structure

Each file has a single responsibility:

| File | Responsibility |
|---|---|
| `agent.py` | CLI entry point: bootstrap + interactive REPL + chat commands |
| `chat_store.py` | Chat session persistence: create / list / load / save / remove (`chats/*.json`) |
| `agent.spec` | PyInstaller build spec for the standalone `dist/agent.exe` |
| `config.py` | Configuration constants (model, tokens file, rotation budget, client timeout) |
| `token_manager.py` | `tokens.json` loading + credential rotation every 18 requests |
| `system_prompt.py` | OS-aware system prompt (Windows / Linux / macOS) |
| `tool_schemas.py` | The 15 Cohere function-calling tool schemas |
| `tool_engine.py` | Adapter for `module.py` (logger injection, workspace pinning) |
| `module.py` | Tool execution engine backing every tool |
| `tool_dispatch.py` | Tool execution + retry discipline |
| `small_talk.py` | Conversational-input detection |
| `streaming.py` | `chat_stream` consumption, retries, thinking, usage |
| `agent_loop.py` | The multi-step tool-use loop (`run_turn`) |
| `ui.py` | Colors and appearance for all console output |
| `logger.py` | File-only rotating logging (`logs/agent.log`) |
| `API/flask_gateway.py` | Optional SSE proxy: forwards `/v2/chat` to the Cohere API (host it on any provider, point `apiUrl` at it) |
| `API/requirements.txt` | Proxy dependencies (flask, requests, gunicorn) |
| `API/DEPLOY.md` | Hosting instructions for the proxy (local / PythonAnywhere / Render / Railway / Fly) |

## How a turn works

1. `agent.py` reads your input and appends it to the conversation.
2. `agent_loop.run_turn` loops until the model produces a final answer:
   - `streaming.consume_stream` calls the API (with retry/backoff), streams
     thinking + answer text, and collects tool plans and tool calls.
   - No tool calls? The streamed text is the final answer.
   - Tool calls? Each one is displayed before execution, executed via
     `tool_dispatch`, then displayed with an outcome summary; the results are
     appended as `tool` messages and the loop continues.
3. The turn ends with a token-usage summary and everything is logged.

## API proxy (optional)

`API/flask_gateway.py` is a small Flask server that relays `POST /v2/chat`
requests to `https://api.cohere.com/v2/chat`, streaming the SSE response
back to the caller. Host it on any provider and point a `tokens.json`
entry's `apiUrl` at it - the Cohere SDK automatically calls
`{apiUrl}/v2/chat`, so no agent changes are needed.

Run it locally:

```bash
pip install -r API/requirements.txt
python API/flask_gateway.py   # serves on 0.0.0.0:8000
```

Then add an entry like
`{"token": "cohere_...", "apiUrl": "http://127.0.0.1:8000"}` to
`tokens.json`. The gateway also exposes `GET /health` for provider
liveness probes. See `API/DEPLOY.md` for provider-specific hosting
instructions (PythonAnywhere, Render, Railway, Fly.io).

## Support

If you run into any issues with the agent CLI (bugs, unexpected behavior,
setup problems), contact me on Telegram: **[@Warriorx0](https://t.me/Warriorx0)**.

Please include a short description of the problem and, if possible, the
relevant lines from `logs/agent.log` - that makes debugging much faster.
