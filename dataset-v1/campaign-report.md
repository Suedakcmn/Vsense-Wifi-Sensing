# VSense Week 5 Veri Kampanyası Raporu

## 1. Amaç

Bu kampanyada Wi-Fi CSI verileri, LD2450 mmWave radar verileriyle aynı kayıt
oturumunda toplanarak aktivite sınıflandırması için etiketli `dataset-v1` veri
seti oluşturulmuştur.

Ana veri setinde beş senaryo için üçer bağımsız tekrar bulunmaktadır:

- `empty_room`
- `walking`
- `sitting`
- `standing`
- `desk_work`

Ana 15 oturuma ek olarak, iki kişinin aynı anda oturduğu bir yardımcı
`sitting` kaydı da saklanmıştır.

## 2. Kampanya düzeni

- Kayıt tarihleri: 10-11 Ağustos 2026
- Konum: `lab`
- Operatör: `busra`
- CSI alıcıları: `rx_01`, `rx_02`
- Ground-truth düğümü: `ld2450_01`
- MQTT broker: `192.168.128.34:1883`
- LD2450 UART hızı: 256000 baud
- Ortak zaman alanı: `collector_ts_us`

Her oturum klasöründe aşağıdaki dosyalar bulunmaktadır:

- `metadata.json`: oturum, katılımcı, konum, süre ve cihaz bilgileri
- `labels.json`: senaryo etiketi ve etiket zaman aralığı
- `csi.jsonl`: RX1 ve RX2 CSI kayıtları
- `ground_truth.jsonl`: LD2450 hedef kayıtları
- `telemetry.jsonl`: cihaz sağlık ve aktarım sayaçları
- `session.log`: collector çalışma günlüğü

## 3. Ana kayıtlar

| Senaryo | Tekrar | Oturum | Katılımcı | Süre (dk) | CSI satırı | Radar satırı | Kalite | RX1 P95 (ms) | RX2 P95 (ms) | Radar hedefli satır |
|---|---:|---|---|---:|---:|---:|---|---:|---:|---:|
| Empty room | 1 | `20260810_142641_lab_empty_room_r01` | none | 10.9 | 96,702 | 7,349 | WARNING | 13.923 | 11.455 | 6.2% |
| Empty room | 2 | `20260810_145706_lab_empty_room_r02` | none | 43.0 | 415,697 | 29,010 | WARNING | 10.751 | 10.901 | 0.2% |
| Empty room | 3 | `20260811_150821_lab_empty_room_r03` | none | 10.5 | 78,390 | 7,098 | WARNING | 11.034 | 27.999 | 1.2% |
| Walking | 1 | `20260810_154517_lab_walking_r01` | busra | 10.5 | 103,260 | 7,061 | WARNING | 9.868 | 13.817 | 2.2% |
| Walking | 2 | `20260810_160021_lab_walking_r02` | sueda | 10.8 | 106,438 | 7,275 | PASS | 9.786 | 10.061 | 2.9% |
| Walking | 3 | `20260810_161516_lab_walking_r03` | busra | 10.6 | 104,137 | 7,148 | WARNING | 10.059 | 13.460 | 2.3% |
| Sitting | 1 | `20260811_111731_lab_sitting_r01` | busra | 10.1 | 75,896 | 6,831 | WARNING | 11.417 | 25.913 | 93.3% |
| Sitting | 2 | `20260811_132130_lab_sitting_r02` | busra | 10.3 | 79,803 | 6,974 | WARNING | 10.722 | 28.080 | 100.0% |
| Sitting | 3 | `20260811_133652_lab_sitting_r03` | busra | 10.4 | 78,668 | 6,982 | WARNING | 13.161 | 26.685 | 95.0% |
| Standing | 1 | `20260811_135408_lab_standing_r01` | busra | 10.4 | 83,166 | 7,003 | WARNING | 13.482 | 28.138 | 100.0% |
| Standing | 2 | `20260811_142725_lab_standing_r02` | sueda | 10.9 | 75,703 | 7,348 | WARNING | 20.509 | 28.955 | 1.2% |
| Standing | 3 | `20260811_145406_lab_standing_r03` | busra | 10.8 | 76,729 | 7,269 | PASS | 14.324 | 28.121 | 100.0% |
| Desk work | 1 | `20260811_103534_lab_desk_work_r01` | sueda | 12.0 | 92,066 | 8,108 | WARNING | 10.733 | 32.054 | 6.1% |
| Desk work | 2 | `20260811_104956_lab_desk_work_r02` | sueda | 12.2 | 99,697 | 8,196 | WARNING | 10.681 | 25.635 | 6.7% |
| Desk work | 3 | `20260811_110352_lab_desk_work_r03` | sueda | 11.0 | 95,506 | 7,433 | WARNING | 10.513 | 22.459 | 6.7% |

## 4. Senaryo süreleri

| Senaryo | Tekrar sayısı | Toplam süre (dk) |
|---|---:|---:|
| Empty room | 3 | 64.4 |
| Walking | 3 | 31.9 |
| Sitting | 3 | 30.8 |
| Standing | 3 | 32.1 |
| Desk work | 3 | 35.2 |
| **Toplam** | **15** | **194.4** |

Ana veri setinde toplam 1,661,858 CSI satırı ve 131,085 LD2450 satırı
bulunmaktadır.

## 5. Yardımcı çok kişili kayıt

| Senaryo | Oturum | Katılımcı | Süre (dk) | CSI satırı | Radar satırı | Kalite |
|---|---|---|---:|---:|---:|---|
| Sitting | `20260811_095654_lab_sitting_r01` | two_people | 11.4 | 92,303 | 7,667 | WARNING |

Bu oturum ana üç tek kişilik `sitting` tekrarına dahil edilmemiştir. Çok
kişili deneylerde yardımcı veri olarak kullanılabilir.

## 6. Kalite ve senkronizasyon

Validasyon sırasında CSI ve radar satırları collector tarafından eklenen
`collector_ts_us` alanı üzerinden eşleştirilmiştir. Ana kalite sınırı P95
CSI-radar zaman farkı için 200 ms olarak belirlenmiştir.

- `PASS`: yapısal hata veya önemli akış uyarısı yoktur.
- `WARNING`: P95 senkronizasyon sınırı sağlanmıştır ancak izole kısa akış
  kesintileri görülmüştür.
- `FAIL`: gerekli düğüm/veri eksiktir, süre yetersizdir, kayıt tamamlanmamıştır
  veya P95 senkronizasyon sınırı aşılmıştır.

Ana 15 oturumun tamamında hem RX1 hem RX2 P95 zaman farkı 200 ms sınırının
altındadır. En yüksek P95 değerleri RX1 için 20.509 ms, RX2 için 32.054 ms
olarak ölçülmüştür. Böylece rastgele seçilecek bir ana oturum için beklenen
CSI-radar zaman farkının 200 ms altında olması DoD şartı P95 ölçütüne göre
sağlanmaktadır.

`WARNING` oturumları ML için kullanılabilir. Eğitim verisi hazırlanırken
akış kesintilerinin çevresindeki zaman pencereleri dışarıda bırakılmalıdır.

## 7. Bilinen sınırlamalar

- Bazı oturumlarda RX1 veya RX2 akışında yaklaşık 1-5 saniyelik izole CSI
  kesintileri görülmüştür.
- LD2450 tamamen hareketsiz kişileri zaman zaman takip edememektedir.
  `standing` repeat 2 kaydında hedefli radar satırı oranı yalnızca %1.2'dir.
  Oturum etiketi kontrollü senaryo bilgisinden gelmektedir; bu oturum güçlü
  bir sürekli konum ground-truth kaynağı olarak değerlendirilmemelidir.
- `desk_work` oturumlarında kişi oturup küçük hareketler yaptığı için radar
  hedefi zaman zaman kaybetmiştir.
- `empty_room` kayıtlarının başlangıç ve sonunda operatör giriş/çıkışından
  kaynaklanan kısa hedef algılamaları bulunabilir.
- Aynı oturumdan üretilen ML pencereleri eğitim, doğrulama ve test kümelerine
  dağıtılmamalıdır. Veri bölme işlemi oturum kimliğine göre yapılmalıdır.

## 8. ML kullanımı için öneri

1. Her oturumun başlangıç ve sonundaki operatör giriş/çıkış bölümleri kırpılmalıdır.
2. CSI veya radar akış boşluğuyla kesişen pencereler çıkarılmalıdır.
3. CSI ve radar `collector_ts_us` üzerinden eşleştirilmelidir.
4. Ana senaryo etiketi `labels.json` ve `metadata.json` içinden okunmalıdır.
5. Veri ayrımı satır veya pencere bazında değil, oturum bazında yapılmalıdır.
6. Çok kişili sitting kaydı ana tek kişilik modelden ayrı tutulmalı veya
   `participant_count=2` bilgisiyle kullanılmalıdır.

## 9. Sonuç

Beş senaryonun her biri için en az 10 dakikalık üç bağımsız ana tekrar
tamamlanmıştır. CSI, LD2450 ground-truth, etiket, metadata ve telemetry
dosyaları oturum bazında kaydedilmiştir. Ana kayıtların tamamı P95
senkronizasyon açısından 200 ms sınırını sağlamaktadır. Veri seti, belirtilen
kesinti pencereleri filtrelenerek ML ön işleme aşamasına hazırdır.
