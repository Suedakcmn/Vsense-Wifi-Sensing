# VSense Baseline v1

## Deney düzeni

- Girdi: iki saniyelik CSI pencereleri
- Kayma: bir saniye
- Başlangıç/son kırpma: 10 saniye
- Düğümler: RX1 ve RX2
- Temsil: seçilmiş 20 alt taşıyıcının genlik istatistikleri, RSSI ve paket hızı
- Eğitim: repeat 1 oturumları
- Validation: repeat 2 oturumları
- Test: repeat 3 oturumları
- Model seçme ölçütü: validation macro-F1

Aynı oturumdan gelen pencereler farklı kümelere dağıtılmamıştır.

## Sonuçlar

| Model | Validation macro-F1 | Test accuracy | Test macro-F1 |
|---|---:|---:|---:|
| kNN | 0.618 | 0.354 | 0.271 |
| SVM | 0.473 | 0.358 | 0.273 |

Validation macro-F1 ölçütüne göre seçilen model kNN'dir.

Testte kNN sınıf bazlı F1 sonuçları:

| Sınıf | F1 |
|---|---:|
| empty_room | 0.000 |
| walking | 0.496 |
| sitting | 0.000 |
| standing | 0.000 |
| desk_work | 0.861 |

## Dürüstlük ve sınırlamalar

Bu ilk baseline beş sınıfta yeterli genelleme sağlamamıştır. Test macro-F1
değeri 0.271'dir. Özellikle `empty_room`, `sitting` ve `standing` sınıfları
repeat 3 oturumlarında doğru ayrılamamıştır.

Bu sonuçların olası nedenleri:

- CSI dağılımı oturumlar arasında belirgin değişmektedir.
- Katılımcılar bütün sınıflarda dengeli değildir.
- Mevcut ayrım oturum-bağımsızdır fakat tam kişi-bağımsız değildir.
- Basit pencere istatistikleri aktivitenin frekans örüntülerini yeterince
  temsil etmiyor olabilir.
- RX1 ve RX2 paket hızları farklıdır ve bazı kayıtlarda kısa akış boşlukları
  vardır.

Farklı gün ve farklı kişi testi için, her sınıfı içeren ayrı bir holdout
kampanyası henüz alınmamıştır. Bu nedenle Hafta 6 DoD'sinin bu bölümü henüz
tamamlanmış sayılmamalıdır.

## Artifact'ler

- `model.joblib`: validation sonucuna göre seçilmiş model
- `feature_config.json`: canlı tahmin için pencere ve özellik sözleşmesi
- `metrics.json`: ayrıntılı split ve sınıflandırma metrikleri
- `confusion_matrix_knn.png`: kNN test confusion matrix
- `confusion_matrix_svm.png`: SVM test confusion matrix

## Sonraki deneyler

1. Pencere içi alt taşıyıcı normalizasyonu eklemek.
2. Zamansal/frekans özellikleri ve spektrogram denemek.
3. 1, 2 ve 4 saniyelik pencere uzunluklarını karşılaştırmak.
4. Oturum bazlı çapraz doğrulama yapmak.
5. Her sınıf için farklı gün ve farklı katılımcı holdout kaydı toplamak.
6. İyileştirilmiş temsil üzerinde küçük CNN eğitmek.

