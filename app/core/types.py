"""Core data types shared across ANIE.

These are intentionally minimal structured representations used instead of
passing raw dictionaries around the codebase.

Phase 2 extends Phase 0/1's `Context`/`Message`/`ExecutionResult` with the
smallest possible tool-calling contract: `Context.tools` (provider-agnostic
tool/function definitions handed to a provider), `Message`/`Role.TOOL` (a
tool-role message carrying a tool's result back to the model), and
`ExecutionResult.tool_calls` (a model's request to invoke one or more
tools, in lieu of a final text response). This does not change the
`ModelProvider.generate(context) -> ExecutionResult` interface at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Role(str, Enum):
    """Role of a single message in a conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ToolCall:
    """A single tool invocation requested by a model.

    `arguments` is always a plain dict here, regardless of whether the
    underlying provider sent arguments as a JSON string (NVIDIA/OpenAI
    style) or a native object (Ollama style) — providers normalize this
    before constructing a ToolCall.
    """

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    """A single message in a conversation.

    `tool_calls` is set on an assistant message that requested tool use.
    `tool_call_id`/`name` are set on a `Role.TOOL` message reporting a
    tool's result back to the model.
    """

    role: Role
    content: str
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None
    name: Optional[str] = None


@dataclass
class Context:
    """Minimal structured context passed from the Agent to a ModelProvider.

    Phase 0/1 do not implement persistent memory: a Context only exists for
    the lifetime of a single `agent.run(...)` call. It stays
    provider-independent: it knows about system prompt + a conversation of
    messages, nothing about how a specific provider serializes them.

    Phase 2 adds `tools`: an optional list of provider-agnostic tool/
    function definitions (OpenAI "tools" shape:
    `{"type": "function", "function": {"name", "description", "parameters"}}`)
    that a provider forwards to the model if it supports tool calling.
    """

    system_prompt: Optional[str] = None
    messages: list[Message] = field(default_factory=list)
    tools: Optional[list[dict[str, Any]]] = None

    def add_user_message(self, content: str) -> None:
        self.messages.append(Message(role=Role.USER, content=content))

    def add_assistant_message(self, content: str) -> None:
        self.messages.append(Message(role=Role.ASSISTANT, content=content))

    def add_assistant_tool_calls(self, tool_calls: list[ToolCall]) -> None:
        """Record that the assistant requested these tool calls, so the
        conversation replayed to the provider on the next turn reflects
        what actually happened."""
        self.messages.append(Message(role=Role.ASSISTANT, content="", tool_calls=list(tool_calls)))

    def add_tool_result(self, tool_call_id: str, name: str, content: str) -> None:
        """Record a tool's (structured, JSON-serialized) result so the model
        can see it on the next `generate()` call."""
        self.messages.append(Message(role=Role.TOOL, content=content, tool_call_id=tool_call_id, name=name))

    def as_prompt_messages(self) -> list[dict[str, Any]]:
        """Return messages (including system prompt) as plain dicts.

        This is a convenience representation useful for providers whose APIs
        expect a list of {"role": ..., "content": ...} dicts (e.g. Ollama's
        chat endpoint and NVIDIA's OpenAI-compatible chat endpoint), extended
        to carry `tool_calls`/`tool_call_id`/`name` when present so a
        tool-calling round trip can be replayed to the provider.
        """
        result: list[dict[str, Any]] = []
        if self.system_prompt:
            result.append({"role": Role.SYSTEM.value, "content": self.system_prompt})
        for message in self.messages:
            entry: dict[str, Any] = {"role": message.role.value, "content": message.content}
            if message.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.name,
                            "arguments": json.dumps(tool_call.arguments),
                        },
                    }
                    for tool_call in message.tool_calls
                ]
            if message.tool_call_id:
                entry["tool_call_id"] = message.tool_call_id
            if message.name:
                entry["name"] = message.name
            result.append(entry)
        return result


class ErrorCode(str, Enum):
    """Stable, structured error codes used across ANIE.

    CLI and callers should branch on these rather than parsing error strings.
    """

    INVALID_CONFIGURATION = "invalid_configuration"
    INVALID_PROVIDER = "invalid_provider"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    CONNECTION_TIMEOUT = "connection_timeout"
    MODEL_UNAVAILABLE = "model_unavailable"
    MODEL_REQUEST_FAILED = "model_request_failed"
    AUTHENTICATION_FAILED = "authentication_failed"
    ALL_PROVIDERS_FAILED = "all_providers_failed"
    TOOL_EXECUTION_FAILED = "tool_execution_failed"
    UNKNOWN = "unknown"


@dataclass
class ExecutionError:
    """Structured error information, as an alternative to raw exceptions."""

    code: ErrorCode
    message: str
    details: Optional[dict[str, Any]] = None


@dataclass
class ExecutionResult:
    """Structured result returned by the Agent (and providers) instead of
    arbitrary dictionaries.

    Phase 2 adds `tool_calls`: when set (and `success` is True), this
    result represents a model *requesting* tool use rather than a final
    answer — `response` stays `None` in that case. The Agent is
    responsible for executing the requested tools and calling the provider
    again; a `ModelProvider` never executes tools itself.
    """

    success: bool
    response: Optional[str] = None
    error: Optional[ExecutionError] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tool_calls: Optional[list[ToolCall]] = None

    @classmethod
    def ok(cls, response: str, **metadata: Any) -> "ExecutionResult":
        return cls(success=True, response=response, metadata=metadata)

    @classmethod
    def tool_call_requested(cls, tool_calls: list[ToolCall], **metadata: Any) -> "ExecutionResult":
        return cls(success=True, response=None, tool_calls=list(tool_calls), metadata=metadata)

    @classmethod
    def fail(
        cls,
        code: ErrorCode,
        message: str,
        details: Optional[dict[str, Any]] = None,
        **metadata: Any,
    ) -> "ExecutionResult":
        return cls(
            success=False,
            error=ExecutionError(code=code, message=message, details=details),
            metadata=metadata,
        )
