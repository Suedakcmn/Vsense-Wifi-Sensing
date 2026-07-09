import pandas as pd
import numpy as np
import os
import glob
import csiread

def ingest_all_dat_files(output_file):
    search_path = os.path.join("data", "**", "*.dat")
    dat_files = sorted(glob.glob(search_path, recursive=True))
    
    if not dat_files:
        print("Hata: .dat dosyası bulunamadı.")
        return

    print(f"Toplam {len(dat_files)} dosya bulundu. İkili (Binary) formattan ayrıştırılıyor...")
    
    all_dfs = []
    for file in dat_files:
        try:
            csidata = csiread.Intel(file, if_report=False)
            csidata.read()
            
            amplitude = np.abs(csidata.csi)
            csi_list = [row.flatten().tolist() for row in amplitude]
            
            df = pd.DataFrame({
                'file_name': os.path.basename(file),
                'ts_us': csidata.timestamp_low,
                'rssi_a': csidata.rssi_a,
                'rssi_b': csidata.rssi_b,
                'rssi_c': csidata.rssi_c,
                'csi_amplitude': csi_list
            })
            all_dfs.append(df)
            print(f"Başarılı: {os.path.basename(file)} -> {len(df)} paket eklendi.")
            
        except Exception as e:
            print(f"Uyarı ({os.path.basename(file)}): Okunamadı - {e}")

    if all_dfs:
        final_df = pd.concat(all_dfs, ignore_index=True)
        final_df = final_df.sort_values(['file_name', 'ts_us'])
        
        final_df.to_parquet(output_file, index=False)
        print("\n" + "="*50)
        print(f"MUHTEŞEM! Veriler birleştirildi ve kaydedildi: {output_file}")
        print(f"Toplam Paket (Satır) Sayısı: {len(final_df)}")
        print("="*50)

if __name__ == "__main__":
    ingest_all_dat_files("data/csi_final.parquet")
