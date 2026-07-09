import argparse
import json
import time

import pandas as pd


def to_jsonable(value):
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def get_rssi(row):
    if "rssi" in row and pd.notna(row["rssi"]):
        return int(row["rssi"])

    candidates = []
    for col in ["rssi_a", "rssi_b", "rssi_c"]:
        if col in row and pd.notna(row[col]):
            candidates.append(int(row[col]))

    if candidates:
        return max(candidates)

    return 0


def get_payload(row):
    if "csi" in row and row["csi"] is not None:
        return "csi", to_jsonable(row["csi"])

    if "csi_amplitude" in row and row["csi_amplitude"] is not None:
        return "csi_amplitude", to_jsonable(row["csi_amplitude"])

    raise ValueError("Row has neither 'csi' nor 'csi_amplitude'.")


def main():
    parser = argparse.ArgumentParser(
        description="Replay recorded/provided CSI parquet data as JSON lines."
    )
    parser.add_argument("input", help="Path to recorded/provided CSI parquet file")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.05,
        help="Delay between frames in seconds",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of frames to replay",
    )
    parser.add_argument(
        "--node-id",
        default="public_rx_01",
        help="Default node_id if the dataset has no node_id column",
    )

    args = parser.parse_args()

    df = pd.read_parquet(args.input)

    if args.limit is not None:
        df = df.head(args.limit)

    for index, row in df.iterrows():
        payload_name, payload_value = get_payload(row)

        message = {
            "ts_us": int(row["ts_us"]) if "ts_us" in row and pd.notna(row["ts_us"]) else int(index),
            "node_id": str(row["node_id"]) if "node_id" in row and pd.notna(row["node_id"]) else args.node_id,
            "rssi": get_rssi(row),
            "label": str(row["label"]) if "label" in row and pd.notna(row["label"]) else "",
        }

        message[payload_name] = payload_value

        print(json.dumps(message), flush=True)
        time.sleep(args.delay)


if __name__ == "__main__":
    main()
