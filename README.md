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

1. Copy the example env file:

   ```bash
   cp .env_example .env
   ```

2. Put your API key in `.env` (never commit this file - it is git-ignored):

   ```
   COHERE_API_KEY=cohere_xxxxxxxxxxxxxxxxxxxxxxxx
   ```

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

## Project structure

Each file has a single responsibility:

| File | Responsibility |
|---|---|
| `agent.py` | CLI entry point: bootstrap + interactive REPL |
| `config.py` | Configuration constants (model, step limit, env file) |
| `env_loader.py` | `.env` parsing (`COHERE_API_KEY`) |
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

## How a turn works

1. `agent.py` reads your input and appends it to the conversation.
2. `agent_loop.run_turn` loops (up to `config.MAX_STEPS`):
   - `streaming.consume_stream` calls the API (with retry/backoff), streams
     thinking + answer text, and collects tool plans and tool calls.
   - No tool calls? The streamed text is the final answer.
   - Tool calls? Each one is displayed before execution, executed via
     `tool_dispatch`, then displayed with an outcome summary; the results are
     appended as `tool` messages and the loop continues.
3. The turn ends with a token-usage summary and everything is logged.
