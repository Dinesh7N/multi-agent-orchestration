"""
Agent-as-tool abstraction for uniform agent invocation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ..run_agent import AgentResult, AgentType, Phase, run_agent


@dataclass
class ToolResult:
    """Result from a tool invocation."""

    success: bool
    output: Any
    error: str | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}


class BaseTool(ABC):
    """Base class for all tools."""

    name: str
    description: str

    @abstractmethod
    async def run(self, **kwargs: Any) -> ToolResult:
        pass


class AgentTool(BaseTool):
    """Wraps an agent as a callable tool."""

    def __init__(
        self,
        agent_type: AgentType,
        name: str | None = None,
        description: str | None = None,
    ):
        self.agent_type = agent_type
        self.name = name or f"{agent_type.value}_tool"
        self.description = description or f"Invoke {agent_type.value} agent"

    async def run(
        self,
        task_slug: str,
        round_number: int = 0,
        phase: str = "analysis",
        **kwargs: Any,
    ) -> ToolResult:
        del kwargs
        try:
            result: AgentResult = await run_agent(
                task_slug=task_slug,
                agent=self.agent_type,
                round_number=round_number,
                phase=Phase(phase),
            )
            return ToolResult(
                success=True,
                output=result.raw_output,
                metadata={
                    "agent": self.agent_type.value,
                    "round": round_number,
                    "phase": phase,
                },
            )
        except Exception as exc:
            return ToolResult(success=False, output=None, error=str(exc))


GeminiTool = AgentTool(
    AgentType.GEMINI,
    name="gemini_analyzer",
    description="Large context codebase analysis with Gemini",
)

ClaudeTool = AgentTool(
    AgentType.CLAUDE,
    name="claude_analyzer",
    description="Deep reasoning and security analysis with Claude",
)

CodexTool = AgentTool(
    AgentType.CODEX,
    name="codex_implementer",
    description="Code implementation with Codex",
)


class ToolRegistry:
    """Registry of available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())


default_registry = ToolRegistry()
default_registry.register(GeminiTool)
default_registry.register(ClaudeTool)
default_registry.register(CodexTool)
