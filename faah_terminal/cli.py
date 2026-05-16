from __future__ import annotations

import argparse
import fcntl
import json
import os
import pty
import select
import signal
import subprocess
import sys
import termios
import tty
from pathlib import Path

from .core import (
    Config,
    clear_snooze,
    config_path,
    init_snippet,
    output_matches,
    play_alert,
    should_alert,
    snooze,
)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="faah",
        description="Terminal error drama alarm. Play the Faah sound on failed commands or scary output.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Run a command and alert on non-zero exit or error-looking output")
    run.add_argument("command", nargs=argparse.REMAINDER, help="Command to run. Use -- before commands with flags.")
    run.add_argument("--mode", choices=["exit-code", "output", "either"], help="Detection mode override")

    alert = sub.add_parser("alert", help="Play the alert now")
    alert.add_argument("--reason", default="manual alert")
    alert.add_argument("--force", action="store_true", help="Ignore cooldown/quiet-hours/snooze")

    init = sub.add_parser("init", help="Print shell hook snippet for zsh/bash/fish")
    init.add_argument("shell", choices=["zsh", "bash", "fish"], nargs="?", default="zsh")

    cfg = sub.add_parser("config", help="Read or change config")
    cfg_sub = cfg.add_subparsers(dest="config_cmd", required=True)
    cfg_sub.add_parser("path", help="Print config path")
    cfg_sub.add_parser("show", help="Print config JSON")
    setp = cfg_sub.add_parser("set", help="Set one config key")
    setp.add_argument("key")
    setp.add_argument("value")

    snooze_p = sub.add_parser("snooze", help="Snooze alerts")
    snooze_p.add_argument("minutes", type=_positive_int)
    sub.add_parser("unsnooze", help="Clear snooze")
    sub.add_parser("test", help="Play a forced test alert")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = Config.load()

    if args.cmd == "run":
        if not args.command:
            parser.error("faah run needs a command")
        if args.command and args.command[0] == "--":
            args.command = args.command[1:]
        if args.mode:
            config.mode = args.mode
        return run_command(args.command, config)

    if args.cmd == "alert":
        return 0 if play_alert(args.reason, config=config, force=args.force) else 1

    if args.cmd == "test":
        return 0 if play_alert("test", config=config, force=True) else 1

    if args.cmd == "init":
        print(init_snippet(args.shell), end="")
        return 0

    if args.cmd == "config":
        return handle_config(args, config)

    if args.cmd == "snooze":
        snooze(args.minutes * 60)
        print(f"Faah snoozed for {args.minutes} minute(s)")
        return 0

    if args.cmd == "unsnooze":
        clear_snooze()
        print("Faah snooze cleared")
        return 0

    parser.error("unknown command")
    return 2


def run_command(command: list[str], config: Config) -> int:
    if _should_use_pty():
        return run_command_pty(command, config)
    return run_command_piped(command, config)


def _should_use_pty() -> bool:
    return os.name != "nt" and sys.stdin.isatty() and sys.stdout.isatty() and sys.stderr.isatty()


def _finish_run(code: int, text: str, config: Config) -> int:
    matched = output_matches(text, config)
    if should_alert(code, matched, config):
        reason = f"exit {code}" if code else "matched error output"
        play_alert(reason, config=config)
    return code


def run_command_piped(command: list[str], config: Config) -> int:
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    collected: list[str] = []
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            print(line, end="")
            collected.append(line)
    except KeyboardInterrupt:
        proc.terminate()
        raise
    code = proc.wait()
    return _finish_run(code, "".join(collected), config)


def run_command_pty(command: list[str], config: Config) -> int:
    master_fd, slave_fd = pty.openpty()
    stdin_fd = sys.stdin.fileno()
    stdout_fd = sys.stdout.fileno()
    old_tty = termios.tcgetattr(stdin_fd)
    old_winch_handler = signal.getsignal(signal.SIGWINCH)
    collected = bytearray()
    proc: subprocess.Popen[bytes] | None = None

    def resize_child(_signum: int | None = None, _frame: object | None = None) -> None:
        try:
            size = fcntl.ioctl(stdin_fd, termios.TIOCGWINSZ, b"\0" * 8)
            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, size)
        except OSError:
            pass

    try:
        resize_child()
        signal.signal(signal.SIGWINCH, resize_child)
        tty.setraw(stdin_fd)
        proc = subprocess.Popen(command, stdin=slave_fd, stdout=slave_fd, stderr=slave_fd, close_fds=True)
        os.close(slave_fd)
        slave_fd = -1

        while True:
            read_fds = [master_fd, stdin_fd]
            ready, _, _ = select.select(read_fds, [], [], 0.1)

            if master_fd in ready:
                try:
                    data = os.read(master_fd, 4096)
                except OSError:
                    data = b""
                if data:
                    collected.extend(data)
                    os.write(stdout_fd, data)
                elif proc.poll() is not None:
                    break

            if stdin_fd in ready:
                data = os.read(stdin_fd, 4096)
                if data:
                    os.write(master_fd, data)

            if proc.poll() is not None:
                # Drain anything still buffered after process exit.
                while True:
                    ready, _, _ = select.select([master_fd], [], [], 0)
                    if not ready:
                        break
                    try:
                        data = os.read(master_fd, 4096)
                    except OSError:
                        break
                    if not data:
                        break
                    collected.extend(data)
                    os.write(stdout_fd, data)
                break
    except KeyboardInterrupt:
        if proc and proc.poll() is None:
            proc.terminate()
        raise
    finally:
        signal.signal(signal.SIGWINCH, old_winch_handler)
        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_tty)
        if slave_fd != -1:
            os.close(slave_fd)
        try:
            os.close(master_fd)
        except OSError:
            pass

    assert proc is not None
    code = proc.wait()
    return _finish_run(code, collected.decode(errors="replace"), config)


def handle_config(args: argparse.Namespace, config: Config) -> int:
    if args.config_cmd == "path":
        print(config_path())
        return 0
    if args.config_cmd == "show":
        print(json.dumps(config.__dict__, indent=2))
        return 0
    if args.config_cmd == "set":
        if not hasattr(config, args.key):
            print(f"Unknown config key: {args.key}", file=sys.stderr)
            return 2
        current = getattr(config, args.key)
        value: object = args.value
        if isinstance(current, bool):
            value = args.value.lower() in {"1", "true", "yes", "on"}
        elif isinstance(current, int):
            value = int(args.value)
        elif isinstance(current, list):
            value = [x.strip() for x in args.value.split(",") if x.strip()]
        setattr(config, args.key, value)
        config.save()
        print(f"Set {args.key} = {value!r}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
