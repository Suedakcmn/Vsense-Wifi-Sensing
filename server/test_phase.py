import argparse
import json
import queue
import sys
import threading
import time
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from scipy.ndimage import median_filter, uniform_filter
from scipy.signal import butter, lfilter, lfilter_zi
from collections import deque


# ---------------------------------------------------------
# ZAMAN BAZLI (TEMPORAL) FİLTRE SINIFI (Hampel + Butterworth)
# ---------------------------------------------------------
class TemporalCSIFilter:
    def __init__(self, hampel_window=15, hampel_n_sigma=3.0, cutoff_hz=3.0, fs=100.0, butter_order=3):
        self.hampel_window = hampel_window
        self.hampel_n_sigma = hampel_n_sigma

        # Butterworth katsayıları
        nyq = 0.5 * fs
        normal_cutoff = cutoff_hz / nyq
        self.b, self.a = butter(butter_order, normal_cutoff, btype='low', analog=False)
        
        self.zi = None
        self.history = deque(maxlen=hampel_window)
        self.last_length = 0

    def process(self, current_frame):
        current_frame = np.asarray(current_frame, dtype=np.float32)

        if len(current_frame) != self.last_length:
            self.history.clear()
            self.zi = None
            self.last_length = len(current_frame)

        self.history.append(current_frame)
        if len(self.history) == self.hampel_window:
            hist_array = np.array(self.history)
            median = np.median(hist_array, axis=0)
            mad = np.median(np.abs(hist_array - median), axis=0)
            threshold = self.hampel_n_sigma * 1.4826 * mad + 1e-6
            outlier_mask = np.abs(current_frame - median) > threshold
            clean_frame = np.where(outlier_mask, median, current_frame)
        else:
            clean_frame = current_frame

        if self.zi is None:
            zi_base = lfilter_zi(self.b, self.a)
            self.zi = np.outer(zi_base, clean_frame)

        filtered_frame, self.zi = lfilter(self.b, self.a, [clean_frame], axis=0, zi=self.zi)
        return filtered_frame[0]


# ---------------------------------------------------------
# DOSYA OKUYUCU (OFFLINE FILE READER)
# ---------------------------------------------------------
def file_listener(file_path, message_queue, delay_sec=0.05, loop=False):
    """
    JSON / JSONL dosyasını okuyarak verileri kuyruğa (Queue) besler.
    """
    print(f"[{file_path}] dosyası okunuyor (Sadece Kanal 1)...", file=sys.stderr)
    
    while True:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                first_char = f.read(1)
                f.seek(0)
                
                # Standart JSON dizisi [...] şeklinde mi, yoksa JSON Lines (satır satır) mı?
                if first_char == '[':
                    data = json.load(f)
                    for item in data:
                        # SADECE KANAL 1 OLANLARI AL (Integer veya String olabilir diye iki durumu da kontrol ediyoruz)
                        if "csi" in item and (item.get("channel") == 1 or item.get("channel") == "1"):
                            message_queue.put({
                                "csi_raw": item["csi"],
                                "rssi": item.get("rssi", None)
                            })
                            time.sleep(delay_sec)
                else:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            item = json.loads(line)
                            # SADECE KANAL 1 OLANLARI AL
                            if "csi" in item and (item.get("channel") == 1 or item.get("channel") == "1"):
                                message_queue.put({
                                    "csi_raw": item["csi"],
                                    "rssi": item.get("rssi", None)
                                })
                                time.sleep(delay_sec)
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            print(f"Dosya okuma hatası: {e}", file=sys.stderr)
            break
        
        if not loop:
            print("Dosya okuması tamamlandı.", file=sys.stderr)
            break


# ---------------------------------------------------------
# ESP32-S3 HT-LTF DOKÜMANTASYONUNA GÖRE PİLOT VE DC/NULL FİLTRESİ
# ---------------------------------------------------------
def get_ignore_indices(num_subcarriers=64):
    pilots = {6, 20, 34, 48}
    dc_nulls = {27, 28}
    edges = {0, 1, 2, 3, 60, 61, 62, 63}
    return pilots.union(dc_nulls).union(edges)


# ---------------------------------------------------------
# MAKALEDEKİ SANITIZATION FONKSİYONLARI 
# ---------------------------------------------------------
def sanitize_phase_makale(valid_indices, raw_phase, unwrapped_phase, median_size=3, uniform_size=3):
    unwrapped = unwrapped_phase
    med_filtered = median_filter(unwrapped, size=median_size)
    filtered = uniform_filter(med_filtered, size=uniform_size)

    coeffs = np.polyfit(valid_indices, filtered, 1)
    trend = np.polyval(coeffs, valid_indices)
    sanitized = filtered - trend

    return {
        'raw': raw_phase,
        'unwrapped': unwrapped,
        'filtered': filtered,
        'sanitized': sanitized,
        'trend': trend
    }


# ---------------------------------------------------------
# ANA PROGRAM VE GRAFİK (6 PANEL)
# ---------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Offline CSI Viewer (File Analysis Mode)")
    parser.add_argument("--file", type=str, required=True, help="Incelenecek JSON/JSONL dosya yolu")
    parser.add_argument("--interval-ms", type=int, default=50, help="Grafik yenileme hizi (ms)")
    parser.add_argument("--speed", type=float, default=0.05, help="Kareler arasi bekleme suresi (saniye)")
    parser.add_argument("--loop", action="store_true", help="Dosya bitince bastan tekrar baslat")
    args = parser.parse_args()

    message_queue = queue.Queue(maxsize=1000)
    
    # Arka planda dosya okuma baslatiliyor
    threading.Thread(
        target=file_listener, 
        args=(args.file, message_queue, args.speed, args.loop), 
        daemon=True
    ).start()

    amp_temporal_filter = TemporalCSIFilter(cutoff_hz=3.0, fs=100.0)
    phase_temporal_filter = TemporalCSIFilter(cutoff_hz=3.0, fs=100.0)

    fig = plt.figure(figsize=(16, 10))
    gs = fig.add_gridspec(2, 3, hspace=0.3, wspace=0.25)

    ax_amp = fig.add_subplot(gs[0, 0])
    ax_phase_raw = fig.add_subplot(gs[0, 1])
    ax_phase_unwrap = fig.add_subplot(gs[0, 2])
    ax_raw_amp = fig.add_subplot(gs[1, 0]) # Motion Score yerine Raw Amplitude
    ax_phase_filter = fig.add_subplot(gs[1, 1])
    ax_phase_final = fig.add_subplot(gs[1, 2])

    fig.canvas.manager.set_window_title("CSI Viewer: Offline File Mode")

    line_amp, = ax_amp.plot([], [], color="blue", linewidth=2)
    ax_amp.set_title("(a) Amplitude (RSSI Norm + Butterworth)", fontweight="bold")
    ax_amp.set_ylabel("Amplitude")
    ax_amp.grid(True, linestyle="--", alpha=0.6)

    line_raw, = ax_phase_raw.plot([], [], color="red", linewidth=2)
    ax_phase_raw.set_title("(b) Original Phase (Wrapped)", fontweight="bold")
    ax_phase_raw.set_ylabel("Phase (Rad)")
    ax_phase_raw.grid(True, linestyle="--", alpha=0.6)

    line_unwrap, = ax_phase_unwrap.plot([], [], color="orange", linewidth=2)
    ax_phase_unwrap.set_title("(c) Phase after Unwrapping", fontweight="bold")
    ax_phase_unwrap.set_ylabel("Phase (Rad)")
    ax_phase_unwrap.grid(True, linestyle="--", alpha=0.6)

    # RAW AMPLITUDE ÇİZGİSİ
    line_raw_amp, = ax_raw_amp.plot([], [], color="purple", linewidth=2)
    ax_raw_amp.set_title("(d) Raw Amplitude", fontweight="bold")
    ax_raw_amp.set_xlabel("Subcarrier Index")
    ax_raw_amp.set_ylabel("Amplitude")
    ax_raw_amp.grid(True, linestyle="--", alpha=0.6)

    line_filter, = ax_phase_filter.plot([], [], color="cyan", linewidth=2)
    ax_phase_filter.set_title("(e) Spatial Filtered (Median+Uniform)", fontweight="bold")
    ax_phase_filter.set_ylabel("Phase (Rad)")
    ax_phase_filter.grid(True, linestyle="--", alpha=0.6)

    line_final, = ax_phase_final.plot([], [], color="green", linewidth=2)
    ax_phase_final.set_title("(f) SUCCESS: Full + Butterworth", fontweight="bold")
    ax_phase_final.set_xlabel("Subcarrier Index")
    ax_phase_final.set_ylabel("Phase (Rad)")
    ax_phase_final.grid(True, linestyle="--", alpha=0.6)

    def update(_frame):
        last_plot_data = None
        
        while not message_queue.empty():
            item = message_queue.get_nowait()
            
            try:
                csi_raw = item["csi_raw"]
                rssi_val = item.get("rssi")
                
                csi_np = np.array(csi_raw, dtype=float)
                if len(csi_np) % 2 != 0: csi_np = csi_np[:-1]

                complex_csi = csi_np[0::2] + 1j * csi_np[1::2]
                if len(complex_csi) >= 128:
                    complex_csi = complex_csi[64:128]

                amplitude_raw = np.abs(complex_csi)
                raw_phase_full = np.angle(complex_csi)

                IGNORE_INDICES = get_ignore_indices(len(amplitude_raw))
                
                # Dynamic mask for dead/faded subcarriers
                max_amp = np.max(amplitude_raw)
                valid_mask = (amplitude_raw > (max_amp * 0.15)) & ~np.isin(np.arange(len(amplitude_raw)), list(IGNORE_INDICES))
                valid_indices = np.where(valid_mask)[0]

                if len(valid_indices) > 6:
                    edge_trim = 2
                    valid_indices = valid_indices[edge_trim:-edge_trim]

                if len(valid_indices) == 0:
                    continue
                
                # Orijinal ham genlik verisi (normalizasyon öncesi)
                raw_amp_plot = amplitude_raw[valid_indices]
                
                clean_amplitude = amplitude_raw[valid_indices]
                clean_raw_phase = raw_phase_full[valid_indices]
                clean_unwrapped = np.unwrap(clean_raw_phase)

                # Safe normalization preventing division explosion
                if rssi_val is not None and isinstance(rssi_val, (int, float)):
                    linear_rssi = 10 ** ((rssi_val + 50) / 20.0)
                    mean_amp = np.mean(clean_amplitude)
                    clean_amplitude = (clean_amplitude / (mean_amp + 10.0)) * linear_rssi
                else:
                    mean_amp = np.mean(clean_amplitude)
                    if mean_amp > 1e-3:
                        clean_amplitude = clean_amplitude / mean_amp

                temporal_filtered_amp = amp_temporal_filter.process(clean_amplitude)

                # --- FAZ İŞLEMLERİ ---
                result = sanitize_phase_makale(valid_indices, clean_raw_phase, clean_unwrapped)
                temporal_filtered_phase = phase_temporal_filter.process(result['sanitized'])

                x_compact = np.arange(len(valid_indices))
                last_plot_data = (x_compact, valid_indices, raw_amp_plot, temporal_filtered_amp, result, temporal_filtered_phase)

            except Exception:
                continue

        if last_plot_data is None:
            return line_amp, line_raw, line_unwrap, line_raw_amp, line_filter, line_final

        x_compact, valid_indices, raw_amp_plot, final_amp, result, final_phase = last_plot_data

        line_amp.set_data(x_compact, final_amp)
        line_raw.set_data(x_compact, result['raw'])
        line_unwrap.set_data(x_compact, result['unwrapped'])
        line_filter.set_data(x_compact, result['filtered'])
        line_final.set_data(x_compact, final_phase)
        
        # Raw Amplitude grafiğine veri aktarımı
        line_raw_amp.set_data(x_compact, raw_amp_plot)

        # --- EKSEN AYARLARI ---
        max_x = len(valid_indices) - 1
        
        # Tüm alt taşıyıcı (subcarrier) bazlı grafiklerin X eksenini senkronize et
        for ax in [ax_amp, ax_phase_raw, ax_phase_unwrap, ax_raw_amp, ax_phase_filter, ax_phase_final]:
            ax.set_xlim(0, max_x)
            ax.set_xticks(x_compact)
            ax.set_xticklabels(valid_indices, fontsize=7, rotation=90)

        # Y Ekseni Limitleri
        ax_amp.set_ylim(0, max(np.max(final_amp) * 1.2, 1.0))
        ax_phase_raw.set_ylim(-np.pi, np.pi)

        # Raw amplitude Y ekseni (Dinamik)
        if len(raw_amp_plot) > 0:
            ax_raw_amp.set_ylim(0, max(np.max(raw_amp_plot) * 1.2, 1.0))

        if len(result['unwrapped']) > 0:
            u_min, u_max = np.min(result['unwrapped']), np.max(result['unwrapped'])
            if u_max - u_min > 20: u_min, u_max = -10, 10
            ax_phase_unwrap.set_ylim(u_min - 0.5, u_max + 0.5)

        if len(result['filtered']) > 0:
            fl_min, fl_max = np.min(result['filtered']), np.max(result['filtered'])
            if fl_max - fl_min > 20: fl_min, fl_max = -10, 10
            ax_phase_filter.set_ylim(fl_min - 0.5, fl_max + 0.5)

        if len(final_phase) > 0:
            s_min, s_max = np.min(final_phase), np.max(final_phase)
            ax_phase_final.set_ylim(s_min - 0.2, s_max + 0.2)

        return line_amp, line_raw, line_unwrap, line_raw_amp, line_filter, line_final

    animation = FuncAnimation(fig, update, interval=args.interval_ms, cache_frame_data=False)
    plt.show()

if __name__ == "__main__":
    main()