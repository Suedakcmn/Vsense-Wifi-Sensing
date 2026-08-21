import argparse
import csv
import json
import queue
import sys
import threading
import math
import time
import traceback
from collections import deque
from datetime import datetime

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import numpy as np

try:
    import paho.mqtt.client as mqtt
except ImportError:
    import paho.mqtt.client as mqtt

try:
    from csi_utils import csi_to_amplitude
except ImportError:
    # csi_utils bulunamazsa varsayılan karmaşık sayı genlik dönüşümü
    def csi_to_amplitude(csi_raw):
        csi_np = np.array(csi_raw, dtype=float)
        if len(csi_np) % 2 != 0:
            csi_np = csi_np[:-1]
        complex_csi = csi_np[0::2] + 1j * csi_np[1::2]
        return np.abs(complex_csi)

# ---------------------------------------------------------
# 1. SCALAR FİLTRELER VE HİBRİT SKOR
# ---------------------------------------------------------
class HampelFilterScalar:
    def __init__(self, window_size=7, threshold=5.0):
        self.window = deque(maxlen=window_size)
        self.threshold = threshold
        self.consistency_constant = 1.4826

    def process(self, value):
        self.window.append(value)
        if len(self.window) < 3: return value
        window_array = np.array(self.window)
        median = np.median(window_array)
        mad = np.median(np.abs(window_array - median))
        if mad > 1e-6:
            deviation = abs(value - median) / mad
            if deviation > (self.threshold * self.consistency_constant):
                return float(median)
        return float(value)

class LowPassFilterScalar:
    def __init__(self, cutoff_hz=11.0, sample_rate_hz=100.0):
        wc = math.tan(math.pi * cutoff_hz / sample_rate_hz)
        k = 1.0 + wc
        self.b0 = wc / k
        self.a1 = (wc - 1.0) / k
        self.x_prev = 0.0
        self.y_prev = 0.0

    def process(self, x):
        y = self.b0 * x + self.b0 * self.x_prev - self.a1 * self.y_prev
        self.x_prev = x
        self.y_prev = y
        return float(y)

class HybridMotionScore:
    def __init__(self, mvs_window=30, ma_window=20, mvs_weight=0.7):
        self.mvs_window = mvs_window
        self.ma_window = ma_window
        self.mvs_weight = mvs_weight
        self.ma_weight = 1.0 - mvs_weight

        self.turbulence_buffer = deque(maxlen=mvs_window)
        self.diff_buffer = deque(maxlen=ma_window)

    def process(self, diff_value, filt_turbulence):
        self.turbulence_buffer.append(filt_turbulence)
        mvs_score = 0.0
        if len(self.turbulence_buffer) >= 3:
            arr = np.array(self.turbulence_buffer)
            mvs_score = float(np.var(arr)) * 1000.0

        self.diff_buffer.append(diff_value)
        ma_score = 0.0
        if len(self.diff_buffer) >= 2:
            ma_score = float(np.mean(self.diff_buffer)) * 1000.0

        score = self.mvs_weight * mvs_score + self.ma_weight * ma_score
        return score, mvs_score, ma_score

# ---------------------------------------------------------
# 2. TEMEL YARDIMCI FONKSİYONLAR
# ---------------------------------------------------------
def extract_amplitude(item):
    if "amplitude" in item:
        amplitude = np.asarray(item["amplitude"], dtype=np.float32)
    elif "csi_amplitude" in item:
        amplitude = np.asarray(item["csi_amplitude"], dtype=np.float32)
    elif "csi_raw" in item:
        amplitude = np.asarray(csi_to_amplitude(item["csi_raw"]), dtype=np.float32)
    elif "csi" in item:
        amplitude = np.asarray(csi_to_amplitude(item["csi"]), dtype=np.float32)
    else:
        raise ValueError("Pakette 'csi', 'csi_raw' veya 'amplitude' bulunamadi.")
    
    if amplitude.ndim != 1:
        raise ValueError("CSI genliği tek boyutlu olmalıdır.")
    return amplitude

def preprocess_lltf_amplitude(amplitude, edge_trim=4):
    if len(amplitude) >= 64:
        amplitude = amplitude[:64]

    PILOT_INDICES = {11, 25, 39, 53}
    valid_mask = ~np.isin(np.arange(len(amplitude)), list(PILOT_INDICES))
    amplitude = amplitude[valid_mask]

    if edge_trim > 0 and len(amplitude) > 2 * edge_trim:
        amplitude = amplitude[edge_trim:-edge_trim]

    median = float(np.median(amplitude))
    mad = float(np.median(np.abs(amplitude - median)))
    if mad > 1e-6:
        robust_z = np.abs(amplitude - median) / (1.4826 * mad)
        amplitude = np.where(robust_z > 5.0, median, amplitude)

    return amplitude

# ---------------------------------------------------------
# 3. VERİ İLETİMİ (MQTT VE DOSYA OKUYUCU)
# ---------------------------------------------------------
def file_listener(file_path, message_queue, delay_sec=0.01, loop=False):
    print(f"[{file_path}] dosyasından veri okunuyor...", file=sys.stderr)
    while True:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                first_char = f.read(1)
                f.seek(0)
                
                if first_char == '[':
                    data = json.load(f)
                    for item in data:
                        message_queue.put(item)
                        if delay_sec > 0:
                            time.sleep(delay_sec)
                else:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            item = json.loads(line)
                            message_queue.put(item)
                            if delay_sec > 0:
                                time.sleep(delay_sec)
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            print(f"Dosya okuma hatası: {e}", file=sys.stderr)
            break
        
        if not loop:
            print("Dosya okuma tamamlandı.", file=sys.stderr)
            break

def mqtt_listener(message_queue):
    def on_message(client, userdata, msg):
        try:
            line = msg.payload.decode("utf-8", errors="replace").strip()
            if not line: return
            
            message = json.loads(line)
            if "csi" not in message and "csi_raw" not in message: return
            
            message_queue.put_nowait(message)
            
        except json.JSONDecodeError:
            print(f"[⚠️ JSON HATASI] Gelen veri JSON değil! İlk 20 bayt: {msg.payload[:20]}", file=sys.stderr)
        except queue.Full:
            pass
        except Exception as e:
            print(f"[MQTT Listener Error]: {e}", file=sys.stderr)

    client = mqtt.Client()
    client.on_message = on_message
    broker_ip = "192.168.128.167"
    try:
        client.connect(broker_ip, 1883, 60)
        client.subscribe("vsense/#")
        print("MQTT Subscribed! Dinleniyor...", file=sys.stderr)
        client.loop_forever()
    except Exception as exc:
        print(f"MQTT Error: {exc}", file=sys.stderr)

# ---------------------------------------------------------
# 4. ANA PROGRAM
# ---------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(description="Live/Offline CSI Motion Tracker")
    parser.add_argument("--file", type=str, default=None, help="Test edilecek JSON/JSONL dosya yolu")
    parser.add_argument("--speed", type=float, default=0.01, help="Dosya okuma gecikmesi (sn)")
    parser.add_argument("--loop", action="store_true", help="Dosya bitince otomatik başa dön")
    parser.add_argument("--edge-trim", type=int, default=4)
    parser.add_argument("--auto-multiplier", type=float, default=1.3)
    parser.add_argument("--mvs-window", type=int, default=30)
    parser.add_argument("--ma-window", type=int, default=20)
    parser.add_argument("--mvs-weight", type=float, default=0.7)
    parser.add_argument("--hampel-window", type=int, default=7)
    parser.add_argument("--cutoff-hz", type=float, default=11.0)
    parser.add_argument("--sample-rate", type=float, default=100.0)
    parser.add_argument("--history", type=int, default=300)
    parser.add_argument("--interval-ms", type=int, default=100)
    parser.add_argument("--start-count", type=int, default=3)
    parser.add_argument("--stop-count", type=int, default=10)
    parser.add_argument("--csv-output", type=str, default=None)
    return parser.parse_args()

def main():
    args = parse_args()
    message_queue = queue.Queue(maxsize=1000)

    stats = {
        "queue_full_count": 0,
        "processed_frames": 0,
        "skipped_frames": 0,
        "start_time": time.time(),
        "true_sampling_rate": 0.0
    }

    if args.file:
        threading.Thread(target=file_listener, args=(args.file, message_queue, args.speed, args.loop), daemon=True).start()
    else:
        threading.Thread(target=mqtt_listener, args=(message_queue,), daemon=True).start()

    hampel = HampelFilterScalar(args.hampel_window, 5.0)
    lowpass = LowPassFilterScalar(args.cutoff_hz, args.sample_rate)
    hybrid = HybridMotionScore(args.mvs_window, args.ma_window, args.mvs_weight)

    frame_history = deque(maxlen=args.history)
    hist_score = deque(maxlen=args.history)
    hist_mvs = deque(maxlen=args.history)
    hist_ma = deque(maxlen=args.history)
    
    fps_timestamps = deque(maxlen=30)

    baseline_scores = []
    thresh_calibrated = False
    thresh = 0.5 

    frame_count = 0
    is_moving = False
    high_count, low_count = 0, 0
    prev_filt = None
    active_subcarrier_count = 0

    csv_file, csv_writer = None, None
    if args.csv_output:
        csv_file = open(args.csv_output, 'w', newline='')
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(['timestamp', 'frame', 'rssi', 'score', 'thresh', 'is_moving', 'fps'])

    fig, (ax_score, ax_debug) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={"height_ratios": [3, 1]})
    
    score_line, = ax_score.plot([], [], label="Hybrid Score (MVS+MA)", color="blue", linewidth=2.0)
    mvs_line, = ax_score.plot([], [], label="MVS Component", color="red", alpha=0.5, linestyle=':')
    ma_line, = ax_score.plot([], [], label="MA Component", color="black", alpha=0.6, linestyle='-.')
    tline, = ax_score.plot([], [], linestyle="--", color="green", alpha=0.8, label="Dynamic Threshold")
    
    ax_score.set_title("CSI Motion Score Tracker", fontweight="bold")
    ax_score.set_ylabel("Score (x1000)")
    ax_score.legend(loc="upper left", fontsize=9, ncol=4)
    ax_score.grid(True, linestyle='--', alpha=0.5)

    status_text = ax_score.text(0.02, 0.85, "Status: WAITING", transform=ax_score.transAxes, 
                                bbox=dict(boxstyle="round", facecolor="white", alpha=0.8))

    debug_text = ax_debug.text(
        0.02, 0.95, "", transform=ax_debug.transAxes,
        verticalalignment="top", fontsize=10, fontfamily="monospace",
        bbox=dict(boxstyle="round", facecolor="lightgray", alpha=0.8)
    )
    ax_debug.set_xlim(0, 1)
    ax_debug.set_ylim(0, 1)
    ax_debug.axis("off")

    def process_new_messages():
        nonlocal frame_count, prev_filt, thresh, thresh_calibrated, is_moving, high_count, low_count, active_subcarrier_count

        latest_score = None
        latest_rssi = None
        current_fps = 0.0

        while True:
            try:
                item = message_queue.get_nowait()
            except queue.Empty:
                break

            try:
                raw_amplitude = extract_amplitude(item)
                latest_rssi = item.get("rssi")

                cleaned_amps = preprocess_lltf_amplitude(raw_amplitude, args.edge_trim)
                active_subcarrier_count = len(cleaned_amps)

                mean_val = float(np.mean(cleaned_amps))
                std_val = float(np.std(cleaned_amps))
                raw_turb = (std_val / mean_val) if mean_val > 1e-6 else 0.0

                filt_turb = lowpass.process(hampel.process(raw_turb))

                if prev_filt is None:
                    prev_filt = filt_turb
                    continue

                diff_val = abs(filt_turb - prev_filt)
                prev_filt = filt_turb

                score, mvs_val, ma_val = hybrid.process(diff_val, filt_turb)

                elapsed_time = time.time() - stats["start_time"]
                
                if not thresh_calibrated:
                    if elapsed_time >= 5.0 or (args.file and frame_count >= 50):
                        baseline_scores.append(score)
                        if len(baseline_scores) >= 30:
                            p95 = float(np.percentile(baseline_scores, 95))
                            thresh = max(p95 * args.auto_multiplier, 0.05) 
                            thresh_calibrated = True

                if thresh_calibrated:
                    if score > thresh: 
                        high_count += 1; low_count = 0
                    else: 
                        low_count += 1; high_count = 0

                    if not is_moving and high_count >= args.start_count: is_moving = True
                    elif is_moving and low_count >= args.stop_count: is_moving = False

                frame_count += 1
                stats["processed_frames"] += 1
                frame_history.append(frame_count)

                hist_score.append(score)
                hist_mvs.append(mvs_val)
                hist_ma.append(ma_val)
                
                fps_timestamps.append(time.time())
                if len(fps_timestamps) > 1:
                    current_fps = len(fps_timestamps) / (fps_timestamps[-1] - fps_timestamps[0])

                if csv_writer:
                    csv_writer.writerow([
                        datetime.now().isoformat(), frame_count, latest_rssi or '',
                        score, thresh, int(is_moving), f"{current_fps:.1f}"
                    ])

                latest_score = score

            except Exception as e:
                stats["skipped_frames"] += 1
                continue  

        return latest_score, current_fps

    def update(_frame):
        latest_score, current_fps = process_new_messages()

        if not frame_history:
            return score_line, mvs_line, ma_line, tline, status_text, debug_text

        x = list(frame_history)
        score_line.set_data(x, list(hist_score))
        mvs_line.set_data(x, list(hist_mvs))
        ma_line.set_data(x, list(hist_ma))
        tline.set_data(x, [thresh] * len(x))

        x_min = max(0, x[-1] - args.history)
        x_max = max(args.history, x[-1] + 1)
        ax_score.set_xlim(x_min, x_max)

        if hist_score:
            y_max = max(max(hist_score), max(hist_ma), thresh, 0.1)
            ax_score.set_ylim(0, y_max * 1.5)

        if latest_score is not None:
            elapsed = time.time() - stats["start_time"]
            if not thresh_calibrated:
                status_text.set_text(f"[Frame: {frame_count}] CALIBRATING | Score: {latest_score:.2f}")
                status_text.set_color("black")
                status_text.set_bbox(dict(boxstyle="round", facecolor="orange", alpha=0.8))
            else:
                status_str = "HAREKET" if is_moving else "STILL"
                status_text.set_text(f"[Frame: {frame_count}] Status: {status_str} | Score: {latest_score:.2f} | Thresh: {thresh:.2f}")
                status_text.set_color("white" if is_moving else "black")
                status_text.set_bbox(dict(boxstyle="round", facecolor="red" if is_moving else "white", alpha=0.8))

        debug_text.set_text(
            f"Mode: {'OFFLINE FILE' if args.file else 'LIVE MQTT'}\n"
            f"Software Processing FPS: {current_fps:.1f} FPS\n"
            f"Queue: {message_queue.qsize()}/1000 | Skipped: {stats['skipped_frames']}\n"
            f"Calibrated: {thresh_calibrated} | Active Subcarriers Count: {active_subcarrier_count}"
        )

        return score_line, mvs_line, ma_line, tline, status_text, debug_text

    animation = FuncAnimation(fig, update, interval=args.interval_ms, cache_frame_data=False)
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()