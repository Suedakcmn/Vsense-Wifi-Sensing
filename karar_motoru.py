import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

hedef_dosya = "user4-6-1-1-1-r2.dat"
print(f"1. Veri yükleniyor: {hedef_dosya}")

df_tumu = pd.read_parquet('data/csi_final.parquet')
df = df_tumu[df_tumu['file_name'] == hedef_dosya].copy()

veri_matrisi = np.stack(df['csi_amplitude'].values)
df_csi = pd.DataFrame(veri_matrisi)

print("2. Sinyal işleniyor...")
smoothed = df_csi.rolling(window=10, min_periods=1).mean()
rolling_var = smoothed.rolling(window=50, min_periods=1).var()
motion_score = rolling_var.mean(axis=1).rolling(window=30, min_periods=1).mean()

print("3. Dinamik Kalibrasyon (Sıfır Noktası)...")
kalibrasyon_paketi = 500
baseline_max = motion_score.iloc[50:kalibrasyon_paketi].max()
threshold = baseline_max * 1.5

print("4. Karar Mekanizması (Debounce Filtreli)...")
# Ham karar: Eşiği geçen her an
ham_karar = motion_score > threshold

# DEBOUNCE FİLTRESİ: Son 10 paketin en az %80'i True ise hareket kabul et
# Bu sayede anlık saliselik cızırtılar elenmiş olur.
karar_dizisi = ham_karar.rolling(window=10, min_periods=1).mean() >= 0.8

print("\n5. Sonuç grafiği çiziliyor...")
plt.figure(figsize=(12, 5))
plt.plot(motion_score.values, color='blue', linewidth=1.5, label='Motion Score (Hareket Şiddeti)')
plt.axhline(y=threshold, color='red', linestyle='--', linewidth=2, label=f'Otomatik Threshold ({threshold:.2f})')
plt.fill_between(range(len(motion_score)), 0, motion_score.values, where=karar_dizisi.values, color='red', alpha=0.3, label='Sistem Kararı: HAREKET VAR')
plt.title(f'{hedef_dosya} - Kusursuz Karar Mekanizması (Debounce)')
plt.xlabel('Zaman (Paket Sırası)')
plt.ylabel('Hareket Şiddeti')
plt.legend()
plt.grid(True)
plt.savefig('kusursuz_karar_grafigi.png', dpi=300, bbox_inches='tight')
plt.close()

print("İşlem tamam! Yeni grafiği açmak için terminale şunu yaz:")
print("open kusursuz_karar_grafigi.png")
