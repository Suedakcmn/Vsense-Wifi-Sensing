# ESP32-CSI-Tool Firmware Reference Notes

Reference repository:

StevenMHernandez/ESP32-CSI-Tool

## Why This Repository Is Useful

This repository is useful for understanding how ESP32 can be used to collect CSI data and how TX/RX-like Wi-Fi roles can be structured.

We should use it as a conceptual reference, not as code to copy directly.

## Files to Study

### active_sta/main/main.cc

This file is useful for understanding station/TX-like behavior.

Important ideas:

- ESP32 connects to a Wi-Fi network as a station.
- After connection, it can send packets.
- This is conceptually similar to the VSense TX role.
- VSense TX will eventually send packets at around 100 Hz.

Useful for:

- Wi-Fi station initialization
- Connection event handling
- Packet sender task structure

### active_ap/main/main.cc

This file is useful for understanding AP/RX-like behavior.

Important ideas:

- ESP32 can create an access point.
- Other stations can connect to it.
- CSI collection can be initialized on the receiving side.

Useful for:

- Access point setup
- Wi-Fi event handling
- Starting CSI collection after Wi-Fi initialization

### _components/csi_component.h

This is the most important firmware reference for RX.

Important ideas:

- CSI collection must be enabled.
- A CSI callback is registered.
- The callback receives CSI metadata and raw CSI bytes.
- RSSI, channel, MAC address, timestamp, and CSI buffer are available from the CSI data structure.
- Raw CSI can be interpreted as imag/real pairs.

Useful for:

- Designing VSense RX CSI callback
- Understanding wifi_csi_info_t
- Understanding raw CSI buffer handling
- Understanding amplitude and phase calculations

### _components/sockets_component.h

This file is useful for TX packet transmission.

Important ideas:

- UDP socket can be used to send packets.
- Target IP and port are configured.
- Packet rate can be controlled using delay.
- This is conceptually useful for VSense TX and RX UDP output.

Useful for:

- TX packet sender loop
- UDP send logic
- Packet rate control

## What We Can Reuse Conceptually

- TX/RX separation
- CSI callback pattern
- Raw CSI payload handling
- UDP packet sending pattern
- Packet rate control
- Metadata extraction idea

## What We Should Not Copy Directly

- Full repository structure
- ESP-IDF version-specific code without checking compatibility
- Serial/CSV-only design
- SD card related code
- Old API usage without checking ESP-IDF v5.3.2 compatibility

## VSense-Specific Direction

VSense should use this repository as a learning source, but the implementation should stay aligned with our architecture:

- ESP32-S3 target
- ESP-IDF v5.3.2
- RX CSI -> UDP/MQTT -> Mac collector
- Python analysis pipeline
- Later LD2450 ground truth
- Later web panel and inactivity alarm
