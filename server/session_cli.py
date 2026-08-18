"""Start, inspect, and stop reproducible VSense recording sessions."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


SCENARIOS = ("empty_room", "walking", "standing", "desk_work")
DEFAULT_DATASET_ROOT = Path("dataset-v1")
ACTIVE_FILE_NAME = ".active_session.json"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def timestamp_us():
    return time.time_ns() // 1_000


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def process_is_running(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def active_path(dataset_root):
    return dataset_root / ACTIVE_FILE_NAME


def load_active(dataset_root):
    path = active_path(dataset_root)
    if not path.exists():
        return None
    return read_json(path)


def make_session_id(now, location, scenario, repeat):
    safe_location = location.strip().lower().replace(" ", "_")
    if not safe_location or not all(
        character.isascii() and (character.isalnum() or character == "_")
        for character in safe_location
    ):
        raise ValueError("location must contain only ASCII letters, numbers, or underscores")
    return (
        f"{now.astimezone().strftime('%Y%m%d_%H%M%S')}_"
        f"{safe_location}_{scenario}_r{repeat:02d}"
    )


def count_lines(path):
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as stream:
        return sum(1 for line in stream if line.strip())


def start_session(args):
    dataset_root = args.dataset_root.resolve()
    dataset_root.mkdir(parents=True, exist_ok=True)
    active = load_active(dataset_root)
    if active and process_is_running(active["pid"]):
        raise SystemExit(
            f"A recording is already active: {active['session_id']} "
            f"(PID {active['pid']})"
        )
    if active:
        active_path(dataset_root).unlink()

    started = datetime.now(timezone.utc)
    session_id = make_session_id(started, args.location, args.scenario, args.repeat)
    session_dir = dataset_root / "sessions" / session_id
    if session_dir.exists():
        raise SystemExit(f"Session directory already exists: {session_dir}")
    session_dir.mkdir(parents=True)

    started_ts_us = timestamp_us()
    metadata = {
        "schema_version": 1,
        "session_id": session_id,
        "campaign": args.campaign,
        "scenario": args.scenario,
        "repeat": args.repeat,
        "operator": args.operator,
        "subject": args.subject,
        "location": args.location,
        "started_at": started.isoformat(),
        "started_collector_ts_us": started_ts_us,
        "ended_at": None,
        "duration_seconds": None,
        "mqtt_broker": {"host": args.host, "port": args.port},
        "devices": {
            "csi_nodes": args.csi_nodes,
            "ground_truth_nodes": args.ground_truth_nodes,
        },
        "files": {
            "csi": "csi.jsonl",
            "ground_truth": "ground_truth.jsonl",
            "telemetry": "telemetry.jsonl",
            "labels": "labels.json",
            "log": "session.log",
        },
        "status": "recording",
        "notes": args.notes,
    }
    write_json(session_dir / "metadata.json", metadata)

    collector_path = Path(__file__).with_name("mqtt_collector.py")
    command = [
        sys.executable,
        str(collector_path),
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--session-dir",
        str(session_dir),
        "--session-id",
        session_id,
        "--ground-truth-topic",
        args.ground_truth_topic,
    ]
    if args.username:
        command.extend(["--username", args.username])
    if args.password:
        command.extend(["--password", args.password])

    log_stream = (session_dir / "session.log").open("a", encoding="utf-8")
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=log_stream,
            start_new_session=True,
        )
    finally:
        log_stream.close()

    time.sleep(0.25)
    if process.poll() is not None:
        metadata["status"] = "failed_to_start"
        write_json(session_dir / "metadata.json", metadata)
        raise SystemExit(
            f"Collector could not start. Inspect {session_dir / 'session.log'}"
        )

    active_record = {
        "schema_version": 1,
        "session_id": session_id,
        "session_dir": str(session_dir),
        "pid": process.pid,
        "started_at": metadata["started_at"],
        "started_collector_ts_us": started_ts_us,
    }
    write_json(active_path(dataset_root), active_record)
    print(f"Recording started: {session_id}")
    print(f"Session directory: {session_dir}")
    print(f"Collector PID: {process.pid}")


def status_session(args):
    dataset_root = args.dataset_root.resolve()
    active = load_active(dataset_root)
    if active is None:
        print("No active recording.")
        return
    running = process_is_running(active["pid"])
    elapsed = max(0.0, time.time() - active["started_collector_ts_us"] / 1_000_000)
    session_dir = Path(active["session_dir"])
    print(f"Session: {active['session_id']}")
    print(f"Collector: {'running' if running else 'not running'} (PID {active['pid']})")
    print(f"Elapsed: {elapsed:.1f} seconds")
    print(f"CSI rows: {count_lines(session_dir / 'csi.jsonl')}")
    print(f"Ground-truth rows: {count_lines(session_dir / 'ground_truth.jsonl')}")
    print(f"Telemetry rows: {count_lines(session_dir / 'telemetry.jsonl')}")


def stop_process(pid, timeout=5.0):
    if not process_is_running(pid):
        return
    os.killpg(pid, signal.SIGINT)
    deadline = time.monotonic() + timeout
    while process_is_running(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    if process_is_running(pid):
        os.killpg(pid, signal.SIGTERM)


def stop_session(args):
    dataset_root = args.dataset_root.resolve()
    active = load_active(dataset_root)
    if active is None:
        raise SystemExit("No active recording to stop.")

    stop_process(active["pid"])
    ended_at = utc_now()
    ended_ts_us = timestamp_us()
    session_dir = Path(active["session_dir"])
    metadata_path = session_dir / "metadata.json"
    metadata = read_json(metadata_path)
    metadata.update({
        "ended_at": ended_at,
        "ended_collector_ts_us": ended_ts_us,
        "duration_seconds": round(
            (ended_ts_us - active["started_collector_ts_us"]) / 1_000_000,
            3,
        ),
        "row_counts": {
            "csi": count_lines(session_dir / "csi.jsonl"),
            "ground_truth": count_lines(session_dir / "ground_truth.jsonl"),
            "telemetry": count_lines(session_dir / "telemetry.jsonl"),
        },
        "status": "completed",
    })
    write_json(metadata_path, metadata)
    write_json(session_dir / "labels.json", {
        "schema_version": 1,
        "session_id": active["session_id"],
        "segments": [{
            "label": metadata["scenario"],
            "start_collector_ts_us": active["started_collector_ts_us"],
            "end_collector_ts_us": ended_ts_us,
        }],
    })
    active_path(dataset_root).unlink()
    print(f"Recording stopped: {active['session_id']}")
    print(f"Duration: {metadata['duration_seconds']:.1f} seconds")
    print(
        f"Rows: CSI={metadata['row_counts']['csi']}, "
        f"ground_truth={metadata['row_counts']['ground_truth']}, "
        f"telemetry={metadata['row_counts']['telemetry']}"
    )


def build_parser():
    parser = argparse.ArgumentParser(description="VSense recording session controller")
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Start a recording session")
    start.add_argument("--scenario", required=True, choices=SCENARIOS)
    start.add_argument("--repeat", required=True, type=int, choices=range(1, 100))
    start.add_argument("--operator", required=True)
    start.add_argument("--subject", required=True)
    start.add_argument("--location", required=True)
    start.add_argument("--campaign", default="week5_dataset_v1")
    start.add_argument("--notes", default="")
    start.add_argument("--host", default="127.0.0.1")
    start.add_argument("--port", type=int, default=1883)
    start.add_argument("--username")
    start.add_argument("--password")
    start.add_argument("--ground-truth-topic", default="vsense/gt/+")
    start.add_argument("--csi-nodes", nargs="+", default=["node_01", "node_02"])
    start.add_argument("--ground-truth-nodes", nargs="+", default=["ld2450_01"])
    start.set_defaults(handler=start_session)

    status = subparsers.add_parser("status", help="Show active recording status")
    status.set_defaults(handler=status_session)

    stop = subparsers.add_parser("stop", help="Stop the active recording")
    stop.set_defaults(handler=stop_session)
    return parser


def main():
    args = build_parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
