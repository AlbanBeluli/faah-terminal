import json
import os
import pty
import select
import subprocess
import sys
import time


def _run_faah_in_pty(args, timeout=10, env=None):
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        [sys.executable, "-c", "from faah_terminal.cli import main; raise SystemExit(main())", *args],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env={**os.environ, **(env or {})},
        close_fds=True,
    )
    os.close(slave)
    output = bytearray()
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            ready, _, _ = select.select([master], [], [], 0.1)
            if ready:
                try:
                    output.extend(os.read(master, 4096))
                except OSError:
                    break
        proc.wait(timeout=1)
        while True:
            ready, _, _ = select.select([master], [], [], 0)
            if not ready:
                break
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            output.extend(chunk)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=1)
        os.close(master)
    return proc.returncode, output.decode(errors="replace")


def test_run_preserves_tty_for_interactive_commands():
    code, output = _run_faah_in_pty([
        "run",
        "--",
        sys.executable,
        "-c",
        "import sys; print(sys.stdin.isatty(), sys.stdout.isatty(), sys.stderr.isatty())",
    ])

    assert code == 0
    assert "True True True" in output


def test_run_alerts_from_pty_mode(tmp_path):
    config_path = tmp_path / "config.json"
    state_path = tmp_path / "state.json"
    config_path.write_text(json.dumps({"cooldown_seconds": 0, "sound": "bell", "visual": True}))

    code, output = _run_faah_in_pty(
        ["run", "--", sys.executable, "-c", "print('all good'); raise SystemExit(7)"],
        env={"FAAH_CONFIG": str(config_path), "FAAH_STATE": str(state_path)},
    )

    assert code == 7
    assert "all good" in output
    assert "FAAH: exit 7" in output
