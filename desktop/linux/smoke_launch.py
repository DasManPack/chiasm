from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path



def _stop_process_group(process: subprocess.Popen[str]) -> None:
    """Stop the packaged app and any child process left by an AppImage wrapper."""

    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        time.sleep(0.25)
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return

    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test a packaged Chiasm GUI launch.")
    parser.add_argument("executable", type=Path)
    parser.add_argument(
        "--appimage",
        action="store_true",
        help="run the AppImage in extract-and-run mode so CI does not need FUSE",
    )
    args = parser.parse_args()
    executable = args.executable.resolve()
    if not executable.is_file():
        raise SystemExit(f"packaged executable not found: {executable}")

    command = [str(executable)]
    if args.appimage:
        command.append("--appimage-extract-and-run")

    with tempfile.TemporaryDirectory(prefix="melodex-linux-smoke-") as directory:
        temporary = Path(directory)
        data_home = temporary / "data"
        home = temporary / "home"
        home.mkdir()
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(home),
                "XDG_DATA_HOME": str(data_home),
                "XDG_CONFIG_HOME": str(temporary / "config"),
                "XDG_CACHE_HOME": str(temporary / "cache"),
                "QT_QPA_PLATFORM": "offscreen",
            }
        )
        log_path = temporary / "launch.log"
        with log_path.open("w", encoding="utf-8") as log:
            first = subprocess.Popen(
                command,
                env=env,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
            lock = data_home / "melodex/melodex-instance.lock"
            deadline = time.monotonic() + 45
            try:
                while time.monotonic() < deadline:
                    if first.poll() is not None:
                        raise SystemExit(
                            f"Chiasm exited before acquiring its inherited single-instance lock "
                            f"(exit {first.returncode}):\n{log_path.read_text('utf-8')}"
                        )
                    if lock.is_file():
                        break
                    time.sleep(0.1)
                else:
                    raise SystemExit(
                        f"Chiasm did not create its inherited single-instance lock:\n"
                        f"{log_path.read_text('utf-8')}"
                    )

                second = subprocess.run(
                    command,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=45,
                    check=False,
                )
                if second.returncode != 0:
                    raise SystemExit(
                        f"second GUI launch returned {second.returncode}:\n{second.stdout}"
                    )
                print(f"Packaged GUI launch and single-instance check passed: {executable}")
            finally:
                _stop_process_group(first)
                try:
                    first.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
