"""Cohere function-calling tool schemas.

Single responsibility: declare the tool schemas sent to the model
(mirrors module.EXPECTED_TOOLS). No execution logic.
"""


def _s(type_: str, desc: str) -> dict:
    return {"type": type_, "description": desc}


COHERE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "current_path",
            "description": "Return the absolute path of the workspace root.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List the immediate contents of a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": _s("string", "Directory relative to the workspace; use '.' for the root."),
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "Find files matching a glob pattern (supports ** for recursion).",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": _s("string", "Glob pattern, e.g. '**/*.py'."),
                    "path": _s("string", "Base directory relative to the workspace (optional, default '.')."),
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_search",
            "description": "Search file contents with a regular expression across a directory tree or a single file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": _s("string", "Regular expression to search for."),
                    "path": _s("string", "Directory or file to search (optional, default '.')."),
                    "include": _s("string", "Filename glob filter, e.g. '*.py' (optional, default '*')."),
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the text content of a file, optionally a specific line range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": _s("string", "File path relative to the workspace."),
                    "start_line": _s("integer", "First line to read, 1-based (optional)."),
                    "end_line": _s("integer", "Last line to read, 1-based (optional)."),
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create a new file or completely replace an existing one. Missing parent directories are created.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": _s("string", "File path relative to the workspace."),
                    "content": _s("string", "Full file content to write."),
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replace",
            "description": (
                "Replace exactly one matched text block in an existing file using a "
                "safety-first matching engine. The search text must match a unique location."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": _s("string", "File path relative to the workspace."),
                    "search": _s("string", "Exact existing text to find (copy verbatim from read_file output)."),
                    "replace": _s("string", "New text that replaces the matched block."),
                },
                "required": ["path", "search", "replace"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell_command",
            "description": "Execute a shell command in the foreground or background and return its output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": _s("string", "The shell command to run."),
                    "cwd": _s("string", "Working directory relative to the workspace (optional, default '.')."),
                    "timeout": _s("integer", "Timeout in seconds (optional, default 1800)."),
                    "background": _s("boolean", "Run in background if true (optional, default false)."),
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "code_interpreter",
            "description": "Execute a Python code snippet directly and return stdout/stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": _s("string", "Python code to execute. Use print() to surface results."),
                    "timeout": _s("integer", "Timeout in seconds (optional, default 60)."),
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_background_processes",
            "description": "List all tracked background processes.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_background_output",
            "description": "Read the (possibly partial) output of a background process by its id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": _s("string", "The background process id."),
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kill_process",
            "description": "Terminate a running background process by its id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": _s("string", "The background process id."),
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "enter_plan_mode",
            "description": "Toggle read-only plan mode (research/design without modifications).",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan": _s("boolean", "true to enter plan mode, false to exit."),
                },
                "required": ["plan"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "google_web_search",
            "description": "Search the web and return up to 10 results (title, url).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": _s("string", "The search query."),
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch the content of a URL (truncated to 10,000 characters).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": _s("string", "The URL to fetch."),
                },
                "required": ["url"],
            },
        },
    },
]
