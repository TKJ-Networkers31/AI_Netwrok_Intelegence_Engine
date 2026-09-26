"""Abstract interface every model provider must implement.

Keeping this interface small (generate + health_check) lets the Agent stay
completely provider-agnostic, and lets new providers be added later without
touching Agent logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.types import Context, ExecutionResult


class ModelProvider(ABC):
    """Abstract base class for all model providers (Ollama, future ones)."""

    @abstractmethod
    def generate(self, context: Context) -> ExecutionResult:
        """Generate a response for the given context.

        Implementations must never raise for expected failure modes
        (connection errors, timeouts, model-not-found, etc.) — they should
        catch those and return a failed ExecutionResult with a structured
        ExecutionError instead. Unexpected exceptions may propagate.
        """
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the provider is reachable and ready to serve
        requests, False otherwise. Must not raise.
        """
        raise NotImplementedError
