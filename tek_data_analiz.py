import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

hedef_dosya = "user4-6-1-1-1-r2.dat"

print(f"1. Dev veri seti okunuyor ve '{hedef_dosya}' filtreleniyor...")

# 1. Ana dosyayı oku
df_tumu = pd.read_parquet('data/csi_final.parquet')

# 2. SADECE hedef dosyaya ait olan satırları çek (İşte bütün sihir burada!)
df = df_tumu[df_tumu['file_name'] == hedef_dosya].copy()

if len(df) == 0:
    print(f"HATA: '{hedef_dosya}' dev dosyanın içinde bulunamadı!")
    exit()

print(f"Filtreleme başarılı! {hedef_dosya} için {len(df)} paket bulundu.")

# 3. Veriyi matrise çevir (Kolon adın ingest_data.py'ye göre 'csi_amplitude')
veri_matrisi = np.stack(df['csi_amplitude'].values)
df_csi = pd.DataFrame(veri_matrisi)

# --- GRAFİK: HAREKET SKORU (MOTION SCORE) ---
print("2. Motion Score hesaplanıyor...")
smoothed = df_csi.rolling(window=10, min_periods=1).mean()
rolling_var = smoothed.rolling(window=50, min_periods=1).var()
raw_motion_score = rolling_var.mean(axis=1)
final_motion_score = raw_motion_score.rolling(window=30, min_periods=1).mean()

plt.figure(figsize=(12, 4))
plt.plot(final_motion_score.values, color='red', linewidth=1.5)
plt.title(f'{hedef_dosya} - Parquet İçinden Filtrelenmiş Skor')
plt.xlabel('Zaman (Paket Sırası)')
plt.ylabel('Hareket Şiddeti (Varyans)')
plt.grid(True)
plt.savefig('tek_motion_score.png', dpi=300, bbox_inches='tight')
plt.close()

print("İşlem tamamlandı! Grafiği açmak için: open tek_motion_score.png")
