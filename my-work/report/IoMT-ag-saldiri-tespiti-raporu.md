# IoMT Ağlarında Saldırı Tespiti: Simülasyon, Veri Seti ve Makine Öğrenmesi Detektörü

**Yazar:** Okan Koca
**Tarih:** Temmuz 2026
**Kod ve veri:** `github.com/<kullanıcı>/IoMT-NetworkAttackScenarios18`, sürüm `v1.1`

---

## Özet

Bir tıbbi cihazın hasta verisini kablosuz ağ üzerinden bir monitöre akıttığı ortamda, aynı ağ
üzerindeki bir saldırganın bu akışı bozması ya da değiştirmesi mümkündür. Bu çalışma, böyle bir
ortamı NS-3 ağ simülatöründe kurar, normal ve saldırı altındaki trafiği etiketli bir veri
setine dönüştürür, ve bu veriden hem "saldırı var mı" hem "hangi saldırı" sorularını yanıtlayan
bir makine öğrenmesi detektörü eğitir. Çalışma, DoS, DDoS, MITM, Blackhole ve MQTT-flood
saldırılarını simüle eden mevcut bir NS-3 çalışmasının üzerine kurulmuştur (Zenodo:
`10.5281/zenodo.16747386`) ve ona bir de **yeni, sessiz bir saldırı** ekler.

Üretilen veri seti **285 simülasyon koşusu** içerir; her koşu beş sınıftan birine aittir
(`normal`, `dos`, `ddos`, `greyhole`, `blackhole`) ve koşu başına 13 sayısal özellikle
temsil edilir. Konfigürasyon-grupli, iyimserliği kırılmış bir değerlendirme altında detektörün
çok-sınıflı makro-F1 skoru **0.788 ± 0.094**, ikili (saldırı var/yok) F1 skoru **0.960**'tır.
Yeni saldırı olarak seçilen **grey-hole (seçici iletmeme)** güvenilir biçimde tanınmaktadır
(F1 **0.958**). Buna karşılık `dos` ve `ddos` sınıfları birbirine karışmaktadır (F1 0.676 /
0.600) ve bu raporun bir bölümü bunun neden bir eğitim eksikliği değil, ölçüm tasarımının
yapısal bir sonucu olduğunu göstermeye ayrılmıştır.

Çalışmanın asıl bulgusu bir skor değildir. Saldırganı ağ yoluna gerçekten yerleştiren bir
kontrol deneyi, **hiçbir şey yapmayan** — tek bir paket bile düşürmeyen — bir aracı düğümün
tek başına detektörü %97.5 oranında alarma geçirdiğini göstermektedir. Yani detektörün
saldırıyı tespit ettiği sanılan yerde ölçtüğü şey büyük ölçüde **saldırının kendisi değil,
ağ yolunda fazladan bir aracının bulunmasıdır**. Aynı desen üç yerde birden tekrar eder ve
raporun §8'i bu desenin kendisini konu alır.

---

## Bu belge nasıl okunur

Bölümler birbirine dayanacak şekilde sıralanmıştır: önce simüle edilen ağ, sonra o ağdan
hangi büyüklüklerin ölçüldüğü, sonra bu büyüklüklerin nasıl bir veri setine dönüştüğü, ancak
ondan sonra model. Her bölüm, ne kurduğunu ve neden gerekli olduğunu söyleyen kısa bir
paragrafla açılır; yalnızca bu açılış paragraflarını okuyan biri de çalışmanın tamamını
takip edebilir.

Teknik terimlerin bir kısmı İngilizce bırakılmıştır (*throughput*, *jitter*, *flow*,
*grey-hole*). Sebebi, bu terimlerin Türkçe karşılıklarının alanda yerleşmemiş olması ve
zorlama çevirilerin anlamı belirsizleştirmesidir. Her biri ilk geçtiği yerde tanımlanır;
tamamı **Ek A — Terimler Sözlüğü**'nde toplanmıştır.

Raporda geçen her sayısal sonuç tek bir kaynaktan üretilmiştir (`my-work/report_numbers.py`
→ `report_numbers.json`) ve elle kopyalanmamıştır. Bunun neden bir ayrıntı değil bir yöntem
kararı olduğu §10'da açıklanmaktadır.

---

## 1. Giriş

### 1.1 Problem

**IoMT (Internet of Medical Things)**, hastanelerde ve evde bakımda kullanılan, ölçtüğü veriyi
bir ağ üzerinden başka bir yere gönderen tıbbi cihazların ortak adıdır: infüzyon pompaları,
hasta başı monitörleri, giyilebilir EKG ve solunum sensörleri. Bu cihazların ortak özelliği,
ürettikleri verinin **zamanında ve değişmeden** ulaşmasının klinik bir gereklilik olmasıdır.
Gecikmiş ya da eksik bir ölçüm, yalnızca bir veri kaybı değil, yanlış bir klinik karara
dayanak olabilir.

Bu cihazlar aynı zamanda savunması en zayıf ağ bileşenleridir. Çoğu sınırlı işlemci ve
bellekle çalışır, güncelleme alması üreticiye ve hastane prosedürlerine bağlıdır, ve klinik
sertifikasyon süreçleri nedeniyle yazılımlarına müdahale edilmesi kolay değildir. Yani
korumayı **cihazın içine** koymak çoğu durumda mümkün değildir.

Bu, savunmayı doğal olarak **ağ tarafına** taşır. Cihazlara dokunulamıyorsa, cihazların
ürettiği trafik tek bir noktadan gözlenebilir ve trafiğin kendisindeki bozulmadan saldırının
varlığı çıkarılabilir. Bu çalışmanın konusu tam olarak budur: **ağ trafiğinin ölçülebilir
özelliklerinden saldırı tespiti.**

### 1.2 Neden simülasyon

Gerçek bir hastane ağında kontrollü saldırı denemesi yapmak mümkün değildir; hem hasta
güvenliği hem de etik ve yasal kısıtlar bunu engeller. Ayrıca makine öğrenmesi için gerekli
olan şey yalnızca "saldırı altındaki trafik" değil, **etiketli** ve **tekrarlanabilir**
trafiktir: hangi koşunun hangi saldırıyı, hangi şiddette içerdiğinin kesin olarak bilinmesi
gerekir. Gerçek bir ortamda bu etiket ancak varsayımla üretilebilir.

Bu nedenle çalışma **NS-3** ağ simülatörü üzerinde yürütülmüştür. NS-3, paket seviyesinde
ayrıklı-olay simülasyonu yapan, akademik olarak yerleşik açık kaynaklı bir simülatördür;
Wi-Fi fiziksel katmanını, MAC kuyruklarını ve yönlendirmeyi ayrı ayrı modeller. Simülasyonun
karşılığında verdiği şey, bir gerçek ölçümün asla veremeyeceği iki şeydir: **her koşunun
etiketi kesindir** ve **her koşu tohum (seed) verilerek birebir tekrar üretilebilir**.

Karşılığında ödenen bedel de açıktır ve bu rapor onu saklamaz: simülasyon, gerçek bir hastane
ağının bütün karmaşıklığını içermez. Bunun sonuçlarımızı nasıl sınırladığı §9'da ayrıntısıyla
tartışılmaktadır.

### 1.3 Ne yapılması istendi

Çalışmanın dört teslim edilebilir çıktısı vardır:

1. Mevcut bir saldırı senaryosunu yeniden üreten, çalışır bir NS-3 kurulumu.
2. Simülasyonlardan çıkarılmış, **etiketli bir ağ trafiği veri seti** (normal + saldırılar).
3. Saldırı olup olmadığını işaretleyen ve **saldırı tipini** belirleyen bir makine öğrenmesi
   detektörü; yanında **tespit–saldırı şiddeti eğrisi**.
4. Kaynak çalışmada bulunmayan, **yeni ve sessiz bir saldırının** NS-3'te gerçeklenmesi ve
   detektöre karşı sınanması.

### 1.4 Ne yapıldı — sonuçların özeti

Dördü de üretilmiştir. Kısaca:

- **Simülasyon tabanı.** Kaynak çalışmanın senaryo dosyaları temel alınmış, ancak
  doğrulandıktan sonra **yeniden yazılmıştır** — nedeni §2'de ayrıntısıyla verilen ampirik bir
  bulgudur: dosyaların üçünde saldırı fiilen gerçekleşmemektedir. Ayrıca senaryolara komut
  satırı parametreleri ve tohum yönetimi eklenmiş, ölçülebilir bir taban gürültüsü
  kalibre edilmiştir (§3).
- **Veri seti.** 285 koşu, 5 sınıf, koşu başına 13 model girdisi. Sınıf dağılımı:
  `greyhole` 110, `dos` 100, `normal` 40, `ddos` 25, `blackhole` 10 (§4).
- **Detektör.** Tek bir çok-sınıflı Random Forest. Dürüst, konfigürasyon-grupli çapraz
  doğrulama altında makro-F1 **0.788 ± 0.094**; ikili görünümde saldırı-F1 **0.960**, yanlış
  alarm oranı **0.150**. Sınıf bazında: `greyhole` 0.958, `blackhole` 0.952, `normal` 0.800,
  `dos` 0.676, `ddos` 0.600 (§5, §6).
- **Yeni saldırı.** Ağ yoluna gerçekten yerleşen, paketleri `p` olasılığıyla düşüren bir
  **grey-hole** relay'i gerçeklenmiştir. `p` doğal bir şiddet ekseni verir ve tespit–şiddet
  eğrisi bunun üzerine kurulmuştur. İkinci bir saldırı — paketleri düşürmeyip **geciktiren**
  bir *timing-MITM* — de gerçeklenmiş, fakat sınıf olarak modele dahil edilmemiştir; sebebi
  bir başarısızlık değil, ölçüm katmanının yapısal bir körlüğüdür ve kendi başına bir bulgudur
  (§7).

### 1.5 Raporun asıl iddiası

Bu rapor, "yüksek bir skor elde edildi" iddiası üzerine kurulu değildir. Yukarıdaki skorların
her biri, **ne ölçtükleri sorulduğunda** farklı bir anlam kazanmaktadır.

Çalışmanın merkezindeki kontrol deneyi şudur: saldırganı ağ yoluna yerleştiren ama ona
**hiçbir zararlı davranış vermeyen** bir konfigürasyon koşulmuştur — gelen her paketi
düşürmeden, geciktirmeden, değiştirmeden ileten bir aracı. Detektör bu 40 koşunun **39'unu**
saldırı olarak işaretlemektedir. Yani "saldırı tespit edildi" çıktısının büyük kısmı,
saldırının kendisinden değil, **ağ yolunda fazladan bir düğüm bulunmasından** kaynaklanmaktadır.

Aynı desen bağımsız olarak üç kez ortaya çıkar: `ddos` sınıfı pratikte "saldırgan sayısı çok"
değil "hasar çok" anlamına gelmekte, `mitm` sınıfı ise "paket düşürmeyen aracı" anlamına
gelmektedir. Üçünün ortak açıklaması, akış seviyesinde ölçülen özet büyüklüklerin
**saldırganın niyetini değil kullandığı mekanizmayı** görmesidir. Bu bulgu §8'de bir araya
getirilmiştir ve raporun ana katkısı olarak sunulmaktadır.

---

## 2. Dayanak çalışma ve doğrulanması

> Bu bölüm, çalışmanın üzerine kurulduğu kaynağı tanıtır ve ondan ne alınıp neyin yeniden
> yazıldığını gerekçesiyle ortaya koyar. Gerekçe bir tercih meselesi değildir: kaynak
> senaryoların hangilerinin ağı fiilen değiştirdiği ölçülmüş, üçünün değiştirmediği
> görülmüştür. Aynı bölüm, kaynağın yayımlanmış ölçüm çıktılarının neden bir karşılaştırma
> ölçütü olarak kullanılamayacağını da gösterir.

### 2.1 Kaynak çalışma

Bu çalışma, **`ramamr33/IoMT-NetworkAttackScenarios18`** adlı NS-3 tabanlı simülasyon
çalışmasının üzerine kurulmuştur (Zenodo DOI: **`10.5281/zenodo.16747386`**). Kaynak çalışma,
bir tıbbi IoT ağında beş saldırı senaryosu simüle eder — DoS, DDoS, MITM, Blackhole ve
MQTT-flood — ve her senaryo için NS-3'ün **FlowMonitor** modülüyle toplanmış ölçüm çıktıları
yayımlar.

Kaynaktan devralınan şey **simülasyon tabanının kendisidir**: ağ topolojisi (9 Wi-Fi istasyonu,
bir erişim noktası, bir giyilebilir sensör düğümü), 802.11n Wi-Fi yapılandırması, UDP tabanlı
trafik deseni, ve saldırıların kurulduğu iki kod kalıbı — (a) saldırgan düğüme kötü niyetli bir
trafik uygulaması yerleştirmek (flood saldırıları), (b) saldırgan düğüme paket-işleme geri
çağrımı bağlamak (MITM, Blackhole). Bu iki kalıp, bu çalışmadaki yeni saldırının da temelidir.

### 2.2 Senaryoların ampirik doğrulanması

Kaynak çalışmanın senaryoları doğrudan kullanılmadan önce derlenip koşulmuş ve **ağı fiilen
değiştirip değiştirmedikleri** ölçülmüştür. Bu, "kurulum çalışıyor mu" kontrolünün ötesinde
bir adımdır: bir saldırı senaryosunun çalıştığının kanıtı, hatasız derlenmesi değil, ürettiği
trafiğin normal koşudan **ölçülebilir biçimde** farklı olmasıdır.

Sonuç, beş senaryodan ikisinin çalıştığı, üçünün çalışmadığı yönündedir:

| Senaryo | Amaçlanan davranış | Ölçülen sonuç | Durum |
|---|---|---|---|
| NORMAL | — | referans koşu | referans |
| **DoS** | Saldırgan istasyondan UDP flood | Saldırı akışında 2900 paket; gerçek bir flood | **çalışıyor** |
| **DDoS** | 5 saldırgan düğümden eşzamanlı flood | Yalnız 2 meşru akış, kayıp 0, **hiç saldırı akışı yok** | etkisiz |
| **MITM** | Saldırgan düğüm paket içeriğini değiştirir | Geri çağrım yalnızca 36 baytlık yönetim çerçevelerini görüyor; 512 baytlık tıbbi veriye hiç dokunmuyor | amaçlananı yapmıyor |
| **Blackhole** | Saldırgan hasta verisi paketlerini düşürür | Akışlar normalle aynı (2197 gönderilen / 1999 alınan, **kayıp 0**) | hiçbir şey düşürmüyor |

Üç arızanın kök nedenleri kodda doğrudan görülebilmektedir:

**DDoS — saldırgan düğümlerin ağ arayüzü yok.** Saldırgan düğümlere IP yığını kuruluyor,
fakat Wi-Fi cihazı takılmıyor ve IP adresi atanmıyor:

```cpp
attackerNodes.Create(numAttackerNodes);   // 5 düğüm
stack.Install(attackerNodes);             // yalnızca IP yığını
// wifi.Install(..., attackerNodes) yok; address.Assign(...) yok
```

Üzerlerinde bir UDP istemcisi çalışsa bile paketi gönderecek bir ağ cihazı ya da rota
bulunmadığından sessiz kalıyorlar.

**MITM — düğüm ağ yolunda değil, yalnızca pasif bir dinleyici.** Geri çağrım, MAC katmanının
`MacRx` izine bağlanmış durumda. Altyapı modundaki bir Wi-Fi ağında bir istasyonun MAC katmanı
üst katmana yalnızca **kendisine adreslenmiş** çerçeveleri verir; başkasına giden tıbbi veri
hiç görünmez. Üstelik geri çağrımın ilk satırı büyük paketleri zaten atlamaktadır:

```cpp
if (packet->GetSize() > 512) { return; }   // 512 baytlık tıbbi paketi baştan eliyor
Config::ConnectWithoutContext("/NodeList/10/DeviceList/0/Mac/MacRx", ...);
```

**Blackhole — iki ayrı hata üst üste.** Birincisi, filtre bir **katman-2 MAC adresini** bir
`InetSocketAddress` (katman-3 IP:port) ile karşılaştırıyor; tip uyuşmazlığı nedeniyle koşul
hiçbir zaman doğru olmuyor. İkincisi, saldırgan düğüme Wi-Fi cihazı takılmadığı için
`GetDevice(0)` geri döngü (loopback) arayüzünü veriyor ve geri çağrım Wi-Fi trafiğini hiç
almıyor:

```cpp
if (protocol == 17 && from == InetSocketAddress("192.168.1.2", 8080)) { // L2 ile L3 karşılaştırması
    return false;                                                       // hiçbir zaman çalışmaz
}
Ptr<NetDevice> attackerDevice = attacker->GetDevice(0);  // Wi-Fi yok → loopback
```

### 2.3 Bu bulgunun çalışmaya etkisi

Bu, kaynak çalışmayı geçersiz kılan bir eleştiri olarak değil, **bir tasarım kararının
gerekçesi** olarak sunulmaktadır. Sonuç şudur: senaryolar oldukları gibi kullanılamazlar,
çünkü üçü hiçbir saldırı üretmemektedir. Bozuk bir senaryonun ürettiği veriyle eğitilen bir
detektör, "saldırı" etiketli ama saldırı içermeyen koşular öğrenir — yani ölçtüğü şey
gürültüdür.

Bu nedenle senaryolar bu çalışmada **yeniden yazılmıştır**. Devralınan şey topoloji, trafik
deseni ve saldırı kurma kalıplarıdır; devralınmayan şey saldırıların gerçeklenmesidir. Aynı
karar, yeni saldırı için de belirleyici olmuştur: grey-hole, bozuk Blackhole geri çağrımı
düzeltilerek değil, **ağ yoluna gerçekten yerleşen bir aracı düğüm** yazılarak kurulmuştur
(§7.1).

Bir yan sonuç olarak, kaynak çalışmanın "Blackhole" senaryosunun hiçbir paket düşürmediği
tespiti, bu çalışmanın kendi `blackhole` sınıfının niçin ayrı gerçeklendiğini de açıklamaktadır.

### 2.4 Kaynağın yayımlanmış verisi neden bir ölçüt olarak kullanılamıyor

Detektörün bağımsız bir veri üzerinde sınanması amacıyla, kaynak çalışmanın **kendi
yayımladığı** FlowMonitor çıktılarından bu çalışmanın şemasıyla birebir uyumlu bir test seti
üretilmiştir (60 koşu). Test setini üreten kod, eğitim verisini üreten ayrıştırıcının
**aynısını** çağırır; ayrı bir ayrıştırıcı yazılsaydı özellik tanımları eğitim ile test
arasında kayar ve karşılaştırma anlamsızlaşırdı.

Üretilen veri incelendiğinde üç bağlayıcı bulgu ortaya çıkmıştır:

1. **Altı etiket, üç ölçüm.** Yayımlanan XML dosyaları özet (MD5) karşılaştırmasına
   sokulduğunda, `normal` ile `mqtt` koşularının ve `dos`, `ddos`, `blackhole` koşularının
   **10 tohumun 10'unda da birebir aynı dosyalar** olduğu görülmektedir. Yani altı farklı
   etiket, gerçekte üç farklı ölçüme karşılık gelmektedir. Bu, o veri üzerinde **herhangi bir
   modelin** ulaşabileceği makro-F1 skorunu yaklaşık **0.36** ile sınırlar — model kusursuz
   çalışsa bile, birbirinin kopyası olan iki koşuya farklı etiket veremez.
2. **Alan kayması (domain shift).** Kaynağın topolojisi koşu başına sabit 9 akış üretirken bu
   çalışmanınki 3–15 akış üretmektedir (normal koşularda 3–7); toplam throughput'un medyanı
   bu çalışmada kaynağınkinin yaklaşık **5 katıdır** (11.29 Mbps'e karşı 2.20 Mbps) ve port
   düzeni ayrıdır. Adlandırılmış 12 özelliğin **6'sı**, kaynağın 60 koşusunun tamamında
   eğitim verisinin değer aralığının **tümüyle dışında** kalmaktadır: `max_flow_throughput_mbps`,
   `max_flow_txpackets`, `flow_concentration`, `monitor_owd_ms`, `monitor_pdv_ms`,
   `victim_startup_lag_ms`. İki özellik daha kısmen dışarıdadır (`mean_owd_ms` %85,
   `mean_pdv_ms` %50). Karar ağacı toplulukları eğitim aralığının dışına **ekstrapolasyon
   yapamaz** — gördükleri son sınır değerine sabitlenirler — dolayısıyla bu girdilerin
   taşıdığı bilgi model için kullanılamaz durumdadır.
3. **Saldırı sinyali normal varyansın içinde.** Kaynağın verisinde saldırı koşularıyla normal
   koşular arasındaki fark yaklaşık %1 düzeyindedir; bu, bu çalışmanın normal koşularının
   kendi içindeki dalgalanmadan küçüktür.

Bu üç bulgu birlikte, kaynağın verisinin bir **doğruluk kıyaslaması** olarak kullanılamayacağını
göstermektedir. Bu çalışmada eğitilen detektör, o veri üzerinde `normal` etiketli koşular dahil
her şeyi tek bir sınıfa atamaktadır — ki bu, detektörün başarısızlığından çok, iki veri
kümesinin aynı ölçüm evreninde bulunmadığının göstergesidir. Dolayısıyla bu test seti raporda
bir **alan kayması probu** olarak sunulmakta, bir başarım ölçütü olarak sunulmamaktadır (§8.3).

Aynı zamanda §2.2'nin sonucunu bağımsız olarak desteklemektedir: `dos`, `ddos` ve `blackhole`
koşularının birebir aynı dosyalar olması, o üç senaryonun ağ üzerinde birbirinden farklı
hiçbir etki üretmediğinin ikinci bir kanıtıdır.

---

## 3. Simülasyon tabanı

> *(Yazılacak: topoloji ve trafik modeli; 802.11n yapılandırması; taban gürültüsünün neden ve
> nasıl kalibre edildiği — gürültüsüz bir tabanın tespit eğrisini nasıl düzleştirdiği;
> senaryolara eklenen komut satırı parametreleri ve tohum yönetimi.)*

## 4. Veri seti

> *(Yazılacak: "koşu" neden örneklem birimi seçildi; üç ölçüm modalitesi — hacim, teslim,
> zamanlama; 13 özelliğin tanımı ve hangi ham FlowMonitor büyüklüğünden türediği; şiddet
> eksenleri; eğitim sınıfı ile değerlendirme probu ayrımı ve kuralı.)*

## 5. Detektör ve değerlendirme yöntemi

> *(Yazılacak: model seçimi; konfigürasyon-grupli bölme nedir ve neden koşu-bazlı bölmeden
> daha sert bir sınavdır; iyimser bölmeyle farkı; hangi metriklerin neden raporlandığı.)*

## 6. Sonuçlar

> *(Yazılacak: ikili tespit; çok-sınıflı sınıf bazında sonuçlar; karışıklık matrisi;
> tespit–şiddet eğrisi; eşik ayarı.)*

## 7. Yeni saldırı

> *(Yazılacak: 7.1 grey-hole tasarımı, gerçeklenmesi ve doğrulanması; 7.2 timing-MITM ve
> akış seviyesi ölçümün yapısal körlüğü; 7.3 değerlendirilip reddedilen alternatifler.)*

## 8. Ne ölçtüğümüzü sorgulamak

> *(Yazılacak: 8.1 zararsız relay tabanı ve R0 = 0.975; 8.2 dos/ddos ayrımının hasar eksenine
> indirgenmesi; 8.3 alan kayması probu; 8.4 üç bulgunun ortak açıklaması.)*

## 9. Sınırlılıklar

> *(Yazılacak.)*

## 10. Yeniden üretilebilirlik ve sürüm yönetimi

> *(Yazılacak: v1.1 sürümü, manifest ve özet değerler; her rakamın tek kaynaktan üretilmesi;
> yayımlanan sürümün kendi iddialarını doğrulayan kapılar.)*

## 11. Sonuç ve gelecek çalışma

> *(Yazılacak.)*

---

## Ek A — Terimler Sözlüğü

> *(Yazılacak.)*

## Kaynakça

1. `ramamr33/IoMT-NetworkAttackScenarios18` — IoMT ağlarında saldırı senaryoları (NS-3).
   Zenodo. DOI: **10.5281/zenodo.16747386**
