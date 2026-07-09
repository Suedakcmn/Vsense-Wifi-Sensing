import numpy as np

# İncelemek istediğin dosyanın yolunu buraya yaz
dosya_yolu = "user4-6-1-1-1-r2.dat"

try:
    # Veriyi binary olarak okuma (Format projenin yapısına göre float32, complex vb. olabilir)
    veri = np.fromfile(dosya_yolu, dtype=np.float32) 
    print(f"Dosya başarıyla okundu!")
    print(f"Toplam değer sayısı: {veri.size}")
    print(f"İlk 20 ham değer:\n{veri[:20]}")
except Exception as e:
    print("Okuma hatası:", e)
