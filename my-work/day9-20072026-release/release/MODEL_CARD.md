# Model Kartı — IoMT Ağ-Saldırı Detektörü v1

**Sürüm:** v1 · **Dondurulma:** 2026-07-20 · **Provenance:** `MANIFEST_v1.json`
**Kaynak çalışma:** IoMT-NetworkAttackScenarios18 — Zenodo DOI `10.5281/zenodo.16747386`

> **Bu kartın en önemli bölümü §5 (Sınırlılıklar).** Modelin skorları bağlamsız okunduğunda
> yanıltıcıdır ve projenin ana bulgusu tam olarak budur. §5'i okumadan hiçbir rakamı aktarmayın.

---

## 1. Model ne yapıyor

NS-3'te simüle edilmiş bir IoMT (tıbbi nesnelerin interneti) Wi-Fi ağında, **bir simülasyon
koşusunun** akış istatistiklerinden saldırı tespiti ve tip sınıflandırması yapar.

- **Girdi:** koşu başına 13 sayısal öznitelik (12 ölçüm + 1 eksiklik göstergesi). Paket içeriğine
  bakılmaz; yalnız hacim, teslim ve zamanlama istatistikleri kullanılır.
- **Çıktı:** 5 sınıftan biri — `normal`, `dos`, `ddos`, `greyhole`, `blackhole`.
- **Binary tespit** bundan türetilir: `normal` değilse "atak".
- **Granülerlik: koşu düzeyi (run-level), akış düzeyi değil.** Yani "bu 30 saniyelik koşuda bir
  saldırı var mıydı" sorusunu yanıtlar; gerçek zamanlı akış sınıflandırıcısı değildir.

**Amaçlanan kullanım:** akademik/eğitim amaçlı; flow-tabanlı tespitin neyi görüp neyi göremediğini
göstermek. **Amaçlanmayan kullanım:** gerçek klinik ağlarda üretim IDS'i olarak konuşlandırmak
(§5.6, §5.7).

## 2. Eğitim verisi

| | |
|---|---|
| Kaynak | NS-3 simülasyonu (`my-work/scenarios/`), gerçek ağ trafiği **değil** |
| Toplam koşu | 285 (`dataset_v1.csv`) |
| Eğitimde kullanılan | 255 |
| Eğitim dışı bırakılan | 30 (`dos` yoğunluk < 10 pkt/s) |
| Sınıf dağılımı | greyhole 110 · dos 100 · normal 40 · ddos 25 · blackhole 10 |
| Prob seti | 340 koşu (`probes_v1.csv`) — **yalnız değerlendirildi, hiç eğitilmedi** |

**Neden 30 koşu eğitim dışı:** 10 pkt/s altındaki DoS, feature uzayında `normal`'den ayırt
edilemiyor (aynı tohumda teslim farkı −0.003, throughput farkı −0.07 Mbps). Bunları `dos` diye
eğitmek tek vektöre iki etiket yüklemek olurdu. **Ölçüldü:** eğitime katılınca yanlış alarm
%12.5 → %35, macro-F1 0.809 → 0.741. Eğrinin tabanını görmek için gerekli olduklarından
değerlendirme probu olarak tutuluyorlar.

**Dengesizlik:** sınıflar dengesiz (110 ↔ 10). `class_weight="balanced"` ile telafi ediliyor.

## 3. Değerlendirme yöntemi

**Config-grupli bölme (`StratifiedGroupKFold`, 5 kat).** Saldırı sınıflarında grup = yoğunluk
konfigürasyonu, yani model her yoğunluğu **hiç görmediği** halde tahmin ediyor;
`normal`/`blackhole` tek konfig olduğu için koşu düzeyinde gruplu.

**Neden bu şema:** aynı konfigürasyonun farklı tohumları feature düzeyinde birbirinin kopyası
(konfig-içi CV ≈ 0.001). Rastgele bölme onları train ve test'e dağıtıp modelin soruyu ezberlemesine
izin veriyordu: **shuffle-CV 0.994, config-grupli 0.786.** Gerçek olan ikincisidir.

## 4. Sonuçlar (dürüst, config-grupli)

**Çok sınıflı:** macro-F1 **0.786 ± 0.092** (kat ortalaması) / **0.792** (havuzlanmış OOF)

> Bu iki sayı farklı istatistiklerdir, farklı koşular değil: biri kat-başı F1'lerin ortalaması,
> diğeri havuzlanmış tahminler üzerindeki macro avg. Sapma yönü sabit olmadığından karıştırılmamalı.

| sınıf | precision | recall | F1 |
|---|---|---|---|
| normal | 0.761 | 0.875 | 0.814 |
| dos | 0.697 | 0.657 | **0.672** |
| ddos | 0.571 | 0.640 | **0.577** |
| greyhole | 0.971 | 0.927 | 0.944 |
| blackhole | 0.909 | 1.000 | 0.952 |

**Binary tespit (türetilmiş):** TN=35 · FP=5 · FN=11 · TP=204 · attack-F1 **0.962**
Yanlış alarm tabanı **0.125** (saldırı yokken "atak" denme oranı).

---

## 5. Sınırlılıklar — bu bölüm rakamlardan daha önemlidir

### 5.1 Binary tespit doygun: ölçtüğü şey saldırı değil, aracının varlığı

Yol üzerinde **tek paket bile düşürmeyen** bir relay, 40 koşunun ~39'unda "atak" işaretleniyor
(R0 = 0.975–1.000). Grey-hole tespit eğrisinin **tamamı** bu tabanın üstüne çıkmıyor — çıkamaz,
çünkü taban zaten tavan.

**Sonuç:** "grey-hole'ün %90'ını yakalıyoruz" gibi bir ifade yanlış çerçevededir. Model iki ayrı
yeteneği karıştırır: *topolojik anomali tespiti* ("ağda olmaması gereken bir aracı var" — bunda
kusursuz) ve *saldırı tespiti* ("o aracı zarar veriyor" — bu eksende kör). Ayırmadan verilen her
tespit rakamı birincisini ikincisi diye satar. (docs/19)

### 5.2 Grey-hole: %5–10'un altında görünmez

Ayrım `normal`'e karşı değil **zararsız relay'e** karşı ölçüldüğünde gerçek çöküş ortaya çıkıyor:

| | STA8 (31.6 m) | STA5 (10.0 m) |
|---|---|---|
| yanlış alarm tabanı | 0.350 | 0.225 |
| p = 0.02 | 0.40 (taban üstü +0.05) | 0.20 (**−0.025**) |
| p = 0.05 | 0.70 | 0.70 |
| p = 0.10 | 0.90 | 1.00 |
| **çöküş noktası** | **p = 0.1** | **p = 0.1** |

Bir grey-hole'ün zararsız bir aracıdan ayrılması için paketlerin **en az %5–10'unu** düşürmesi
gerekiyor. Altında saldırı, zararsız relay'in kendi gürültüsüne gömülüyor. (docs/23)

### 5.3 dos ↔ ddos ayrımı zayıf — model "kaç saldırgan"ı değil "ne kadar hasar"ı okuyor

İki sınıf çift yönlü karışıyor (F1 0.672 / 0.577).

Bir süre bunun **grid artefaktı** olduğu ve düzgün bir eğitim grid'iyle düzeltilebileceği
düşünüldü. Dayanağı şuydu: toplam yük 200 pkt/s'de sabit tutulup yalnız saldırgan sayısı
değiştirildiğinde doğru-tip oranı **0.925** çıkıyordu. **Bu dayanak 2026-07-21'de çürütüldü**
(docs/24, notebook 10):

- O grid yükü **teklif** düzeyinde eşitliyor, **gerçekleşen hasarı değil**. Saldırgan sayısı
  arttıkça çekişme artıyor ve delivery (0.897→0.626), kayıp (0.161→0.549), gecikme *hep
  birlikte* kayıyor (ρ ≈ 0.85). Model saldırgan sayısını bu eksenlerin herhangi birinden
  okuyabiliyor.
- **Hiçbir feature grubu gerekli değil** — herhangi biri çıkarıldığında sonuç ≥0.891 kalıyor.
- Ayrımı taşıdığı sanılan **akış sayısı en zayıf grup** (tek başına 0.823); hacim tek başına
  0.907.
- **Gerçekleşen hasar eşleştirildiğinde ayrım şansa iniyor:** 0.662 → **0.475** (şans 0.500).

**Doğru okuma:** `ddos` sınıfı pratikte "saldırgan sayısı çok" değil **"hasar çok"** anlamına
geliyor — `greyhole`'ün "relay var", `mitm`'in "relay düşürmüyor" anlamına gelmesiyle aynı
desen (§5.1, §5.4). Koşu-başı 12 sayılık özet, "kaç saldırgan" bilgisini "ne kadar hasar"
bilgisi içinde eritiyor.

*Sınır (dürüstlük kaydı):* "dos ve ddos temelde ayrılamaz" **denmiyor.** Kontrol deneyi, bant
daraltmanın küçük-örneklem cezasının da +0.070 taşıdığını gösterdi (eşleştirmenin kendi katkısı
+0.117), ve eşleştirmesiz kontrolün yayılımı geniş (±0.157). Söylenebilen: *ayrılabilir olduğu
iddiasının dayanağı geçersiz.* Kalan belirsizliği çözecek olan daha iyi bir grid değil, **daha
çok ddos konfigi** — sınıf 5 konfig / 25 koşu ile temsil ediliyor ve her fold tek konfig test
ediyor. **Bu modeli dos/ddos ayrımı için kullanmayın.**

### 5.4 Zamanlama saldırıları görünmüyor

Paketleri düşürmeden **geciktiren** bir relay (timing-MITM), 80/80 koşuda `greyhole` işaretleniyor
ve gecikme 1 ms'den 200 ms'ye çıkarılırken tespit sabit 1.0 kalıyor — yani eğri `delay` hakkında
hiçbir bilgi taşımıyor.

`mitm` 6. sınıf olarak eğitildiğinde F1 = 0.859 alıyor, **ama öğrendiği şey timing değil**: aynı
modele hiçbir şey yapmayan relay sorulduğunda %80 `mitm` diyor. Modelin `mitm` sınıfı pratikte
**"paket düşürmeyen on-path relay"** anlamına geliyor. Bu yüzden v1'e dahil edilmedi.

**Yapısal sebep:** FlowMonitor akış-başı transit ölçüyor; relay birinci akışı sonlandırıp ikinciyi
başlattığı için tutma süresi ikisinin **arasında** kalıyor. `victim_startup_lag_ms` bu boşluğu
ölçüm düzeyinde kapatıyor (28 → 162 ms, monoton) ama karar doygun olduğu için tespit değişmiyor.
(docs/21, docs/22 §1)

### 5.5 Rakamlar bu topolojiye özgü

Relay'in konumu sonuçları belirgin şekilde değiştiriyor: AP'ye 10 m'de zararsız relay'in teslimi
0.987 (normalin içinde, neredeyse görünmez), 40 m'de 0.814. Yanlış alarm tabanı 0.225 ↔ 0.350
arasında oynuyor. **Her relay-tabanı rakamı, relay konumuyla birlikte verilmelidir.**

Ayrıca koğuş çapraz trafiği STA3–STA7'yi kaynak olarak kullanıyor; STA8 kendi trafiği olmayan tek
düğüm. Relay başka bir düğüme taşındığında ölçüm "relay + o cihaz" olur. (docs/22 §2)

### 5.6 Veri simülasyondur

Gerçek hastane ağından tek bir paket yoktur. Özellikle:

- Trafik **UDP**'dir; gerçek IoMT telemetrisi çoğunlukla MQTT/TCP üzerinden akar. Bu bilinçli bir
  sadeleştirmedir ve tıkanıklık kontrolü olan protokollerde davranış farklı olacaktır.
- Topoloji sabit 9 STA + 1 AP + 1 Hexoskin'dir; cihaz sayısı, hareketlilik ve girişim gerçek bir
  koğuşun çeşitliliğini yansıtmaz.
- Kaynak çalışmanın kendi yayımlanmış verisi üzerinde denendiğinde model **her şeyi** tek sınıfa
  eşliyor (yazarın `normal` koşuları dahil): ölçtüğü şey tespit değil **domain shift**. Yani bu
  model başka bir simülasyon kurulumuna bile aktarılamaz. (docs/15)

### 5.7 Üretimde kullanılmamalıdır

§5.1–5.6 birlikte okunduğunda: bu model, ağda bir aracının **varlığını** güvenilir biçimde
saptıyor; o aracının **kötü niyetli olup olmadığını** ancak paketlerin %5–10'undan fazlası
düşürülüyorsa ayırt edebiliyor; zamanlama saldırılarını hiç göremiyor; ve rakamları eğitildiği
topolojiye bağlı. Klinik bir ortamda bağlayıcı kısıt yanlış alarm oranıdır ve buradaki taban
(0.225–0.350) üretim için fazlasıyla yüksektir.

---

## 6. Kullanım

```python
import joblib, json, pandas as pd

meta  = json.load(open("MANIFEST_v1.json"))
model = joblib.load("detector_v1.joblib")
feats = meta["model"]["features"]            # son eleman: monitor_missing

df = pd.read_csv("dataset_v1.csv")
X  = df[feats[:-1]].copy()
X["monitor_missing"] = df["monitor_owd_ms"].isna().astype(int)
model.predict(X.fillna(0.0))
```

**İki uyarı:**

1. `joblib` dosyaları **sürüme duyarlıdır**. Farklı bir scikit-learn altında yüklenmeyebilir veya
   sessizce farklı davranabilir. Release'in kullandığı sürümler `MANIFEST_v1.json` →
   `environment` altındadır; `freeze_release.py --check` uyuşmazlığı bildirir.
2. `joblib`/`pickle` yüklerken **kod çalıştırır**. Yalnız kendi ürettiğiniz veya güvendiğiniz
   dosyaları açın.

**Bütünlük doğrulaması:**

```bash
python3 freeze_release.py --version v1 --check
```

## 7. Yeniden üretim

| adım | komut |
|---|---|
| Ham XML üretimi | `run_sweep.py --jobs 4` |
| XML → veri seti | `build_dataset.py --manifest manifest.csv --outdir out` |
| Dondurma | `freeze_release.py --version v1` |

Ayrıntılı gerekçeler ve deney kayıtları: `docs/` (özellikle 19, 21, 22, 23).
Değerlendirme notebook'ları: `my-work/day5-10072026-detector/01–08`.

## 8. Atıf

Bu çalışma, aşağıdaki çalışmanın senaryolarını temel alır ve onun atıflanmasını gerektirir:

> IoMT-NetworkAttackScenarios18 — Zenodo DOI `10.5281/zenodo.16747386`

**Not:** senaryolar temel alınmış ancak yeniden yazılmıştır (gerçekçi gürültü tabanı, çalışan DDoS,
gerçek on-path grey-hole). Kaynak çalışmanın yayımlanmış çıktıları bu modelin eğitiminde
kullanılmamıştır; yalnız domain-shift probu olarak sınanmıştır (§5.6).
