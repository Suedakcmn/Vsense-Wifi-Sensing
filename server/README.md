# Server

This folder contains the platform-side scripts for CSI replay and live processing.

## Files

- `requirements.txt`: Python dependencies
- `csi_utils.py`: Shared CSI helper functions
- `csi_replay.py`: Replays recorded CSI data as a stream
- `csi_live.py`: Receives CSI stream and computes live motion score

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r server/requirements.txt