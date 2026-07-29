# Multi-Node Firmware

This guide covers the VSense firmware profiles for one TX and two RX nodes.

## Profiles

| Profile | Node ID | Role | Build directory |
| --- | --- | --- | --- |
| `sdkconfig.defaults.rx_01` | `rx_01` | RX | `build-rx-01` |
| `sdkconfig.defaults.rx_02` | `rx_02` | RX | `build-rx-02` |
| `sdkconfig.defaults.tx_01` | `tx_01` | TX | `build-tx-01` |

Each profile must use its own build directory and generated `sdkconfig`.
This prevents settings from one node from leaking into another node.

## Before the Hardware Test

Record the following values without guessing:

| Value | Verified value |
| --- | --- |
| TX serial port | |
| RX-01 serial port | |
| RX-02 serial port | |
| TX station MAC | |
| RX-01 IPv4 address | |
| RX-02 IPv4 address | |
| Mac collector IPv4 address | |
| Wi-Fi channel | |

Reserve the RX addresses in the router's DHCP configuration when possible.
Unicast targets are not reliable if their addresses can change after reboot.

## Local Configuration

The committed profile fragments identify the node role and ID. Wi-Fi
credentials and environment-specific addresses must be reviewed locally
before flashing.

Open a profile-specific configuration with:

```bash
cd firmware
source ~/esp/esp-idf/export.sh

idf.py -B build-rx-01 \
  -D SDKCONFIG="$PWD/build-rx-01/sdkconfig" \
  -D 'SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.defaults.rx_01' \
  menuconfig
```

Use `VSense node configuration` to review:

- Wi-Fi SSID and password
- Wi-Fi channel
- collector IP and UDP port
- MQTT broker URI
- TX MAC filter
- TX target IP addresses

Repeat with `build-rx-02` and `sdkconfig.defaults.rx_02` for RX-02.

For TX-01:

```bash
idf.py -B build-tx-01 \
  -D SDKCONFIG="$PWD/build-tx-01/sdkconfig" \
  -D 'SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.defaults.tx_01' \
  menuconfig
```

Keep `Enable RX-02 target` disabled until RX-02 has a verified or
DHCP-reserved address.

## Build

RX-01:

```bash
idf.py -B build-rx-01 \
  -D SDKCONFIG="$PWD/build-rx-01/sdkconfig" \
  -D 'SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.defaults.rx_01' \
  build
```

RX-02:

```bash
idf.py -B build-rx-02 \
  -D SDKCONFIG="$PWD/build-rx-02/sdkconfig" \
  -D 'SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.defaults.rx_02' \
  build
```

TX-01:

```bash
idf.py -B build-tx-01 \
  -D SDKCONFIG="$PWD/build-tx-01/sdkconfig" \
  -D 'SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.defaults.tx_01' \
  build
```

Before flashing, verify the generated settings:

```bash
grep -E 'CONFIG_VSENSE_(NODE_ID|NODE_ROLE|RX_01_IP|RX_02|TX_MAC)' \
  build-rx-01/sdkconfig \
  build-rx-02/sdkconfig \
  build-tx-01/sdkconfig
```

## Flash

Replace each example port with the port recorded for that physical card.

RX-01:

```bash
idf.py -B build-rx-01 -p /dev/cu.usbmodemXXXX flash monitor
```

RX-02:

```bash
idf.py -B build-rx-02 -p /dev/cu.usbmodemYYYY flash monitor
```

TX-01:

```bash
idf.py -B build-tx-01 -p /dev/cu.usbmodemZZZZ flash monitor
```

Exit the monitor with `Ctrl+]`.

## Expected Logs

RX startup:

```text
Node ID: rx_01
Configured role: RX
Wi-Fi connected.
IP address: 192.168.128.x
CSI TX MAC filter enabled: AA:BB:CC:DD:EE:FF
CSI collection enabled.
```

TX startup:

```text
Node ID: tx_01
Configured role: TX
Target rx_01 configured: 192.168.128.x:3333
Target rx_02 configured: 192.168.128.y:3333
```

TX delivery:

```text
TX target=rx_01 cycles=100 sent=100 failed=0
TX target=rx_02 cycles=100 sent=100 failed=0
```

## Test Checklist

1. Start the collector and MQTT subscriber on the Mac.
2. Power RX-01 and confirm its node ID, IP, and online status.
3. Power RX-02 and confirm its node ID, IP, and online status.
4. Power TX-01 after both RX targets have been verified.
5. Confirm TX delivery counters increase for both targets.
6. Confirm CSI and health messages arrive under both node IDs.
7. Confirm each RX reports an acceptable CSI packet rate.
8. Disconnect RX-02 and verify its status becomes offline within five seconds.
9. Reconnect RX-02 and verify its status returns online.
10. Record packet rate, failures, drops, RSSI, channel, and CSI length.

Do not claim the multi-node task complete until both RX nodes receive CSI
simultaneously and the offline test passes.

## Single-RX Fallback

If RX-02 is unavailable or its address is not verified, disable
`Enable RX-02 target` in the TX configuration and rebuild TX-01. RX-01 will
continue to use the existing single-target path.
