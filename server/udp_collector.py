import json
import socket
from datetime import datetime

HOST = "0.0.0.0"
PORT = 4444
BUFFER_SIZE = 4096


def main() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        sock.bind((HOST, PORT))
    except OSError as exc:
        raise SystemExit(
            f"Could not bind UDP {HOST}:{PORT}: {exc}\n"
            f"Check the port with: lsof -nP -iUDP:{PORT}"
        ) from exc

    print(f"Collector listening on UDP {HOST}:{PORT}")

    packet_count = 0

    try:
        while True:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            packet_count += 1

            now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            text = data.decode("utf-8", errors="replace")

            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                print(
                    f"[{now}] packet={packet_count} "
                    f"from={addr[0]}:{addr[1]} "
                    f"invalid_json={exc} "
                    f"raw={text}"
                )
                continue

            csi = payload.get("csi")

            if isinstance(csi, list):
                csi_sample_count = len(csi)
                csi_preview = csi[:8]
            else:
                csi_sample_count = 0
                csi_preview = None

            declared_length = payload.get("len")

            length_matches = (
                isinstance(declared_length, int)
                and isinstance(csi, list)
                and declared_length == len(csi)
            )

            if packet_count % 20 == 0:
                print(
                    f"[{now}] "
                    f"packet={packet_count} "
                    f"from={addr[0]}:{addr[1]} "
                    f"node={payload.get('node_id')} "
                    f"frame={payload.get('frame_count')} "
                    f"ts_us={payload.get('ts_us')} "
                    f"len={declared_length} "
                    f"rssi={payload.get('rssi')} "
                    f"channel={payload.get('channel')} "
                    f"csi_samples={csi_sample_count} "
                    f"length_ok={length_matches} "
                    f"csi_preview={csi_preview}"
                )

    except KeyboardInterrupt:
        print("\nCollector stopped.")

    finally:
        sock.close()


if __name__ == "__main__":
    main()