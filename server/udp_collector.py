import argparse
import json
import socket
import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 4444
BUFFER_SIZE = 4096


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Receive raw CSI JSON packets from an ESP32 RX node."
    )

    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"UDP address to listen on. Default: {DEFAULT_HOST}",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"UDP port to listen on. Default: {DEFAULT_PORT}",
    )

    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Print only valid JSON lines to stdout for piping into another script.",
    )

    parser.add_argument(
        "--record",
        type=Path,
        help="Optional JSONL file where all valid CSI packets will be recorded.",
    )

    parser.add_argument(
        "--required-len",
        type=int,
        choices=(128, 256),
        help="Ignore CSI frames whose length does not match this value.",
    )

    parser.add_argument(
        "--print-every",
        type=int,
        default=20,
        help="In normal mode, print one summary for every N packets. Default: 20.",
    )

    return parser.parse_args()


def open_record_file(path: Path | None) -> TextIO | None:
    if path is None:
        return None

    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("a", encoding="utf-8")


def validate_payload(payload: object) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "payload is not a JSON object"

    csi = payload.get("csi")
    declared_length = payload.get("len")

    if not isinstance(csi, list):
        return False, "missing or invalid csi list"

    if not isinstance(declared_length, int):
        return False, "missing or invalid len"

    if declared_length != len(csi):
        return False, (
            f"declared len={declared_length}, "
            f"but received {len(csi)} CSI samples"
        )

    return True, ""


def main() -> None:
    args = parse_args()

    if args.print_every < 1:
        raise SystemExit("--print-every must be at least 1")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    record_file = open_record_file(args.record)

    try:
        sock.bind((args.host, args.port))
    except OSError as exc:
        if record_file is not None:
            record_file.close()

        raise SystemExit(
            f"Could not bind UDP {args.host}:{args.port}: {exc}\n"
            f"Check the port with: lsof -nP -iUDP:{args.port}"
        ) from exc

    # In JSON-only mode, status messages must go to stderr.
    status_stream = sys.stderr if args.json_only else sys.stdout

    print(
        f"Collector listening on UDP {args.host}:{args.port}",
        file=status_stream,
        flush=True,
    )

    if args.record is not None:
        print(
            f"Recording valid packets to: {args.record}",
            file=status_stream,
            flush=True,
        )

    if args.required_len is not None:
        print(
            f"Accepting only CSI len={args.required_len}",
            file=status_stream,
            flush=True,
        )

    packet_count = 0
    accepted_count = 0
    invalid_count = 0
    filtered_count = 0

    try:
        while True:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            packet_count += 1

            now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            text = data.decode("utf-8", errors="replace")

            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                invalid_count += 1

                print(
                    f"[{now}] invalid JSON from {addr[0]}:{addr[1]}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
                continue

            is_valid, validation_error = validate_payload(payload)

            if not is_valid:
                invalid_count += 1

                print(
                    f"[{now}] invalid CSI packet from "
                    f"{addr[0]}:{addr[1]}: {validation_error}",
                    file=sys.stderr,
                    flush=True,
                )
                continue

            if (
                args.required_len is not None
                and payload["len"] != args.required_len
            ):
                filtered_count += 1
                continue

            accepted_count += 1
            json_line = json.dumps(payload, separators=(",", ":"))

            if record_file is not None:
                record_file.write(json_line + "\n")
                record_file.flush()

            if args.json_only:
                print(json_line, flush=True)
                continue

            if accepted_count % args.print_every == 0:
                csi = payload["csi"]

                print(
                    f"[{now}] "
                    f"packet={packet_count} "
                    f"accepted={accepted_count} "
                    f"invalid={invalid_count} "
                    f"filtered={filtered_count} "
                    f"from={addr[0]}:{addr[1]} "
                    f"node={payload.get('node_id')} "
                    f"frame={payload.get('frame_count')} "
                    f"ts_us={payload.get('ts_us')} "
                    f"len={payload.get('len')} "
                    f"rssi={payload.get('rssi')} "
                    f"channel={payload.get('channel')} "
                    f"length_ok=True "
                    f"csi_preview={csi[:8]}",
                    flush=True,
                )

    except KeyboardInterrupt:
        print(
            "\nCollector stopped. "
            f"received={packet_count} "
            f"accepted={accepted_count} "
            f"invalid={invalid_count} "
            f"filtered={filtered_count}",
            file=status_stream,
            flush=True,
        )

    finally:
        sock.close()

        if record_file is not None:
            record_file.close()


if __name__ == "__main__":
    main()
