# faah-terminal

Terminal error drama alarm inspired by Faah for VS Code.

It plays the Faah sound when terminal commands fail, so the drama follows you into Hermes, Codex, Claude Code, raw zsh, tmux, CI sessions, and whatever cursed shell you are living in.

Original VS Code extension and sound:
- https://marketplace.visualstudio.com/items?itemName=thk.faah
- https://github.com/kiron0/faah

The bundled `faah.wav` is from `kiron0/faah`, which is MIT licensed. See `NOTICE`.

## Install globally

From GitHub once pushed:

```bash
pipx install git+https://github.com/AlbanBeluli/faah-terminal.git
```

From a local checkout:

```bash
pipx install /path/to/faah-terminal
```

Without pipx:

```bash
python3 -m pip install --user /path/to/faah-terminal
```

## Enable in your shell

For zsh:

```bash
faah init zsh >> ~/.zshrc
exec zsh
```

For bash:

```bash
faah init bash >> ~/.bashrc
exec bash
```

For fish:

```fish
faah init fish >> ~/.config/fish/config.fish
exec fish
```

After this, any interactive command exiting non-zero triggers the sound.

Example:

```bash
false
# FAAH
```

## Wrap a command explicitly

Useful for Hermes/Codex/Claude launchers, long jobs, scripts, and CI-like flows:

```bash
faah run -- pytest
faah run -- npm test
faah run -- claude
faah run -- codex
faah run -- hermes
```

`faah run` alerts on either non-zero exit or scary output by default.

## Commands

```bash
faah test                         # force-play the sound
faah alert --reason "boom"         # play, respecting cooldown
faah snooze 30                    # snooze for 30 minutes
faah unsnooze                     # clear snooze
faah config show                  # print config JSON
faah config path                  # print config file path
faah config set cooldown_seconds 5
faah config set mode exit-code    # exit-code | output | either
faah config set sound bell        # faah | bell | /path/file.wav | command:<cmd>
faah config set quiet_hours 23:00-08:00
```

## Config

Config lives at:

```bash
~/.config/faah/config.json
```

Default config:

```json
{
  "enabled": true,
  "mode": "either",
  "cooldown_seconds": 15,
  "sound": "faah",
  "visual": true,
  "quiet_hours": "",
  "patterns": ["..."],
  "excludes": ["..."]
}
```

## Why this works broadly

VS Code/Cursor extensions only see their integrated terminal/diagnostics. This package hooks the actual shell prompt and/or wraps commands, so it works anywhere the shell works: native terminal, tmux, SSH, Hermes, Codex, Claude Code, etc.

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e . pytest build
pytest
python -m build
```

## License

MIT. See `LICENSE` and `NOTICE`.
