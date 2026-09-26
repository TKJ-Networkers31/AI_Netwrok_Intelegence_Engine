"""ANIE CLI.

Usage:
    anie "Explain VLAN"      # single-shot
    anie                     # interactive mode
    anie --debug "..."       # show full internal error details
"""

from __future__ import annotations

import argparse
import sys

from app.core.agent import Agent
from app.core.config import Config, ConfigError
from app.core.logging_setup import configure_logging
from app.core.types import ExecutionResult
from app.models.router import ModelRouter, UnsupportedProviderError

PROMPT = "ANIE > "


def build_agent(config_path: str | None = None) -> Agent:
    config = Config.load(config_path)
    configure_logging(config.runtime.log_level)
    router = ModelRouter(config)
    return Agent(router)


def format_error(result: ExecutionResult, debug: bool) -> str:
    assert result.error is not None
    base = f"Error [{result.error.code.value}]: {result.error.message}"
    if debug and result.error.details:
        base += f"\nDetails: {result.error.details}"
    return base


def run_single(agent: Agent, user_input: str, debug: bool) -> int:
    result = agent.run(user_input)
    if result.success:
        print(result.response)
        return 0
    print(format_error(result, debug), file=sys.stderr)
    return 1


def run_interactive(agent: Agent, debug: bool) -> int:
    print(f"{PROMPT}ANIE interactive mode. Type 'exit' or 'quit' to leave.")
    while True:
        try:
            user_input = input(PROMPT).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            return 0

        result = agent.run(user_input)
        if result.success:
            print(result.response)
        else:
            print(format_error(result, debug), file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="anie", description="ANIE network engineering assistant")
    parser.add_argument("prompt", nargs="?", help="Prompt to send. Omit for interactive mode.")
    parser.add_argument("--config", dest="config_path", default=None, help="Path to config.yaml")
    parser.add_argument("--debug", action="store_true", help="Show full internal error details")
    args = parser.parse_args(argv)

    try:
        agent = build_agent(args.config_path)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    except UnsupportedProviderError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    if args.prompt:
        return run_single(agent, args.prompt, args.debug)
    return run_interactive(agent, args.debug)


if __name__ == "__main__":
    sys.exit(main())
