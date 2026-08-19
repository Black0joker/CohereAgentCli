"""Adapter for the shared tool engine (module.py).

Single responsibility: wire the agent to module.py's execute_tool -
provide the Logger that module.py expects, and expose workspace setup
and tool execution. No agent-loop logic.
"""

import module as tool_module

import ui


class ConsoleLogger:
    """Logger injected into module.py (it references a global `Logger`
    that is not defined there; we provide one instead of modifying
    module.py)."""

    def info(self, msg: str) -> None:
        ui.log("info", msg)

    def warn(self, msg: str) -> None:
        ui.log("warn", msg)

    def error(self, msg: str) -> None:
        ui.log("error", msg)


tool_module.Logger = ConsoleLogger()


def set_workspace(path: str) -> bool:
    """Pin the tool engine's working directory (sandbox root)."""
    return tool_module.set_working_directory(path)


def execute_tool(name: str, arguments: dict) -> dict:
    """Execute a tool by name via the shared engine; returns its envelope."""
    return tool_module.execute_tool(name, arguments)
