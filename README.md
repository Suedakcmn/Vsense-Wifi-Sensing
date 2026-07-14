# Vsense-Wifi-Sensing

**VSense** is a privacy-focused Wi-Fi sensing prototype that detects human presence and motion using Channel State Information (CSI) from ESP32-S3 devices.

Instead of relying on cameras, microphones, or wearable sensors, VSense analyzes how human movement affects Wi-Fi signals in an indoor environment. The project aims to build a real-time sensing system that can detect motion, estimate basic indoor zones, and trigger inactivity alerts.

## Overview

Wi-Fi signals are affected by reflection, absorption, and multipath changes when a person moves through a room. By collecting CSI data from ESP32-S3 receiver nodes and processing this data in real time, VSense can identify motion patterns without capturing any visual or audio information.

The long-term goal of the project is to explore privacy-preserving indoor monitoring, especially for use cases such as elderly care, smart homes, and ambient activity sensing.

## Key Features

* Real-time Wi-Fi CSI collection with ESP32-S3 devices
* Motion detection based on signal variation
* Multi-node sensing architecture
* MQTT-based data communication
* CSI data recording and replay support
* LD2450 mmWave radar integration for ground-truth comparison
* Python-based signal processing and machine learning pipeline
* Web dashboard for live visualization and alerts

## System Architecture

```text id="3vp6gi"
ESP32-S3 TX
    ↓
Wi-Fi packets
    ↓
ESP32-S3 RX Nodes
    ↓
CSI Stream
    ↓
MQTT / UDP Collector
    ↓
Python Processing & ML Pipeline
    ↓
FastAPI + WebSocket Backend
    ↓
React Dashboard
```

## Tech Stack

* **Embedded:** ESP32-S3, ESP-IDF, C
* **Communication:** MQTT, UDP, Mosquitto
* **Data Processing:** Python, NumPy, pandas, matplotlib
* **Machine Learning:** PyTorch
* **Backend:** FastAPI, WebSocket
* **Frontend:** React
* **Storage:** Parquet, SQLite
* **Ground Truth:** LD2450 mmWave Radar

## Use Case

VSense is designed for indoor environments where privacy is important. A possible use case is monitoring the activity of elderly people living alone. The system can detect unusual inactivity or movement changes and trigger alerts without using cameras or requiring the person to wear any device.

## Project Status

The project is currently under active development as a working prototype. The initial system focuses on live CSI collection, motion scoring, signal analysis, and basic dashboard visualization.

## Goal

The final goal is to deliver an end-to-end demo where human movement inside a room can be detected and visualized in real time, with inactivity alerts and radar-based validation.
