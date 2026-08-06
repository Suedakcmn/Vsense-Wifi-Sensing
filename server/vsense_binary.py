"""Versioned binary payload contract for VSense CSI MQTT messages."""

import struct


MAGIC = b"VSCS"
VERSION = 1
FLAGS = 0
HEADER_FORMAT = "<4sBBHIQbBH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


def encode_csi_packet(*, frame_count, ts_us, rssi, channel, csi):
    """Encode one CSI frame using the VSCS v1 binary wire format."""
    csi_values = list(csi)
    if len(csi_values) > 0xFFFF:
        raise ValueError("CSI payload is too long")
    if any(not isinstance(value, int) or not -128 <= value <= 127 for value in csi_values):
        raise ValueError("CSI values must be signed int8 values")

    try:
        header = struct.pack(
            HEADER_FORMAT,
            MAGIC,
            VERSION,
            FLAGS,
            HEADER_SIZE,
            frame_count,
            ts_us,
            rssi,
            channel,
            len(csi_values),
        )
        payload = struct.pack(f"<{len(csi_values)}b", *csi_values)
    except struct.error as exc:
        raise ValueError(f"CSI metadata is out of range: {exc}") from exc
    return header + payload


def decode_csi_packet(payload):
    """Decode one VSCS v1 payload into the collector's existing CSI fields."""
    if len(payload) < HEADER_SIZE:
        raise ValueError("CSI binary payload is shorter than its header")

    (
        magic,
        version,
        flags,
        header_size,
        frame_count,
        ts_us,
        rssi,
        channel,
        csi_len,
    ) = struct.unpack_from(HEADER_FORMAT, payload)

    if magic != MAGIC:
        raise ValueError("CSI binary payload has an invalid magic value")
    if version != VERSION:
        raise ValueError(f"unsupported CSI binary version: {version}")
    if flags != FLAGS:
        raise ValueError(f"unsupported CSI binary flags: {flags}")
    if header_size != HEADER_SIZE:
        raise ValueError(f"unsupported CSI binary header size: {header_size}")

    expected_size = header_size + csi_len
    if len(payload) != expected_size:
        raise ValueError(
            f"CSI binary payload size mismatch: expected {expected_size}, got {len(payload)}"
        )

    csi = list(struct.unpack_from(f"<{csi_len}b", payload, header_size))
    return {
        "ts_us": ts_us,
        "frame_count": frame_count,
        "rssi": rssi,
        "channel": channel,
        "len": csi_len,
        "csi": csi,
    }
