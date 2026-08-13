import unittest

from vsense_binary import HEADER_SIZE, decode_csi_packet, encode_csi_packet


class VsenseBinaryTest(unittest.TestCase):
    def test_round_trip_preserves_existing_csi_fields(self):
        csi = [((index * 17) % 256) - 128 for index in range(256)]
        payload = encode_csi_packet(
            frame_count=66205,
            ts_us=785458597,
            rssi=-41,
            channel=1,
            csi=csi,
        )

        self.assertEqual(len(payload), HEADER_SIZE + 256)
        self.assertEqual(
            decode_csi_packet(payload),
            {
                "ts_us": 785458597,
                "frame_count": 66205,
                "rssi": -41,
                "channel": 1,
                "len": 256,
                "csi": csi,
            },
        )

    def test_rejects_invalid_magic(self):
        payload = bytearray(encode_csi_packet(
            frame_count=1,
            ts_us=2,
            rssi=-3,
            channel=1,
            csi=[-1, 1],
        ))
        payload[:4] = b"FAIL"

        with self.assertRaisesRegex(ValueError, "magic"):
            decode_csi_packet(payload)

    def test_rejects_unknown_version(self):
        payload = bytearray(encode_csi_packet(
            frame_count=1,
            ts_us=2,
            rssi=-3,
            channel=1,
            csi=[-1, 1],
        ))
        payload[4] = 2

        with self.assertRaisesRegex(ValueError, "version"):
            decode_csi_packet(payload)

    def test_rejects_truncated_or_trailing_data(self):
        payload = encode_csi_packet(
            frame_count=1,
            ts_us=2,
            rssi=-3,
            channel=1,
            csi=[-1, 1],
        )

        for malformed in (payload[:-1], payload + b"\x00"):
            with self.subTest(size=len(malformed)):
                with self.assertRaisesRegex(ValueError, "size mismatch"):
                    decode_csi_packet(malformed)

    def test_rejects_values_outside_signed_int8(self):
        with self.assertRaisesRegex(ValueError, "signed int8"):
            encode_csi_packet(
                frame_count=1,
                ts_us=2,
                rssi=-3,
                channel=1,
                csi=[128],
            )


if __name__ == "__main__":
    unittest.main()
