import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

print("Veri okunuyor...")
# Parquet dosyasını yükle
df = pd.read_parquet('data/csi_final.parquet')

print("\n--- Veri Özeti ---")
print(f"Toplam Satır: {len(df)}")
print(f"Kolonlar: {list(df.columns)}")

# CSI verisinin yapısını anlamak için ilk satıra bakalım
# Kolon adı 'csi' veya 'amplitude' olabilir, onu kontrol ediyoruz
hedef_kolon = 'csi' if 'csi' in df.columns else df.columns[-1]
ornek_veri = np.array(df.iloc[0][hedef_kolon])
print(f"\nİlk paketin boyutu: {ornek_veri.shape}")

# Basit bir Heatmap çizimi (İlk 1000 paketi alalım ki hızlı çizsin)
print("\nHeatmap çiziliyor ve kaydediliyor...")
plt.figure(figsize=(12, 6))

# Veriyi 2D matrise çevirme (Eğer zaten matris değilse)
veri_matrisi = np.stack(df[hedef_kolon].head(1000).values)

plt.imshow(veri_matrisi.T, aspect='auto', cmap='viridis')
plt.colorbar(label='Değer')
plt.title('CSI Heatmap (İlk 1000 Paket)')
plt.xlabel('Zaman (Paket Sırası)')
plt.ylabel('Alt-Taşıyıcılar (Subcarriers)')

# Ekranda göstermek yerine dosyaya kaydet
plt.savefig('ilk_heatmap.png', dpi=300, bbox_inches='tight')
print("İşlem tamam! 'ilk_heatmap.png' dosyası oluşturuldu.")
