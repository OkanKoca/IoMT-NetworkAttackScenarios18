# Model Kartı — IoMT Ağ-Saldırı Detektörü v1.1

**Sürüm:** v1.1 · **Dondurulma:** 2026-07-21 · **Provenance:** `MANIFEST_v1.1.json`
**Kaynak çalışma:** IoMT-NetworkAttackScenarios18 — Zenodo DOI `10.5281/zenodo.16747386`

> **Bu kartın en önemli bölümü §5 (Sınırlılıklar).** Modelin skorları bağlamsız okunduğunda
> yanıltıcıdır ve projenin ana bulgusu tam olarak budur. §5'i okumadan hiçbir rakamı aktarmayın.

> **Buradaki her sayı `report_numbers.py` tarafından üretilir ve `report_numbers.json`'da durur.**
> Elle kopyalanmaz. Sebebi v1'in kendisidir: rakamlar notebook hücrelerinden elle aktarıldığı için
> bu kart bir yerde yanlış alarmı 0.125, başka yerde 0.150 diyordu, ve sınıf tablosunda hiçbir
> precision/recall çiftinin veremeyeceği bir F1 vardı. Betik her satırda `F1 = 2PR/(P+R)`
> eşitliğini kontrol ediyor ve sağlanmazsa çalışmayı reddediyor.

## Sürüm notu — v1 → v1.1

v1'in probe kümesi, "yalnız değerlendirildi, hiç eğitilmedi" iddiasını taşıdığı halde
**eğitim satırlarının 15 kopyasını içeriyordu**. Sebep: hacim-eşleşmeli kontrol kolları,
eğitim gridindeki konfigürasyonları eğitimdeki tohumlarla yeniden koşuyordu. Bu kolların
tohumları eğitim aralığının dışına taşındı ve `freeze_release.py`'ye bir kapı eklendi —
probe ile eğitim arasında tek bir çakışma bile varsa sürüm kesilmiyor.

**Veri seti ve model dosyası v1 ile birebir aynıdır** (`ee9d8ea2…`, `8e3b5c25…`); yalnız
probe dosyası değişti. Dolayısıyla v1'in *modeline* karşı yazılmış her rakam geçerli kaldı;
yeniden okunması gereken tek şey prob'lara dayanan iddialardı (§5.3).

Aynı turda bu karttaki rakamlar 12 girdili bir koşumdan **13 girdili yayımlanan modele**
taşındı. Model sonucu bu farka dayanıklı (0.786 ↔ 0.788), ama v1'in tabloları iki ayrı
koşumdan birleştirilmişti.

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
| Toplam koşu | 285 (`dataset_v1.1.csv`) |
| Eğitimde kullanılan | 255 (73 grup) |
| Eğitim dışı bırakılan | 30 (`dos` yoğunluk < 10 pkt/s) |
| Sınıf dağılımı | greyhole 110 · dos 100 · normal 40 · ddos 25 · blackhole 10 |
| Prob seti | 340 koşu (`probes_v1.1.csv`) — yalnız değerlendirildi, hiç eğitilmedi |

**Prob kümesi iddiası artık ölçülmüş bir sonuçtur, bir not değil.** `MANIFEST_v1.1.json`
şunu taşıyor: *340 prob girdi vektörünün 0'ı, 255 eğitim girdi vektöründen herhangi biriyle
eşleşiyor (dondurma anında doğrulandı).* Karşılaştırma modelin fiilen gördüğü vektör üzerinde
yapılıyor, ham sütunlar üzerinde değil — ham sütunlarda NaN hiçbir zaman NaN'a eşit olmadığı
için kopyalar sessizce kaçardı.

**Neden 30 koşu eğitim dışı:** 10 pkt/s altındaki DoS, feature uzayında `normal`'den ayırt
edilemiyor (aynı tohumda teslim farkı −0.003, throughput farkı −0.07 Mbps). Bunları `dos` diye
eğitmek tek vektöre iki etiket yüklemek olurdu. **Ölçüldü:** eğitime katılınca dürüst macro-F1
0.788 → **0.762** düşüyor (maliyet 0.026). Eğrinin tabanını görmek için gerekli olduklarından
değerlendirme probu olarak tutuluyorlar.

**Dengesizlik:** sınıflar dengesiz (110 ↔ 10). `class_weight="balanced"` ile telafi ediliyor.

## 3. Değerlendirme yöntemi

**Config-grupli bölme (`StratifiedGroupKFold`, 5 kat).** Saldırı sınıflarında grup = yoğunluk
konfigürasyonu, yani model her yoğunluğu **hiç görmediği** halde tahmin ediyor;
`normal`/`blackhole` tek konfig olduğu için koşu düzeyinde gruplu.

**Neden bu şema:** aynı konfigürasyonun farklı tohumları feature düzeyinde birbirinin kopyası
(konfig-içi CV ≈ 0.001). Rastgele bölme onları train ve test'e dağıtıp modelin soruyu
ezberlemesine izin veriyor. **Aynı veri üzerinde ölçülen fark: shuffle 0.828 → config-grupli
0.788, yani bölme yönteminin maliyeti 0.040.** Gerçek olan ikincisidir.

> **Düzeltme (v1.1).** Bu kartın önceki sürümü ve rapor taslakları bu maliyeti
> **"0.994 → 0.786"** diye veriyordu, yani yaklaşık dört katı. İki sayı aynı karşılaştırmanın
> uçları değil: **0.994, artık var olmayan eski ve gürültüsüz veri setinde** ölçülmüştü. O
> tabanda `normal` koşularının teslim oranı tam olarak 1.0'dı (std = 0) ve throughput'un
> standart sapması 0.0001 mertebesindeydi; böyle bir zeminde herhangi bir kalıntı fark
> astronomik derecede anlamlı çıkıyordu. 0.994'ten 0.786'ya inişin büyük kısmı **bölme
> yönteminden değil, tabana gerçekçi gürültü ve tıkanıklık eklenmesinden** geliyor.
>
> Bu düzeltme bulguyu zayıflatmıyor, yerini değiştiriyor: projenin asıl kazanımı dürüst
> bölme değil, **ölçülmeye değer bir taban kurmuş olmak.**

## 4. Sonuçlar (dürüst, config-grupli)

**Çok sınıflı:** macro-F1 **0.788 ± 0.094** (kat ortalaması) / **0.797** (havuzlanmış OOF)

> Bu iki sayı farklı istatistiklerdir, farklı koşular değil: biri kat-başı F1'lerin ortalaması,
> diğeri havuzlanmış tahminler üzerindeki macro avg. Sapma yönü sabit olmadığından karıştırılmamalı.
> **± değeri 5 katın standart sapmasıdır, standart hata değildir** — ikisi √5 kadar farklıdır.

| sınıf | precision | recall | F1 |
|---|---|---|---|
| normal | 0.756 | 0.850 | 0.800 |
| dos | 0.681 | 0.671 | **0.676** |
| ddos | 0.600 | 0.600 | **0.600** |
| greyhole | 0.981 | 0.936 | 0.958 |
| blackhole | 0.909 | 1.000 | 0.952 |

> Bu tablonun her satırı `F1 = 2PR/(P+R)` eşitliğini sağlar ve bu betikte assert'lenir. v1'in
> tablosunda `ddos` satırı P=0.571, R=0.640, F1=0.577 diyordu; o çiftin verdiği F1 0.604'tür ve
> hiçbir yuvarlamayla 0.577 olmaz. Sebep: tablo iki ayrı koşumdan (12 ve 13 girdili) elle
> birleştirilmişti. Artık tek koşumdan geliyor.

**Binary tespit (türetilmiş):** TN=34 · FP=6 · FN=11 · TP=204 · attack-F1 **0.960**
Yanlış alarm tabanı **0.150** (saldırı yokken "atak" denme oranı).

> v1 bu satırı 35/5 ve 0.962 diye veriyordu, ve yanlış alarmı bir yerde 0.125, başka yerde
> 0.150 diye. 35/5/0.962/0.125 **12 girdili** koşumun sonucuydu; yayımlanan model 13 girdi
> alıyor. Yukarıdakiler yayımlanan modelin kendi sayılarıdır.

---

## 5. Sınırlılıklar — bu bölüm rakamlardan daha önemlidir

### 5.1 Binary tespit doygun: ölçtüğü şey saldırı değil, aracının varlığı

Yol üzerinde **tek paket bile düşürmeyen** bir relay, 40 koşunun **39'unda** "atak"
işaretleniyor (R0 = **0.975**), 36'sında doğrudan `greyhole` deniyor. Saldırı yokken ve relay
de yokken taban 0.150. Yani **relay'in salt varlığı tespiti 0.150'den 0.975'e çıkarıyor
(+0.825)**; saldırının ekleyebileceği pay 0.025. Grey-hole tespit eğrisi pratikte bu tabanın
üstüne çıkmıyor — çıkamaz, çünkü taban zaten tavana yakın.

Bu kontrol deneyi şöyle kuruldu: grey-hole senaryosu `p = 0` ile koşuldu, yani aracı yol
üzerinde duruyor, paketleri alıp yeniden gönderiyor, ama **hiçbirini düşürmüyor**. Etiketi
`normal` de değil `greyhole` de değil; eğitim setine hiç girmiyor, yalnız değerlendiriliyor.
Böylece "modelin gördüğü şey saldırı mı, yoksa fazladan bir hop mu" sorusu doğrudan
ölçülebiliyor.

**Döngüsellik kontrolü yapıldı:** modele hem `p=0` hem `p=0.02` eğitimden çıkarılmış haliyle
soruldu; ikisi de aynı sınıfa gidiyor. Yani detektör "hiç düşürmeyen aracı" ile "%2 düşüren
aracı"yı ayıramıyor.

**Teslim zinciri (aynı 10 tohum üzerinde):** normal 0.9754 → zararsız relay 0.9023 → grey
p=0.02 0.8953. Relay'in salt varlığının bedeli −0.0731, saldırının kendi katkısı −0.0070.
**Sapmanın %91'i relay, %9'u saldırı.**

**Sonuç:** "grey-hole'ün %90'ını yakalıyoruz" gibi bir ifade yanlış çerçevededir. Model iki ayrı
yeteneği karıştırır: *topolojik anomali tespiti* ("ağda olmaması gereken bir aracı var" — bunda
neredeyse kusursuz) ve *saldırı tespiti* ("o aracı zarar veriyor" — bu eksende kör). Ayırmadan
verilen her tespit rakamı birincisini ikincisi diye satar.

*Ölçüm notu:* 40 koşunun ikisinde (24. ve 28. tohum) hiçbir şey düşürmeyen aracı **hiçbir şey
teslim etmiyor** (teslim 0.000 ve 0.045). Bunlar ağı bilerek tıkanma sınırına yakın yükleyen
kalibrasyonun kuyruğudur, ölçüm hatası değil, o yüzden dışarıda bırakılmadı. Bu yüzden taban
ortalama **0.829** ama medyan **0.883**, std **0.208** — ortalama tek başına yanıltıcıdır.
İlk 10 tohumda hiç çökme yoktu; bu, tabanın 10 koşuyla ölçülmesinin neyi sakladığını gösteriyor.

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
gerekiyor. Altında saldırı, zararsız relay'in kendi gürültüsüne gömülüyor.

Tablodaki iki sütun, aracının ağdaki konumunu değiştirmenin etkisini gösteriyor: STA8 erişim
noktasına en uzak düğüm, STA5 ise yakın olanlardan biri. İki konumda da çöküş aynı yerde
(p = 0.1) ama taban farklı — yani "hangi p'de görünür hale geliyor" sorusunun cevabı
topolojiden bağımsız, "ne kadar yanlış alarmla" sorusununki değil.

### 5.3 dos ↔ ddos ayrımı zayıf — model "kaç saldırgan"ı değil "ne kadar hasar"ı okuyor

İki sınıf çift yönlü karışıyor (F1 0.676 / 0.600).

Bir süre bunun **grid artefaktı** olduğu ve düzgün bir eğitim grid'iyle düzeltilebileceği
düşünüldü. Dayanağı şuydu: toplam yük 200 pkt/s'de sabit tutulup yalnız saldırgan sayısı
değiştirildiğinde doğru-tip oranı **0.925** çıkıyordu.

**O 0.925 rakamı iki ayrı sebeple geçersizdir.**

*Birincisi, ölçüldüğü kümenin bir kısmı eğitim verisiydi.* Bu kontrolün 40 koşusundan 15'i,
eğitim satırlarının birebir kopyasıydı (v1'in probe kusuru — bkz. Sürüm notu). Temiz bir
probe kümesiyle aynı kontrol **0.740 ± 0.028** veriyor. Düşüşün tamamını bu kusura yazmıyoruz:
içinde (a) örneklem-içi satırların çıkması, (b) yeni tohumlar, (c) tek yerine 20 model tohumu
üzerinden ortalama alınması var ve bunlar ayrıştırılmadı.

*İkincisi ve daha önemlisi, kontrolün kendi tasarımı hatalıydı* — aşağıdaki ölçümler bunu
gösteriyor. Kaldı ki 0.740'ın kendisi de tek bir sayı olarak yanıltıcı: **çöküşün tamamı
na=1 (0.45) ve na=2'de (0.51); na≥4'te ayrım kusursuz (1.00).** Yani "aynı yükü tek mi yoksa
sekiz kaynağa mı böldün" ayırt edilebiliyor, "tek mi iki mi" ayırt edilemiyor.

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

**Yapısal sebep:** FlowMonitor akış-başı transit ölçüyor, yani her akışın kendi gönderim–alım
farkını. Relay birinci akışı sonlandırıp ikincisini başlattığı için tutma süresi ikisinin
**arasında** kalıyor: ikinci akışın gönderim damgası tutma bittikten *sonra* atılıyor,
dolayısıyla transiti değişmiyor. Jitter de aynı sebeple kör — RFC 1889'un tanımı
`D(i,j) = (Rj−Ri) − (Sj−Si)`, ve sabit bir tutma transit sabitken tam olarak sıfırlanıyor.

`victim_startup_lag_ms` bu boşluğu kapatmak için eklendi: kurban kaynağının ilk gönderiminden
monitörün ilk alımına kadar geçen süre. Tutmayı gerçekten görüyor — eklenen gecikme 1 ms'den
200 ms'ye çıkarken **28.05 → 162.35 ms**, monoton. Ama ölçüm düzeltilse de karar doygun
olduğu için tespit değişmiyor.

*(Rapor taslaklarında bu çift üç farklı değerle geçiyordu — 23→145, 28→162, 29.4→272.9 — ve
üçü de en düşük gecikmeyi "0 ms" diye anıyordu. Sweep'in en düşük gecikmesi 1 ms'dir; doğru
çift yukarıdakidir.)*

### 5.5 Rakamlar bu topolojiye özgü

Relay'in konumu sonuçları belirgin şekilde değiştiriyor: erişim noktasına yakın konumda
(STA5, 10 m) zararsız relay'in teslim medyanı **0.969**, uzak konumda (STA8, 31.6 m) 0.902.
Yanlış alarm tabanı 0.225 ↔ 0.350 arasında oynuyor. **Her relay-tabanı rakamı, relay konumuyla
birlikte verilmelidir.**

*(Taslaklarda bu değer bir yerde 0.987 olarak geçiyor. O, konum deneyinin kendi içinde sonradan
geçersiz kıldığı bir ara değerdi — aynı ölçümde STA5 için doğru medyan 0.969'dur.)*

**"İki bağımsız konum" ifadesi fazla güçlüdür.** İki kol yalnız mesafede değil, düğüm
doluluğunda da farklı: koğuş çapraz trafiği STA3–STA7'yi kaynak olarak kullanıyor, STA8 ise
kendi trafiği olmayan **tek** düğüm. Yani STA5 ölçümü "relay + o düğümün kendi trafiği",
STA8 ölçümü ise yalnız relay. İkisinin farkı hem mesafeyi hem doluluğu içeriyor ve bu iki
etken ayrıştırılmadı.

### 5.6 Veri simülasyondur

Gerçek hastane ağından tek bir paket yoktur. Özellikle:

- Trafik **UDP**'dir; gerçek IoMT telemetrisi çoğunlukla MQTT/TCP üzerinden akar. Bu bilinçli bir
  sadeleştirmedir ve tıkanıklık kontrolü olan protokollerde davranış farklı olacaktır.
- Topoloji sabit 9 STA + 1 AP + 1 Hexoskin'dir; cihaz sayısı, hareketlilik ve girişim gerçek bir
  koğuşun çeşitliliğini yansıtmaz.
- Kaynak çalışmanın kendi yayımlanmış verisi üzerinde denendiğinde model **her şeyi** tek sınıfa
  eşliyor (yazarın `normal` koşuları dahil): ölçtüğü şey tespit değil **domain shift**. Yani bu
  model başka bir simülasyon kurulumuna bile aktarılamaz.

  Bu ölçüm bir başarısızlık raporu değil, iki ayrı sebeple **karşılaştırılamazlık** raporudur.
  *(a) O veride etiketler birbirinden geri kazanılamıyor:* yayımlanan 100 XML'in akış
  istatistikleri özetlendiğinde on tohumun hepsinde `normal` ile `mqtt` birebir aynı dosya,
  ve `dos` ile `ddos` ile `blackhole` birebir aynı dosya. Altı etiket, üç farklı ölçüm — o
  veride herhangi bir modelin çok-sınıflı macro-F1 tavanı yaklaşık **0.36**. *(b) Özellik
  aralıkları örtüşmüyor:* 12 özelliğin en az 6'sı eğitim aralığının tamamen dışında (örneğin
  akış yoğunlaşması bizde 0.446–0.931, orada 0.143–0.157). Ağaç toplulukları aralık dışına
  ekstrapolasyon yapamaz, bütün girdiler aynı yaprağa düşer.

  **Bu skoru yükseltmeye çalışmak yanlış olurdu:** elde edilecek her kazanç, birbirinin kopyası
  olan etiket gruplarına uydurmaktan gelirdi. Ölçüm bir **domain-shift probu** olarak
  raporlanmalıdır, bir benchmark olarak değil.

### 5.7 Yanlış-alarm bütçesine göre okunan eşik tablosu bilgi taşımaz

Detektör varsayılan eşiği yerine bir **yanlış alarm bütçesine** göre okunduğunda, "bütçe *b*'de
tespit oranı şu" biçiminde bir tablo çıkarılabiliyor. O tablonun **yanlış alarm sütunu
totolojiktir ve rapora konmamalıdır**: eşik, negatif koşuların skor dağılımının (1−*b*)
kuantilinden seçiliyor, sonra yanlış alarm **aynı 40 negatif koşu** üzerinde ölçülüyor.
Sonucun bütçeye eşit çıkması bir bulgu değil, seçim yönteminin tanımıdır.

Aynı sebep tablodaki **tespit oranlarını da iyimser** yapıyor: eşik ayrı bir doğrulama kümesi
üzerinde seçilmediği için, üzerinde ölçüldüğü kümeye uyarlanmış oluyor. Tablo kullanılacaksa
sütun "tanım gereği bütçeye eşittir" diye etiketlenmeli ve tespit oranları üst sınır olarak
sunulmalıdır.

### 5.8 Üretimde kullanılmamalıdır

§5.1–5.7 birlikte okunduğunda: bu model, ağda bir aracının **varlığını** güvenilir biçimde
saptıyor; o aracının **kötü niyetli olup olmadığını** ancak paketlerin %5–10'undan fazlası
düşürülüyorsa ayırt edebiliyor; zamanlama saldırılarını hiç göremiyor; ve rakamları eğitildiği
topolojiye bağlı. Klinik bir ortamda bağlayıcı kısıt yanlış alarm oranıdır ve buradaki taban
(0.225–0.350) üretim için fazlasıyla yüksektir.

---

## 6. Kullanım

```python
import joblib, json, pandas as pd

meta  = json.load(open("MANIFEST_v1.1.json"))
model = joblib.load("detector_v1.1.joblib")
feats = meta["model"]["features"]            # son eleman: monitor_missing

df = pd.read_csv("dataset_v1.1.csv")
X  = df[feats[:-1]].copy()
X["monitor_missing"] = df["monitor_owd_ms"].isna().astype(int)
model.predict(X.fillna(0.0))
```

Depo içinden çalışıyorsanız bu hazırlığı elle tekrarlamayın: `my-work/detector_schema.py`
aynı işi yapan `build_X()` fonksiyonunu tutuyor ve `check_against_release()` ile şemanın
yayımlanan modelle aynı olduğunu — **sütun sırası dahil** — doğruluyor. Sıra önemlidir:
scikit-learn eğitim ve tahmin sütunlarını konumsal eşler, sırası bozuk bir liste şikâyet
etmeden yanlış tahmin üretir.

**İki uyarı:**

1. `joblib` dosyaları **sürüme duyarlıdır**. Farklı bir scikit-learn altında yüklenmeyebilir veya
   sessizce farklı davranabilir. Release'in kullandığı sürümler `MANIFEST_v1.json` →
   `environment` altındadır; `freeze_release.py --check` uyuşmazlığı bildirir.
2. `joblib`/`pickle` yüklerken **kod çalıştırır**. Yalnız kendi ürettiğiniz veya güvendiğiniz
   dosyaları açın.

**Bütünlük doğrulaması:**

```bash
python3 freeze_release.py --version v1.1 --check
```

Bu komut yalnız dosya özetlerini değil, **provenance iddiasını da** yeniden kontrol eder: özet
bir dosyanın dondurulan dosya olduğunu kanıtlar, üzerindeki notun doğru olduğu hakkında hiçbir
şey söylemez. Kusurlu v1 sürümü arşivde bırakıldı ve aynı komutla **hâlâ kalıyor** — kapının
çalıştığının kalıcı kanıtı olarak.

## 7. Yeniden üretim

| adım | komut |
|---|---|
| Ham XML üretimi | `run_sweep.py --jobs 6` |
| XML → veri seti | `build_dataset.py --manifest manifest.csv --outdir out` |
| XML → prob kümesi | `build_dataset.py --manifest manifest_probes.csv --outdir out_probes` |
| Dondurma | `freeze_release.py --version v1.1` |
| Rapor rakamları | `report_numbers.py` |

**Uyarı — bu zincir commit'li ağaçtan olduğu gibi çalışmaz.** Ara çıktı klasörleri (`raw/`,
`out/`, `out_probes/`) ve sweep manifestleri depo dışında tutuluyor, çünkü her koşumda yeniden
üretiliyorlar. Yayımlanan artefaktlardan başlayan bir okuyucu için bağlayıcı olan
`MANIFEST_v1.1.json`'daki özetlerdir; zinciri baştan koşturmak isteyen önce sweep'i
çalıştırmak zorundadır (~35 dk, 6 çekirdek).

Değerlendirme notebook'ları: `my-work/day5-10072026-detector/01–10`. Rapordaki her sayı
`my-work/report_numbers.json`'dan gelir; o dosyayı üreten betik bu kartla aynı şemayı ve aynı
dondurulmuş sürümü kullanır.

## 8. Atıf

Bu çalışma, aşağıdaki çalışmanın senaryolarını temel alır ve onun atıflanmasını gerektirir:

> IoMT-NetworkAttackScenarios18 — Zenodo DOI `10.5281/zenodo.16747386`

**Not:** senaryolar temel alınmış ancak yeniden yazılmıştır (gerçekçi gürültü tabanı, çalışan DDoS,
gerçek on-path grey-hole). Kaynak çalışmanın yayımlanmış çıktıları bu modelin eğitiminde
kullanılmamıştır; yalnız domain-shift probu olarak sınanmıştır (§5.6).
