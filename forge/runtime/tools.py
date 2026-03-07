"""Tool registry and base classes for agent tools."""

from __future__ import annotations

import importlib
import inspect
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class ToolParameter:
    """A parameter for a tool."""
    name: str
    type: str  # "string", "integer", "number", "boolean", "array", "object"
    description: str
    required: bool = True
    enum: list[str] | None = None
    default: Any = None


@dataclass
class Tool:
    """
    A tool that agents can use.
    
    Tools wrap callable functions with metadata for LLM function calling.
    """
    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)
    _fn: Callable[..., Awaitable[Any]] | Callable[..., Any] | None = None

    async def run(self, **kwargs: Any) -> Any:
        """Execute the tool with given arguments."""
        # Validate required parameters
        for param in self.parameters:
            if param.required and param.name not in kwargs:
                raise ValueError(f"Tool '{self.name}' requires parameter '{param.name}' ({param.description})")

        if self._fn is None:
            raise NotImplementedError(f"Tool '{self.name}' has no implementation.")
        if inspect.iscoroutinefunction(self._fn):
            return await self._fn(**kwargs)
        return self._fn(**kwargs)

    def to_openai_schema(self) -> dict[str, Any]:
        """Convert to OpenAI function calling schema."""
        properties = {}
        required = []
        for p in self.parameters:
            prop: dict[str, Any] = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            properties[p.name] = prop
            if p.required:
                required.append(p.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


def tool(name: str | None = None, description: str | None = None) -> Callable:
    """Decorator to turn a function into a Tool."""
    def decorator(fn: Callable) -> Tool:
        tool_name = name or fn.__name__
        tool_desc = description or fn.__doc__ or ""

        # Infer parameters from function signature
        sig = inspect.signature(fn)
        params = []
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }
        for pname, param in sig.parameters.items():
            if pname in ("self", "cls"):
                continue
            annotation = param.annotation
            ptype = type_map.get(annotation, "string")
            required = param.default is inspect.Parameter.empty
            params.append(ToolParameter(
                name=pname,
                type=ptype,
                description=f"Parameter: {pname}",
                required=required,
                default=None if required else param.default,
            ))

        t = Tool(name=tool_name, description=tool_desc, parameters=params, _fn=fn)
        return t
    return decorator


class ToolRegistry:
    """Registry of tools available to an agent."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, t: Tool) -> None:
        """Register a tool."""
        self._tools[t.name] = t

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        """List all registered tools."""
        return list(self._tools.values())

    def get_openai_tools_schema(self) -> list[dict[str, Any]]:
        """Get all tools in OpenAI function calling format."""
        return [t.to_openai_schema() for t in self._tools.values()]


def _import_dotted_path(dotted_path: str) -> Callable:
    """Import a callable from a dotted path like 'myapp.refunds.process_refund'."""
    module_path, _, attr_name = dotted_path.rpartition(".")
    if not module_path:
        raise ImportError(f"Invalid dotted path (no module): {dotted_path}")
    module = importlib.import_module(module_path)
    fn = getattr(module, attr_name)
    if not callable(fn):
        raise TypeError(f"{dotted_path} is not callable")
    return fn


class ToolExecutor:
    """Executes tools with optional real backend overrides.

    Allows registering real backend functions for tools at runtime,
    either programmatically or from a JSON config file.  When ``execute``
    is called, the registered backend (if any) takes precedence over the
    tool's default ``run()`` method.
    """

    def __init__(self) -> None:
        self._backends: dict[str, Callable] = {}

    def register_backend(self, tool_name: str, fn: Callable) -> None:
        """Register a real backend function for a tool."""
        self._backends[tool_name] = fn

    def load_backends_from_config(self, config_path: str) -> None:
        """Load backend mappings from a JSON config file.

        Config format::

            {"process_refund": "myapp.refunds.process_refund", ...}
        """
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Backend config not found: {config_path}")

        data = json.loads(path.read_text(encoding="utf-8"))
        for tool_name, dotted_path in data.items():
            if tool_name.startswith("_"):
                continue  # skip comment keys like "_comment"
            try:
                fn = _import_dotted_path(dotted_path)
                self._backends[tool_name] = fn
                logger.info("Loaded backend for tool '%s' from '%s'", tool_name, dotted_path)
            except (ImportError, TypeError, AttributeError) as exc:
                logger.warning(
                    "Failed to load backend for tool '%s' from '%s': %s",
                    tool_name, dotted_path, exc,
                )

    def has_backend(self, tool_name: str) -> bool:
        """Check whether a real backend is registered for a tool."""
        return tool_name in self._backends

    async def execute(self, tool: Tool, **kwargs: Any) -> Any:
        """Execute tool, using real backend if registered, otherwise default."""
        if tool.name in self._backends:
            fn = self._backends[tool.name]
            if inspect.iscoroutinefunction(fn):
                return await fn(**kwargs)
            return fn(**kwargs)
        return await tool.run(**kwargs)
