import json
import socket
from datetime import datetime

HOST = "0.0.0.0"
PORT = 4444

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((HOST, PORT))

print(f"Collector listening on UDP {HOST}:{PORT}")

packet_count = 0

while True:
    data, addr = sock.recvfrom(4096)
    packet_count += 1

    text = data.decode("utf-8", errors="replace")
    now = datetime.now().strftime("%H:%M:%S.%f")[:-3]

    try:
        payload = json.loads(text)
        print(
            f"[{now}] packet={packet_count} "
            f"from={addr[0]} "
            f"node={payload.get('node_id')} "
            f"frame={payload.get('frame_count')} "
            f"len={payload.get('len')} "
            f"rssi={payload.get('rssi')} "
            f"channel={payload.get('channel')}"
        )
    except json.JSONDecodeError:
        print(f"[{now}] packet={packet_count} from={addr[0]} raw={text}")