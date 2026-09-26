from __future__ import annotations

from app.core.agent import Agent
from app.core.types import ErrorCode
from cli.main import format_error, run_single


def test_run_single_success(capsys, fake_router):
    agent = Agent(router=fake_router)

    exit_code = run_single(agent, "Explain VLAN", debug=False)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "fake response" in captured.out


def test_run_single_error(capsys, fake_router, fake_provider):
    fake_provider.should_fail = True
    fake_provider.error_code = ErrorCode.MODEL_UNAVAILABLE
    agent = Agent(router=fake_router)

    exit_code = run_single(agent, "Explain VLAN", debug=False)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "model_unavailable" in captured.err


def test_format_error_hides_details_without_debug(fake_router, fake_provider):
    fake_provider.should_fail = True
    agent = Agent(router=fake_router)
    result = agent.run("hi")

    message = format_error(result, debug=False)

    assert "Details" not in message
