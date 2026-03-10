from __future__ import annotations

from tests.test_support.output_control import emit_test_output, should_verbose_test_output


def test_should_verbose_test_output_defaults_false() -> None:
    assert should_verbose_test_output({}) is False


def test_should_verbose_test_output_accepts_truthy_values() -> None:
    assert should_verbose_test_output({"LOTUS_TESTS_VERBOSE": "true"}) is True
    assert should_verbose_test_output({"LOTUS_TESTS_VERBOSE": "1"}) is True


def test_emit_test_output_suppresses_verbose_only_messages_when_disabled(capsys) -> None:
    emit_test_output("hidden", verbose_only=True)
    captured = capsys.readouterr()
    assert captured.out == ""


def test_emit_test_output_writes_when_verbose_enabled(capsys, monkeypatch) -> None:
    monkeypatch.setenv("LOTUS_TESTS_VERBOSE", "1")
    emit_test_output("shown", verbose_only=True)
    captured = capsys.readouterr()
    assert captured.out == "shown\n"


def test_emit_test_output_always_writes_non_verbose_messages(capsys) -> None:
    emit_test_output("always")
    captured = capsys.readouterr()
    assert captured.out == "always\n"
