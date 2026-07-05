"""Agent tool definition + registry helpers.

An AgentTool pairs an LLM-facing spec (name/description/JSON-schema params) with
a deterministic async executor `(db, company, **args) -> dict`. Tools are tagged
`permission` ("read" | "write") so a later role can be granted read-only access
without touching individual tools (the write starter tools come in Phase 2).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company

Permission = Literal["read", "write"]

# executor(db, company, **args) -> JSON-safe dict
ToolExecutor = Callable[..., Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    # JSON-schema for the params object the model fills in.
    parameters: dict[str, Any]
    executor: ToolExecutor
    permission: Permission = "read"


def no_params() -> dict[str, Any]:
    return {"type": "object", "properties": {}, "required": []}


@dataclass
class ToolContext:
    """Binds a tool registry to one request (db + company) and records every
    tool output, so the money-safety gate can verify the final reply against
    exactly the numbers the tools returned.
    """

    db: AsyncSession
    company: Company
    tools: dict[str, AgentTool]
    outputs: list[dict[str, Any]] = field(default_factory=list)

    @property
    def company_id(self) -> uuid.UUID:
        return self.company.id

    async def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        tool = self.tools.get(name)
        if tool is None:
            return {"error": f"Unknown tool {name!r}."}
        try:
            result = await tool.executor(self.db, self.company, **(args or {}))
        except Exception as exc:  # noqa: BLE001 - a tool failure must not crash the loop
            result = {"error": f"{name} failed: {exc}"}
        self.outputs.append(result)
        return result
