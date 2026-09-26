"""Core data types shared across ANIE.

These are intentionally minimal structured representations used instead of
passing raw dictionaries around the codebase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Role(str, Enum):
    """Role of a single message in a conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class Message:
    """A single message in a conversation."""

    role: Role
    content: str


@dataclass
class Context:
    """Minimal structured context passed from the Agent to a ModelProvider.

    Phase 0/1 do not implement persistent memory: a Context only exists for
    the lifetime of a single `agent.run(...)` call. It stays
    provider-independent: it knows about system prompt + a conversation of
    messages, nothing about how a specific provider serializes them.
    """

    system_prompt: Optional[str] = None
    messages: list[Message] = field(default_factory=list)

    def add_user_message(self, content: str) -> None:
        self.messages.append(Message(role=Role.USER, content=content))

    def add_assistant_message(self, content: str) -> None:
        self.messages.append(Message(role=Role.ASSISTANT, content=content))

    def as_prompt_messages(self) -> list[dict[str, str]]:
        """Return messages (including system prompt) as plain dicts.

        This is a convenience representation useful for providers whose APIs
        expect a list of {"role": ..., "content": ...} dicts (e.g. Ollama's
        chat endpoint and NVIDIA's OpenAI-compatible chat endpoint).
        """
        result: list[dict[str, str]] = []
        if self.system_prompt:
            result.append({"role": Role.SYSTEM.value, "content": self.system_prompt})
        for message in self.messages:
            result.append({"role": message.role.value, "content": message.content})
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
    """

    success: bool
    response: Optional[str] = None
    error: Optional[ExecutionError] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, response: str, **metadata: Any) -> "ExecutionResult":
        return cls(success=True, response=response, metadata=metadata)

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
