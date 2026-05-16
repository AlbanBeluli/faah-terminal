from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from importlib import resources
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("FAAH_CONFIG_DIR", Path.home() / ".config" / "faah"))
CONFIG_PATH = Path(os.environ.get("FAAH_CONFIG", CONFIG_DIR / "config.json"))
STATE_PATH = Path(os.environ.get("FAAH_STATE", CONFIG_DIR / "state.json"))

DEFAULT_PATTERNS = [
    r"(?i)\berror\b",
    r"(?i)\bfatal\b",
    r"(?i)\bexception\b",
    r"(?i)traceback \(most recent call last\)",
    r"(?i)panic:",
    r"(?i)segmentation fault",
    r"(?i)command not found",
    r"(?i)permission denied",
    r"(?i)failed\b",
]

DEFAULT_EXCLUDES = [
    r"(?i)0 errors?",
    r"(?i)no errors?",
    r"(?i)error rate",
    r"(?i)expected error",
]


@dataclass
class Config:
    enabled: bool = True
    mode: str = "either"  # exit-code, output, either
    cooldown_seconds: int = 15
    sound: str = "faah"  # faah, bell, path to file, command:<shell command>
    visual: bool = True
    quiet_hours: str = ""  # HH:MM-HH:MM
    patterns: list[str] = field(default_factory=lambda: DEFAULT_PATTERNS.copy())
    excludes: list[str] = field(default_factory=lambda: DEFAULT_EXCLUDES.copy())

    @classmethod
    def load(cls) -> "Config":
        if not CONFIG_PATH.exists():
            return cls()
        try:
            raw = json.loads(CONFIG_PATH.read_text())
        except Exception:
            return cls()
        base = asdict(cls())
        base.update({k: v for k, v in raw.items() if k in base})
        return cls(**base)

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(asdict(self), indent=2) + "\n")


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")


def is_quiet_now(quiet_hours: str) -> bool:
    if not quiet_hours or "-" not in quiet_hours:
        return False
    start, end = quiet_hours.split("-", 1)
    try:
        sh, sm = [int(x) for x in start.split(":", 1)]
        eh, em = [int(x) for x in end.split(":", 1)]
    except ValueError:
        return False
    now = time.localtime()
    current = now.tm_hour * 60 + now.tm_min
    s = sh * 60 + sm
    e = eh * 60 + em
    if s <= e:
        return s <= current < e
    return current >= s or current < e


def is_snoozed() -> bool:
    until = float(_load_state().get("snoozed_until", 0) or 0)
    return time.time() < until


def snooze(seconds: int) -> None:
    state = _load_state()
    state["snoozed_until"] = time.time() + seconds
    _save_state(state)


def clear_snooze() -> None:
    state = _load_state()
    state.pop("snoozed_until", None)
    _save_state(state)


def can_alert(config: Config) -> tuple[bool, str]:
    if not config.enabled:
        return False, "disabled"
    if is_snoozed():
        return False, "snoozed"
    if is_quiet_now(config.quiet_hours):
        return False, "quiet-hours"
    state = _load_state()
    last = float(state.get("last_alert", 0) or 0)
    remaining = config.cooldown_seconds - (time.time() - last)
    if remaining > 0:
        return False, f"cooldown:{int(remaining)}s"
    return True, "ok"


def mark_alerted() -> None:
    state = _load_state()
    state["last_alert"] = time.time()
    _save_state(state)


def output_matches(text: str, config: Config) -> bool:
    if not text:
        return False
    for pattern in config.excludes:
        if re.search(pattern, text):
            return False
    return any(re.search(pattern, text) for pattern in config.patterns)


def should_alert(exit_code: int | None, matched_output: bool, config: Config) -> bool:
    mode = config.mode
    exit_failed = exit_code not in (None, 0)
    if mode == "exit-code":
        return exit_failed
    if mode == "output":
        return matched_output
    return exit_failed or matched_output


def play_alert(reason: str = "error", config: Config | None = None, force: bool = False) -> bool:
    config = config or Config.load()
    ok, why = can_alert(config)
    if not force and not ok:
        return False

    if config.visual:
        sys.stderr.write(f"\n🚨 FAAH: {reason}\n")
        sys.stderr.flush()

    played = _play_sound(config.sound)
    if played and not force:
        mark_alerted()
    return played


def _play_sound(sound: str) -> bool:
    if sound.startswith("command:"):
        cmd = sound.removeprefix("command:").strip()
        return subprocess.call(cmd, shell=True) == 0

    candidate = Path(os.path.expanduser(sound))
    if candidate.exists():
        return _play_file(candidate)

    if sound == "bell":
        sys.stderr.write("\a")
        sys.stderr.flush()
        return True

    # Default: bundled MIT-licensed faah.wav from https://github.com/kiron0/faah.
    if sound == "faah":
        try:
            with resources.as_file(resources.files("faah_terminal.assets") / "faah.wav") as asset:
                if _play_file(asset):
                    return True
        except Exception:
            pass

    system = platform.system().lower()
    if system == "darwin" and shutil.which("say"):
        subprocess.Popen(["say", "Faaah"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    if shutil.which("paplay"):
        subprocess.Popen(["paplay", "/usr/share/sounds/freedesktop/stereo/dialog-warning.oga"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    sys.stderr.write("\a")
    sys.stderr.flush()
    return True


def _play_file(path: Path) -> bool:
    players = []
    if platform.system().lower() == "darwin":
        players.append(["afplay", str(path)])
    players.extend([["paplay", str(path)], ["aplay", str(path)], ["ffplay", "-nodisp", "-autoexit", str(path)]])
    for cmd in players:
        if shutil.which(cmd[0]):
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    return False


def init_snippet(shell: str = "zsh") -> str:
    shell = shell.lower()
    if shell == "zsh":
        return r'''# faah-terminal: alert when an interactive command exits non-zero
_faah_precmd() {
  local faah_status=$?
  if [[ -n "$FAAH_RUNNING" ]]; then return; fi
  if [[ $faah_status -ne 0 ]]; then
    FAAH_RUNNING=1 command faah alert --reason "exit $faah_status" >/dev/null 2>&1
    unset FAAH_RUNNING
  fi
}
autoload -Uz add-zsh-hook
add-zsh-hook precmd _faah_precmd
'''
    if shell == "bash":
        return r'''# faah-terminal: alert when an interactive command exits non-zero
_faah_prompt_command() {
  local faah_status=$?
  if [[ -n "$FAAH_RUNNING" ]]; then return $faah_status; fi
  if [[ $faah_status -ne 0 ]]; then
    FAAH_RUNNING=1 command faah alert --reason "exit $faah_status" >/dev/null 2>&1
    unset FAAH_RUNNING
  fi
  return $faah_status
}
if [[ -n "$PROMPT_COMMAND" ]]; then
  PROMPT_COMMAND="_faah_prompt_command; $PROMPT_COMMAND"
else
  PROMPT_COMMAND="_faah_prompt_command"
fi
'''
    if shell == "fish":
        return r'''# faah-terminal: alert when an interactive command exits non-zero
function _faah_postexec --on-event fish_postexec
  set -l faah_status $status
  if test -n "$FAAH_RUNNING"; return; end
  if test $faah_status -ne 0
    set -gx FAAH_RUNNING 1
    command faah alert --reason "exit $faah_status" >/dev/null 2>&1
    set -e FAAH_RUNNING
  end
end
'''
    raise ValueError(f"unsupported shell: {shell}")


def config_path() -> Path:
    return CONFIG_PATH
