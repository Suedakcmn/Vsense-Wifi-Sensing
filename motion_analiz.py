import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

print("Veri okunuyor...")
df = pd.read_parquet('data/csi_final.parquet')

# CSI kolonunu bul ve DataFrame'e çevir
hedef_kolon = 'csi' if 'csi' in df.columns else df.columns[-1]
veri_matrisi = np.stack(df[hedef_kolon].values)
df_csi = pd.DataFrame(veri_matrisi)

print("Sinyal filtreleniyor ve Motion Score hesaplanıyor...")

# 1. ADIM: Smoothing (Yumuşatma) - Donanım gürültüsünü filtrele
# Her 10 paketin ortalamasını alarak anlık sıçramaları eziyoruz
df_csi_smoothed = df_csi.rolling(window=10, min_periods=1).mean()

# 2. ADIM: Hareket Şiddeti (Varyans) - Sadece belirgin değişimleri yakala
rolling_var = df_csi_smoothed.rolling(window=50, min_periods=1).var()

# 3. ADIM: Alt-taşıyıcıları birleştir
raw_motion_score = rolling_var.mean(axis=1)

# 4. ADIM: Çıkan nihai skoru tekrar yumuşat (Zirveleri netleştirmek için)
final_motion_score = raw_motion_score.rolling(window=30, min_periods=1).mean()

# Yeni skoru çizdir
plt.figure(figsize=(12, 4))
plt.plot(final_motion_score, color='red', linewidth=1.5)
plt.title('Filtrelenmiş Motion Score')
plt.xlabel('Zaman (Paket Sırası)')
plt.ylabel('Hareket Şiddeti (Varyans)')
plt.grid(True)

plt.savefig('filtrelenmis_hareket_skoru.png', dpi=300, bbox_inches='tight')
print("İşlem tamam! 'filtrelenmis_hareket_skoru.png' oluşturuldu.")
