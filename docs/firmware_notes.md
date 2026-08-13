# VSense Firmware Notes

## Current status

VSense is an implemented ESP-IDF firmware, not a skeleton. It currently
supports:

- configurable TX and RX roles;
- one TX sending approximately 100 UDP packets/s to one or two RX nodes;
- real ESP32-S3 CSI collection;
- configurable TX MAC filtering with mismatch diagnostics;
- queued raw CSI JSON forwarding over both UDP and MQTT;
- per-node MQTT online/offline state and health telemetry;
- separate RX-01, RX-02, and TX-01 build profiles;
- full-rate or explicitly decimated CSI forwarding.

See `firmware_design.md` for the architecture and
`multi_node_firmware.md` for profile-specific build, flash, and test commands.

## Build summary

Source ESP-IDF, then use a separate build directory and generated sdkconfig for
each node. For example:

```bash
cd firmware
source ~/esp/esp-idf/export.sh

idf.py -B build-rx-01 \
  -D SDKCONFIG="$PWD/build-rx-01/sdkconfig" \
  -D 'SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.defaults.rx_01' \
  build
```

Do not reuse one build directory across TX/RX profiles. Review Wi-Fi
credentials, collector/broker addresses, RX target IPs, and the physical TX MAC
before flashing.

## Current hardening defaults

- Wi-Fi power save: disabled.
- Global TX MAC filter default: disabled for first-boot diagnostics.
- RX-01/RX-02 deployment profiles: enabled for the verified TX-01 MAC
  `84:fc:e6:5e:50:24`.
- Global CSI length filter default: disabled until the active PHY is measured.
- RX-01 deployment profile: enabled at 256 raw CSI bytes after its canary.
- RX-02 deployment profile: disabled until an RX-02 canary verifies its CSI
  length distribution and transport health.
- Maximum CSI length: 384 bytes.
- Forwarding interval: every accepted frame (`N=1`).
- CSI queue length: 128.
- MQTT keepalive: 30 seconds.
- Health interval: 5 seconds.

These are safe code defaults, not a substitute for hardware verification.
Record the measured `csi_pps`, `csi_forwarded_pps`, queue depth, drops, transport
failures, RSSI, channel, and CSI length for both RX nodes before deployment.

## Historical pilot rate

The 27 July pilot deliberately forwarded every second accepted frame and
measured approximately 47–55 forwarded frames/s. That test validates `N=2`,
not the current `N=1` default. Run a new two-to-three-minute dual-RX test before
claiming approximately 100 CSI frames/s or using the rate for LD2450
synchronization.
