# IoMT Ağlarında Saldırı Tespiti — Özet Rapor

**Okan Koca**
**Temmuz 2026 · Kaynak çalışma: Zenodo DOI 10.5281/zenodo.16747386**

---

## 1. Problem

Hastanelerde kullanılan tıbbi cihazlar (infüzyon pompaları, hasta başı monitörleri,
giyilebilir EKG sensörleri) ölçtükleri veriyi kablosuz ağ üzerinden bir monitöre gönderir.
Bu verinin zamanında ve eksiksiz ulaşması klinik bir gerekliliktir.

Bu cihazlara güvenlik yazılımı eklemek çoğunlukla mümkün değildir: donanımları sınırlıdır ve
klinik sertifikasyon süreçleri yazılımlarına müdahaleyi engeller. Dolayısıyla savunma **ağ
tarafında** kurulmalıdır — cihazlara dokunmadan, yalnızca ürettikleri trafiğe bakarak.

**Bu çalışmanın sorusu:** ağ trafiğinin ölçülebilir özelliklerinden (teslim oranı, throughput,
gecikme, akış sayısı) bir saldırının varlığı ve türü anlaşılabilir mi?

Gerçek bir hastane ağında kontrollü saldırı denemesi yapılamayacağı için çalışma **NS-3 ağ
simülatöründe** yürütülmüştür. Simülasyonun karşılığı, gerçek bir ölçümün veremeyeceği iki
şeydir: her koşunun etiketi kesindir, ve her koşu birebir tekrar üretilebilir.

## 2. Teslim edilenler

| # | çıktı | durum |
|---|---|---|
| 1 | Çalışan NS-3 kurulumu, mevcut bir saldırının yeniden üretimi | tamamlandı |
| 2 | Etiketli ağ trafiği veri seti (normal + saldırılar) | 285 koşu, 5 sınıf |
| 3 | Saldırıyı tespit eden ve türünü belirleyen model + tespit–şiddet eğrisi | makro-F1 0.788 |
| 4 | Kaynak çalışmada bulunmayan yeni, sessiz bir saldırı | grey-hole, F1 0.958 |

## 3. Kurulan sistem

**Simüle edilen ağ.** 9 Wi-Fi istasyonu, bir erişim noktası ve bir giyilebilir sensör.
Çalışmanın merkezindeki akış, bir EKG dalga formunun hasta başı monitörüne ulaşmasıdır
(128 kbps, 128 baytlık paketler — gerçek klinik telemetri profili). Arka planda dört tıbbi
cihaz ve bir görüntüleme geçidi trafiği vardır.

**İki tasarım kararı sonuçların tamamını etkilemiştir.**

*Taban gürültüsü kalibre edildi.* Devralınan simülasyon belirlenimliydi: saldırı olmayan
koşularda teslim oranı **tam olarak 1.0**, koşular arası varyans **sıfır**. Böyle bir tabanda
en küçük bozulma bile sonsuz anlamlı görünür; model yüksek skor alır ama bu skor ağın değil
kurulumun yapaylığını ölçer. Ağa gerçekçi bir gürültü tabanı kazandırılmıştır (teslim oranı
artık 0.970 ± 0.032).

Bu kalibrasyon sırasında beklenmedik bir bulgu çıkmıştır: kablosuz bağlantıya hata enjekte
etmek teslim oranını hiç hareket ettirmemektedir, çünkü 802.11'in MAC katmanı bozulan
çerçeveyi yeniden gönderir. Teslim oranını gerçekten düşürebilen tek mekanizma
**tıkanıklıktır** — dolu bir kuyruktan atılan paketin yeniden gönderilecek bir kopyası
yoktur. Arka plan yükü bu nedenle doyum noktasının iki yanına düşecek biçimde ölçülerek
seçilmiştir.

*Örneklem birimi koşudur, akış değil.* Veri setinin her satırı bir simülasyon koşusudur ve o
koşudaki bütün akışların özetini taşır. Sebep: "bu ağda saldırı var mı" sorusu tek bir akışa
bakılarak yanıtlanamaz — DDoS'un tanımı zaten birden çok akışın birlikte davranmasıdır. Ayrıca
bu seçim, "aynı koşunun verisi hem eğitimde hem testte olmasın" kuralının ihlalini **yapısal
olarak imkânsız** kılar.

**Model.** Tek bir çok-sınıflı Random Forest; koşu başına 13 sayısal girdi. "Saldırı var mı"
sorusu ayrı bir model değil, çok-sınıflı çıktının türevidir (`normal` dışındaki her tahmin bir
alarmdır), böylece iki çıktının birbiriyle çelişmesi mümkün değildir.

**Değerlendirme.** Şiddet ekseni olan saldırılarda (`dos`, `ddos`, `greyhole`) aynı ayarın
bütün koşuları eğitim/test bölmesinin **tek bir tarafında** tutulmuştur. Sonuç: model test
edilirken **daha önce hiç görmediği bir saldırı şiddetiyle** karşılaşır. Bu sınav, rastgele
bölmeye göre skoru 0.828'den 0.788'e düşürmektedir.

`normal` ve `blackhole` bu kuralın dışındadır ve bunun sebebi zorunludur: taranacak bir
şiddet parametreleri, dolayısıyla tek bir konfigürasyonları vardır. Hepsi tek grup sayılsaydı
sınıf tek bir kata yığılır, kalan dört katta hiç örneği bulunmazdı. Bu iki sınıfta grup
koşunun kendisidir. Pratik sonucu, aşağıdaki tablonun okunmasını değiştirir: `greyhole`'ün
0.958'i **görülmemiş bir şiddetle**, `blackhole`'ün 0.952'si ise eğitimde görülmüş tek
konfigürasyonla ölçülmüştür. İkisi aynı zorlukta sınav değildir.

## 4. Kaynak çalışmanın doğrulanması

Çalışma mevcut bir NS-3 çalışmasının üzerine kurulmuştur. Senaryoları kullanmadan önce
derlenip koşulmuş ve **ağı fiilen değiştirip değiştirmedikleri** ölçülmüştür. Bir saldırı
senaryosunun çalıştığının kanıtı hatasız derlenmesi değil, ürettiği trafiğin normalden
ölçülebilir biçimde farklı olmasıdır.

| senaryo | ölçülen sonuç | durum |
|---|---|---|
| DoS | saldırı akışında 2900 paket, gerçek flood | çalışıyor |
| DDoS | hiç saldırı akışı yok — saldırgan düğümlere ağ arayüzü takılmamış | etkisiz |
| MITM | yalnızca 36 baytlık yönetim çerçevelerini görüyor, tıbbi veriye dokunmuyor | amaçlananı yapmıyor |
| Blackhole | akışlar normalle aynı, **kayıp 0** — filtre L2 adresi ile L3 adresi karşılaştırıyor | hiçbir şey düşürmüyor |
| MQTT-flood | koşulmadı (kaynağı derlenmeyen `blocksec` klasöründe); yayımlanmış çıktısı `normal` ile özdeş | dolaylı olarak etkisiz |

Koşulabilen dört saldırıdan **yalnızca biri** amaçladığı etkiyi üretmektedir. Bozuk bir senaryodan üretilen veriyle
eğitilen model, "saldırı" etiketli ama saldırı içermeyen koşular öğrenir. Bu nedenle senaryolar
**yeniden yazılmıştır**; kaynaktan devralınan şey topoloji, trafik deseni ve saldırı kurma
kalıplarıdır.

Aynı sonuç ikinci bir yoldan da doğrulanmıştır: kaynak çalışmanın yayımladığı ölçüm
dosyalarından öznitelik çıkarıldığında, 60 koşu yalnızca **30 eşsiz vektör** vermektedir.
`dos`, `ddos` ve `blackhole` 10 tohumun 10'unda da birbirinden **ayırt edilemez**; aynı şey
`mqtt` ile `normal` için de geçerlidir. Yani altı etiket, üç ölçüm. Bu kanıt senaryo kodu hiç
okunmadan, yalnızca kaynağın kendi çıktılarından gelmektedir.

## 5. Sonuçlar

**Saldırı var mı?** 255 koşu üzerinde, görülmemiş şiddetlerle sınandığında:

| | tahmin: normal | tahmin: saldırı |
|---|---|---|
| **gerçek: normal** | 34 | 6 |
| **gerçek: saldırı** | 11 | 204 |

Saldırı F1 = **0.960**, yanlış alarm oranı **0.150**.

**Hangi saldırı?**

| sınıf | F1 | koşu |
|---|---|---|
| `greyhole` | **0.958** | 110 |
| `blackhole` | **0.952** | 10 |
| `normal` | 0.800 | 40 |
| `dos` | 0.676 | 70 |
| `ddos` | 0.600 | 25 |
| **makro-F1** | **0.797** | 255 |

*(Buradaki 0.797 **havuzlanmış** değerdir: beş katın bütün tahminleri tek bir tabloda
toplanır ve sınıf başına metrikler bundan üretilir. Yukarıda ve sonuçta geçen 0.788 ise
**kat ortalamasıdır** (± 0.094) ve sonucun ne kadar oynak olduğunu gösterir. İki sayı aynı
tahminlerin iki farklı özetidir, çelişki değildir.)*

Tablo ikiye ayrılıyor: **paket düşüren saldırılar güvenilir biçimde tanınıyor**, **hacim
saldırıları tanınmıyor**. `dos` ve `ddos` çift yönlü karışmaktadır — bu, bir eşik sorunu değil
iki sınıfın öznitelik uzayında ayrışmadığı anlamına gelir (§7).

![Şekil 1 — Karışıklık matrisi. Satır: gerçek sınıf, sütun: tahmin.](../day5-10072026-detector/figs/G-confusion-honest.png)

**Tespit–şiddet eğrisi.** Saldırı zayıfladıkça tespitin nereye kadar dayandığı:

| saldırı | şiddet | tespit |
|---|---|---|
| `dos` | 100–1000 pkt/s | 1.00 |
| `dos` | 50 pkt/s | 0.80 |
| `dos` | 20 pkt/s | 0.70 |
| `dos` | 10 pkt/s | 0.40 |
| `dos` | **2 – 5 pkt/s** | **0.20** ← taban 0.150 |
| `greyhole` | `p` = 0.02 – 0.9 | 1.00 (hepsinde) |
| `ddos` / `blackhole` | tüm şiddetler | 1.00 |

Gerçek bir çöküş eğrisi olan tek kol `dos`'tur, ve o kol **tabana kadar inmektedir**. 10
paket/s'de flood, tıkanmış ortamda meşru trafiğin kendi dalgalanmasının içinde kalmaktadır;
2–5 paket/s'de tespit oranı yanlış-alarm tabanına oturur, yani model artık saldırıyı
görmemekte, yalnızca saldırısız koşularda da yaptığı hatayı yapmaktadır. Bu noktada saldırının
teslim oranında ve throughput'ta bıraktığı iz, `normal`'in kendi dalgalanmasının **onda biri**
kadardır (−0.10 σ ve −0.04 σ).

Diğer üç kolun eğrisi düzdür — grey-hole, paketlerin yalnızca %2'sini düşürdüğünde bile
kusursuz tespit edilmektedir.

**Bu son cümle gerçek olamayacak kadar iyidir, ve nedeni bu çalışmanın asıl bulgusudur.**

## 6. Yeni saldırı: grey-hole

Kaynak çalışmanın bütün saldırıları gürültülüdür; yakalanmaları için makine öğrenmesine gerek
yoktur. Eklenen saldırı **grey-hole**'dür: yol üzerindeki ele geçirilmiş bir düğüm, paketlerin
tamamını değil `p` olasılıkla **bir kısmını** düşürür, gerisini iletir. Ağ çalışıyor görünmeye
devam ettiği için sessizdir, ve `p` doğal bir şiddet ekseni verir.

**Kritik tasarım kararı:** saldırgan gerçekten yolun üzerinde olmalıdır. Kaynak çalışmanın
blackhole'ü hiçbir paket düşürmemektedir çünkü saldırgan düğüm yönlendirme yolunda değildir —
bu, geri çağrımı düzelterek çözülebilecek bir sorun değildir. Bu nedenle grey-hole, ağ yoluna
fiilen yerleşen bir uygulama olarak yazılmıştır:

```
EKG kaynağı  --UDP-->  grey-hole relay  --UDP-->  monitör
                             |
                        p olasılıkla düşür
```

**Saldırının çalıştığı doğrulanmıştır.** Teslim oranı `p` ile tekdüze düşmekte ve iki uçta
beklenen değerleri vermektedir:

| `p` | ölçülen teslim | beklenen (`1 − p`) |
|---|---|---|
| — (`normal`, ağda aracı yok) | 0.970 | 1.00 |
| 0.10 | 0.826 | 0.90 |
| 0.50 | 0.458 | 0.50 |
| 0.90 | 0.091 | 0.10 |
| 1.00 | 0.000 | 0.00 |

`p = 1` verildiğinde aynı kod **çalışan bir blackhole** olur — kaynak çalışmanın çalışmayan
blackhole'ünün yerine geçen budur.

Sınıflandırma tarafında grey-hole, veri setindeki **en güvenilir tanınan saldırı sınıfıdır**
(F1 0.958).

## 7. Asıl bulgu: detektör neyi ölçüyor?

§5'teki rakamlar doğrudur, ama sordukları soru sanıldığı soru değildir.

**Kontrol deneyi.** Grey-hole eğrisinin neden düz olduğunu anlamak için saldırı ağdan
çıkarılıp **aracı yerinde bırakılmıştır**: gelen her paketi düşürmeden, geciktirmeden ileten
bir aracı düğüm. Bu konfigürasyon hiç eğitilmemiş, yalnızca ölçülmüştür.

| ölçüm | değer |
|---|---|
| yanlış-alarm tabanı (aracı yok, saldırı yok) | 0.150 |
| **aracı var, saldırı yok** | **0.975** |
| aracının tek başına eklediği tespit | **+0.825** |
| **saldırıya kalan pay** | **0.025** |

**Hiçbir zararlı davranışı olmayan bir aracı, 40 koşunun 39'unda saldırı alarmı
üretmektedir** — ve 36'sına özellikle `greyhole` demektedir.

Aynı sonuç öznitelik uzayında da görülmektedir. Bu kez ölçülen şey tespit oranı değil
**teslim oranıdır**; kurban yolu üç aşamada, üç kolun da paylaştığı tohumlar üzerinden:
aracı yok **0.9754** → aracı var ama zararsız **0.9023** → aracı var ve saldırı açık
**0.8953**. Yani düşüşün **%91'i aracının salt varlığından, %9'u saldırıdan** gelmektedir.

**Sonuç:** detektörün fiilen yanıtladığı soru *"bu ağda beklenmedik bir aracı var mı?"*dır —
*"bu aracı kötü niyetli mi?"* değil.

**Doğru soru sorulduğunda gerçek bir eğri ortaya çıkıyor.** Bu bir kusur değil, iki sorunun
ayrılması gerektiğidir. Ayrım `normal`'e karşı değil **zararsız aracıya** karşı ölçüldüğünde:

![Şekil 2 — Zararsız aracıya karşı ayrım. Taralı alan saldırının tabanın üstüne çıkan gerçek katkısıdır.](../day5-10072026-detector/figs/M-zararsiz-relaye-karsi-ayrim.png)

| `p` | tespitin taban üstüne çıkan payı |
|---|---|
| 0.02 | 0.05 — saldırı görünmüyor |
| 0.05 | 0.35 — geçiş bölgesi |
| **0.10** | **0.55 — ayrım netleşiyor** |
| 0.20 – 0.90 | 0.65 |

**Çöküş noktası `p = 0.1`'dir** ve aracının konumu değiştirildiğinde de aynı çıkmaktadır.

**Aynı desen iki kez daha tekrar ediyor.** `ddos` sınıfı pratikte "saldırgan sayısı çok" değil
**"hasar çok"** anlamına gelmektedir: gerçekleşen hasar eşitlendiğinde `dos`/`ddos` ayrımı
0.662'den **0.475**'e düşmektedir (şans 0.500). Benzer biçimde, paketleri düşürmeyip geciktiren
bir saldırı sınıf olarak eğitildiğinde model, **hiçbir şey yapmayan** aracıya koşuların
%80'inde o saldırının adını vermektedir.

**Üçünün ortak açıklaması:** akış seviyesinde ölçülen özet büyüklükler, saldırganın
**niyetini** değil kullandığı **mekanizmayı** görür. Bu aynı zamanda "daha çok saldırı
ekleyelim" önerisinin neden bilgi katmadığının cevabıdır: bu ölçüm düzeyinde UDP flood, MQTT
flood ve sahte bir cihaz aynı olaydır.

## 8. Sınırlılıklar

1. **İkili tespit doygundur** — ölçtüğü şey saldırı değil, aracının varlığıdır.
2. **Grey-hole `p < 0.1`'in altında görünmez.** Telemetrinin %2'sini düşüren bir saldırgan
   yakalanamamaktadır.
3. **`dos`/`ddos` ayrımı güvenilir değildir**; bu model bu ayrım için kullanılmamalıdır.
4. **Zamanlama saldırıları akış seviyesinde görünmez** — ölçüm katmanının yapısal kısıtı.
5. **Rakamlar bu topolojiye özgüdür.** Aracının konumu yanlış-alarm tabanını 0.225 ile 0.350
   arasında değiştirmektedir. Taşınabilir olan yöntemdir, mutlak değerler değil.
6. **Veri simülasyondur** ve trafik UDP'dir; gerçek IoMT telemetrisi çoğunlukla MQTT/TCP
   üzerinden akar.
7. **Bu model üretimde kullanılmamalıdır.** Çalışmanın çıktısı bir ürün değil, bir ölçüm
   yöntemi ve o yöntemin ne ölçtüğüne dair bir soruşturmadır.

## 9. Sonuç

Bir IoMT ağının NS-3 modeli üzerinde 285 koşuluk etiketli bir veri seti üretilmiş, saldırı
varlığını ve türünü belirleyen bir detektör eğitilmiş, ve kaynak çalışmada bulunmayan sessiz
bir saldırı gerçeklenip detektöre karşı sınanmıştır. Kaynak çalışmanın senaryoları
kullanılmadan önce doğrulanmış, üçünün etkisiz olduğu ölçülmüş ve senaryolar yeniden
yazılmıştır.

Sayısal sonuçlar: makro-F1 **0.788**, ikili saldırı-F1 **0.960**, yeni saldırının tanınma
skoru **0.958**.

Çalışmanın asıl katkısı bu skorlar değil, **skorların ne ölçtüğünü soran kontrol
deneyleridir**. Ağ yoluna yerleştirilmiş ama hiçbir zararlı davranışı olmayan bir aracının
detektörü 40 koşunun 39'unda alarma geçirmesi, tespit edilen şeyin büyük ölçüde saldırı değil
**ağ yapısındaki bir değişiklik** olduğunu göstermektedir. Soru doğru biçimde yeniden
sorulduğunda ölçülebilir ve anlamlı bir çöküş eğrisi ortaya çıkmaktadır.

**Bir sonraki adım**, detektörü baştan bu soruya göre kurmaktır: pozitif sınıf "zararlı
aracı", negatif sınıf "zararsız aracı" — `normal` değil.

---

*Bu belge, ayrıntılı teknik raporun özetidir. Raporda geçen her sayısal sonuç tek bir
kaynaktan üretilmiştir ve elle kopyalanmamıştır. Kod, veri seti ve eğitilmiş model `v1.1`
etiketiyle dondurulmuştur.*
