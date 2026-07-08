import argparse
import json
import time

import pandas as pd


def main():
    parser = argparse.ArgumentParser(
        description="Replay CSI parquet data as JSON lines."
    )
    parser.add_argument("input", help="Path to fake CSI parquet file")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.05,
        help="Delay between frames in seconds",
    )
    args = parser.parse_args()

    df = pd.read_parquet(args.input)

    for _, row in df.iterrows():
        message = {
            "ts_us": int(row["ts_us"]),
            "node_id": row["node_id"],
            "rssi": int(row["rssi"]),
            "csi": row["csi"],
            "label": row.get("label", ""),
        }

        print(json.dumps(message))
        time.sleep(args.delay)


if __name__ == "__main__":
    main()