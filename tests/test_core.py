from faah_terminal.core import Config, init_snippet, output_matches, play_alert, should_alert


def test_output_matches_default_error():
    assert output_matches("Traceback (most recent call last):\nValueError: nope", Config())


def test_output_excludes_false_positive():
    assert not output_matches("0 errors, 0 warnings", Config())


def test_should_alert_modes():
    cfg = Config(mode="exit-code")
    assert should_alert(1, False, cfg)
    assert not should_alert(0, True, cfg)

    cfg = Config(mode="output")
    assert not should_alert(1, False, cfg)
    assert should_alert(0, True, cfg)

    cfg = Config(mode="either")
    assert should_alert(1, False, cfg)
    assert should_alert(0, True, cfg)


def test_init_snippet_mentions_faah():
    assert "faah alert" in init_snippet("zsh")
    assert "PROMPT_COMMAND" in init_snippet("bash")
    assert "fish_postexec" in init_snippet("fish")


def test_init_snippet_auto_wraps_agent_commands():
    for shell in ("zsh", "bash", "fish"):
        snippet = init_snippet(shell)
        assert "FAAH_WRAP_COMMANDS" in snippet
        assert "hermes openclaw claude codex" in snippet
        assert "faah run --" in snippet


def test_forced_alert_does_not_consume_cooldown(monkeypatch, tmp_path):
    monkeypatch.setattr("faah_terminal.core.STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr("faah_terminal.core._play_sound", lambda sound: True)

    cfg = Config(cooldown_seconds=60, visual=False)
    assert play_alert("installer test", config=cfg, force=True)
    assert play_alert("first real failure", config=cfg)
