"""Configure, run, inspect and stop standalone screenshot automation."""
import argparse
import json
from pathlib import Path
import sys
import time
import subprocess
import os

from src.background_service import (
    CONFIG_PATH, RUNTIME_DIR, configure, load_config, request_stop, run, status,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone copy-only screenshot automation")
    parser.add_argument("command", choices=("configure", "start", "run", "status", "stop"))
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--runtime", type=Path, default=RUNTIME_DIR)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--dest", type=Path)
    parser.add_argument("--process-existing", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "configure":
            if status(args.runtime)["active"]:
                raise ValueError("Stop background automation before changing configuration.")
            config = configure(args.source, args.dest, path=args.config,
                               process_existing=args.process_existing)
            print(f"Configured copy-only automation.\nSource: {config.source}\nDestination: {config.destination}")
        elif args.command == "start":
            load_config(args.config)
            if status(args.runtime)["active"]:
                print("Automation is already active.")
                return 0
            executable = Path(sys.executable).with_name("pythonw.exe") if os.name == "nt" else Path(sys.executable)
            process = subprocess.Popen(
                [str(executable), str(Path(__file__).resolve()), "run", "--config", str(args.config.resolve()),
                 "--runtime", str(args.runtime.resolve())],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if status(args.runtime)["active"]:
                    print("Background automation started. Use status to check readiness.")
                    return 0
                if process.poll() is not None:
                    break
                time.sleep(0.2)
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            raise RuntimeError("Quiet launch failed; inspect runtime/launcher-error.log and automation.log.")
        elif args.command == "run":
            return run(load_config(args.config), args.runtime)
        elif args.command == "status":
            print(json.dumps(status(args.runtime), indent=2))
        elif request_stop(args.runtime):
            deadline = time.monotonic() + 90
            while status(args.runtime)["active"] and time.monotonic() < deadline:
                time.sleep(0.2)
            if status(args.runtime)["active"]:
                raise RuntimeError("Still stopping; inspect automation.log. No process was forcibly killed.")
            print("Background automation stopped gracefully.")
        else:
            print("Background automation is already stopped.")
        return 0
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        if sys.stderr is not None:
            print(f"Automation error: {exc}", file=sys.stderr)
        else:
            args.runtime.mkdir(parents=True, exist_ok=True)
            with (args.runtime / "launcher-error.log").open("a", encoding="utf-8") as log:
                log.write(f"Automation error: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
