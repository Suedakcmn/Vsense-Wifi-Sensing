"""Launch the complete VSense live inference and dashboard pipeline."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from activity_model import ModelContractError
from validate_model_artifact import validate_artifact


def build_commands(args, python_executable: str) -> list[list[str]]:
    collector = [
        python_executable,
        "server/mqtt_collector.py",
        "--host",
        args.mqtt_host,
        "--port",
        str(args.mqtt_port),
        "--client-id",
        args.client_id,
        "--offline-timeout",
        str(args.offline_timeout),
    ]
    if args.mqtt_username:
        collector.extend(["--username", args.mqtt_username])
        if os.environ.get(args.mqtt_password_env):
            collector.extend(["--password-env", args.mqtt_password_env])

    predictor = [
        python_executable,
        "server/live_activity_predictor.py",
        "--artifact-dir",
        str(args.artifact_dir),
    ]
    if args.model_version:
        predictor.extend(["--model-version", args.model_version])

    alarm = [
        python_executable,
        "server/inactivity_alarm.py",
        "--threshold-seconds",
        str(args.inactivity_seconds),
    ]
    dashboard = [
        python_executable,
        "server/dashboard_api.py",
        "--host",
        args.web_host,
        "--port",
        str(args.web_port),
        "--max-events",
        str(args.max_events),
        "--static-dir",
        str(args.static_dir),
    ]
    return [collector, predictor, alarm, dashboard]


def validate_paths(args):
    try:
        validation = validate_artifact(
            args.artifact_dir,
            require_final_classes=not args.allow_legacy_artifact,
        )
    except (ModelContractError, OSError, ValueError) as exc:
        raise SystemExit(f"invalid model artifact: {exc}") from exc
    for warning in validation["warnings"]:
        print(f"Model artifact warning: {warning}", file=sys.stderr)
    if not (args.static_dir / "index.html").is_file():
        raise SystemExit(
            f"dashboard build not found: {args.static_dir / 'index.html'}; "
            "run `npm --prefix web install` and `npm --prefix web run build`"
        )


def start_pipeline(commands: list[list[str]]) -> list[subprocess.Popen]:
    processes = []
    previous_stdout = None
    try:
        for index, command in enumerate(commands):
            is_last = index == len(commands) - 1
            process = subprocess.Popen(
                command,
                stdin=previous_stdout,
                stdout=None if is_last else subprocess.PIPE,
                stderr=None,
                start_new_session=True,
                text=False,
            )
            if previous_stdout is not None:
                previous_stdout.close()
            processes.append(process)
            previous_stdout = process.stdout
        return processes
    except Exception:
        stop_pipeline(processes)
        raise


def stop_pipeline(processes: list[subprocess.Popen], timeout: float = 5.0):
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + timeout
    for process in reversed(processes):
        remaining = max(0.0, deadline - time.monotonic())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def monitor_pipeline(processes: list[subprocess.Popen], poll_interval: float = 0.2):
    while True:
        for index, process in enumerate(processes):
            return_code = process.poll()
            if return_code is not None:
                if index == len(processes) - 1 and return_code == 0:
                    return
                raise RuntimeError(
                    f"pipeline stage {index + 1} exited with code {return_code}"
                )
        time.sleep(poll_interval)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mqtt-host", default="127.0.0.1")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--mqtt-username")
    parser.add_argument("--mqtt-password-env", default="VSENSE_MQTT_PASSWORD")
    parser.add_argument("--client-id", default="vsense-dashboard-collector")
    parser.add_argument("--offline-timeout", type=float, default=5.0)
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path("dataset-v1/models/baseline_v1"),
    )
    parser.add_argument("--model-version")
    parser.add_argument(
        "--allow-legacy-artifact",
        action="store_true",
        help="allow the five-class integration baseline; never use for final evaluation",
    )
    parser.add_argument("--inactivity-seconds", type=float, default=300.0)
    parser.add_argument("--web-host", default="127.0.0.1")
    parser.add_argument("--web-port", type=int, default=8000)
    parser.add_argument("--max-events", type=int, default=100)
    parser.add_argument("--static-dir", type=Path, default=Path("web/dist"))
    return parser.parse_args()


def main():
    args = parse_args()
    validate_paths(args)
    commands = build_commands(args, sys.executable)
    print(
        f"Starting VSense dashboard at http://{args.web_host}:{args.web_port}",
        file=sys.stderr,
    )
    processes = start_pipeline(commands)
    try:
        monitor_pipeline(processes)
    except KeyboardInterrupt:
        print("\nStopping VSense dashboard pipeline.", file=sys.stderr)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        stop_pipeline(processes)


if __name__ == "__main__":
    main()
