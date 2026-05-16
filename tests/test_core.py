from faah_terminal.core import Config, init_snippet, output_matches, should_alert


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
