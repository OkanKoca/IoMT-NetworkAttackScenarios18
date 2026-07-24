# Sunum metni

Bölüm numaraları **özet raporunkiyle birebir aynıdır** (1–9), böylece dinleyici belgeyi
açık tutarak takip edebilir. Her bölüme geçerken numarayı yüksek sesle söyleyin:
"özet raporun üçüncü bölümü". Rapordaki iki şekil sunumda da işaretlenmiştir.

Dinleyici projeye hâkim değil. Bu yüzden her bölüm aynı kalıpta ilerler:
**ne yaptık → neden böyle yaptık → alternatifi neydi ve neden seçmedik.**
Anlatının taşıyıcısı rakamlar değil bu kararlar; rakamlar sadece kararları doğruluyor.

**Kalın** cümleler vurgulanacak olanlar. Ezberlenecek üç sayı: **0.788**, **0.960**, **39/40**.

**Süre.** Alıntı bloklarının tamamı okunursa konuşma **~15 dakika** (soru–cevap hariç).
Bölüm başlıklarındaki süreler ölçülmüştür, tahmin değil.

**10 dakikaya indirmeniz gerekirse**, sırayla şunları kısın; hiçbiri tezi bozmaz:

| kısılacak | kazanç | neden güvenli |
|---|---|---|
| §3'te Karar 2 ve Karar 3 | ~1.5 dk | Sağlam ama teknik kararlar; sorulursa anlatılır. |
| §6'daki "alternatifler" listesi | ~40 sn | Grey-hole'ün neden seçildiği tek cümleyle özetlenebilir. |
| §1'deki "neden simülasyon" ikinci gerekçesi | ~30 sn | Etiket argümanı; sorulursa geri getirin. |
| §4'teki dört senaryonun kök nedenleri | ~50 sn | "Dördünden biri çalışıyor" tek başına yeterli. |

**Asla kısmayın:** §4'ün ilk paragrafı (neden önce ölçtük), §3 Karar 1 ve Karar 4,
§5'in sonundaki "bu sonuç fazla iyi" cümlesi, ve **§7'nin tamamı**.

---

## Anlatmadan önce: dört terim

Bunları bir kez tanımlayın, sonra rahatça kullanın.

| terim | bir cümlelik karşılığı |
|---|---|
| **flow (akış)** | İki cihaz arasındaki tek yönlü paket dizisi. Ölçümler akış başına tutuluyor. |
| **teslim oranı** | Gönderilen 100 paketin kaçı vardı. Sağlıkta en kritik büyüklük bu. |
| **F1** | Bir skoru tek sayıya indiren ölçü: hem "kaçırmadın mı" hem "boş yere alarm vermedin mi" sorusunu birlikte cevaplar. 1.0 kusursuz. |
| **yanlış alarm tabanı** | Ortada hiç saldırı yokken bile modelin "saldırı var" deme oranı. Bizde 0.150. **Bir saldırı bu çizgiye kadar indiyse artık tespit edilmiyor demektir.** |

*(Son satır sunumun en önemli teknik fikri. Buna fazladan bir cümle ayırın.)*

---

## Açılış (45 sn)

> Konumuz, hastanedeki tıbbi cihazların ağ trafiğine bakarak saldırı tespiti. Dört çıktı
> istendi, dördü de üretildi; sayıları birazdan vereceğim.
>
> Ama sunumun asıl konusu o sayılar değil. **Bir modelin yüksek skor alması, doğru şeyi
> ölçtüğü anlamına gelmiyor.** Bu çalışmanın en değerli kısmı, kendi skorlarımızı sınamak için
> kurduğumuz kontrol deneyleri ve onların çıkardığı sonuç. Sunumun son üçte biri bunun üzerine.

*(Bu açılış şart. Yüksek F1 bekleyerek dinleyen biri, 0.788'i ve `ddos` 0.600'ü başarısızlık
sanır. Beklentiyi baştan doğru yere koyuyorsunuz.)*

---

## 1. Problem ve neden simülasyon (1.5 dk)

> Hastanelerde infüzyon pompaları, hasta başı monitörleri, giyilebilir EKG sensörleri
> ölçtükleri veriyi kablosuz ağ üzerinden gönderiyor. Bu verinin zamanında ve eksiksiz
> ulaşması klinik bir gereklilik; geciken bir ölçüm sadece veri kaybı değil, yanlış bir klinik
> kararın dayanağı olabilir.
>
> **Neden bu cihazları doğrudan koruyamıyoruz?** İki sebep. Donanımları çok sınırlı, üzerinde
> güvenlik yazılımı çalıştıracak yer yok. Daha önemlisi, tıbbi cihazlar klinik sertifikasyondan
> geçiyor; yazılımına dokunduğunuz anda o sertifika geçersiz oluyor. **Yani savunmayı cihazın
> içine koyamıyoruz, ağ tarafına koymak zorundayız.** Cihaza hiç dokunmadan, sadece ürettiği
> trafiğe bakarak.
>
> Sorumuz şu: ağ trafiğinin ölçülebilir özelliklerinden (teslim oranı, hız, gecikme, akış
> sayısı) bir saldırının varlığı ve türü anlaşılabilir mi?

**Neden gerçek ağ değil de simülasyon:**

> İki sebeple. Birincisi bariz: gerçek bir hastane ağına kontrollü saldırı denemesi
> yapamazsınız.
>
> **İkincisi daha önemli ve genelde atlanıyor.** Makine öğrenmesi için sadece "saldırı
> altındaki trafik" yetmez, o trafiğin **etiketi** gerekir: hangi koşuda hangi saldırı vardı,
> hangi şiddette. Gerçek bir ağda bunu ancak tahmin edersiniz. Simülasyonda **kesin
> bilirsiniz**, çünkü saldırıyı siz kurdunuz. Üstelik aynı tohum (seed) verildiğinde koşu
> birebir tekrar üretilebiliyor, yani sonuçlar doğrulanabilir.
>
> Bedeli de açık ve raporda saklamıyoruz: simülasyon gerçek bir hastanenin bütün
> karmaşıklığını içermiyor. Sınırlılıklar bölümünde tek tek yazılı.

---

## 2. Ne istendi, ne teslim edildi (45 sn)

> Dört çıktı istendi:
>
> 1. Çalışan bir NS-3 kurulumu ve mevcut bir saldırının yeniden üretilmesi.
> 2. Etiketli bir ağ trafiği veri seti.
> 3. Saldırıyı tespit eden ve **türünü** belirleyen bir model, yanında tespit–şiddet eğrisi.
> 4. Kaynak çalışmada bulunmayan, yeni ve **sessiz** bir saldırı.
>
> Dördü de üretildi: **285 koşuluk veri seti, beş sınıf.** Makro-F1 **0.788**, yeni saldırının
> tanınma skoru **0.958**.

---

## 3. Kurduğumuz sistem ve dört karar (3 dk)

*(Özet raporda §3.)*

> Ağımız: dokuz Wi-Fi istasyonu, bir erişim noktası, bir giyilebilir sensör. Merkezdeki akış
> bir EKG dalga formunun hasta başı monitörüne ulaşması: saniyede 128 kilobit, 128 baytlık
> küçük paketler. Bu gerçeğe yakın bir klinik telemetri profili. Arka planda dört tıbbi cihaz
> ve bir görüntüleme geçidi trafiği var.

**Karar 1: Tabana kasıtlı olarak gürültü ekledik.**

> Devraldığımız simülasyonda saldırı olmayan koşularda teslim oranı **tam olarak 1.0**'dı ve
> koşular arasında **hiç değişmiyordu**. İlk bakışta bu iyi bir şey gibi görünüyor: tertemiz
> bir referans.
>
> **Aslında sonuçları geçersiz kılan bir kusur.** Şöyle düşünün: hiç oynamayan bir referansta,
> saldırının yaptığı en küçük bozulma bile kocaman görünür. Model kolayca yüksek skor alır, ama
> o skor ağı değil **kurulumun yapaylığını** ölçer. Gerçek bir ağda teslim oranı zaten
> kendiliğinden dalgalanır; tespiti zorlaştıran da budur.
>
> Bu yüzden ağa ölçülü bir gürültü tabanı kazandırdık. Teslim oranı artık 0.970 ± 0.032.
>
> **Bu kalibrasyon sırasında beklemediğimiz bir şey öğrendik.** Kablosuz bağlantıya hata
> enjekte etmek teslim oranını hiç oynatmıyor. Sebebi şu: Wi-Fi bozulan bir paketi fark edip
> **kendiliğinden yeniden gönderiyor**, yani hata alt katmanda gizleniyor. Teslim oranını
> gerçekten düşürebilen tek mekanizma **tıkanıklık**: kuyruk dolduğunda atılan paketin yeniden
> gönderilecek kopyası yoktur. Arka plan yükünü bu yüzden doyum noktasının iki yanına düşecek
> biçimde ölçerek seçtik.

**Karar 2: Bir örnek = bir koşu, bir akış değil.**

> Veri setimizin her satırı bir simülasyon koşusu ve o koşudaki bütün akışların özetini
> taşıyor. Alternatif, her akışı ayrı bir örnek saymaktı. Seçmedik, iki sebeple.
>
> Birincisi anlamsal: **"bu ağda saldırı var mı" sorusu tek bir akışa bakılarak
> yanıtlanamaz.** DDoS'un tanımı zaten birden çok akışın birlikte davranmasıdır; tek akışa
> bakan bir model onu göremez.
>
> İkincisi daha teknik ama önemli: aynı koşudan gelen akışlar birbirine çok benzer. Bazıları
> eğitime, bazıları teste düşerse model **testte kendi eğitim verisinin kopyasını görür** ve
> skor sahte çıkar. Koşuyu birim seçince bu hatayı yapmak **imkânsız** hale geliyor.

**Karar 3: Tek model, iki ayrı model değil.**

> "Saldırı var mı" ve "hangi saldırı" iki ayrı soru; iki ayrı model eğitebilirdik. Eğitmedik.
> Tek bir çok-sınıflı model var ve "saldırı var mı" cevabı ondan türetiliyor: `normal` dışındaki
> her tahmin bir alarm sayılıyor. **Sebep: iki ayrı model birbiriyle çelişebilir**, biri
> "saldırı yok" derken diğeri "bu bir DDoS" diyebilir. Türetilmiş cevapta bu mümkün değil.

**Karar 4: Modele bilerek zor bir sınav verdik.**

> Sonuçları anlamak için en kritik karar bu, ve basitçe şöyle:
>
> Her saldırıyı farklı şiddetlerde koşturduk; örneğin grey-hole'ü paketlerin %2'sini
> düşürmekten %90'ını düşürmeye kadar. **Kolay sınav** şu olurdu: bütün koşuları karıştırıp
> rastgele bölmek. O zaman model, teste düşen bir "%50 düşüren" koşusunu eğitimde başka bir
> tohumda **zaten görmüş** olurdu. Bu bir ezber sınavıdır.
>
> Bunun yerine aynı şiddet ayarının **bütün** koşularını bölmenin tek bir tarafında tuttuk.
> Sonuç: model test edilirken **hiç görmediği bir saldırı şiddetiyle** karşılaşıyor. Gerçek
> hayatta karşılaşacağı durum da budur; saldırganın şiddeti sizin eğitim setinizdekiyle aynı
> olmak zorunda değil.
>
> **Bu tercihin bedeli ölçülü:** kolay sınavda skor 0.828, zor sınavda 0.788. Yaklaşık 0.04
> puan. Düşük skoru bilerek kabul ettik, çünkü yüksek olanı gerçeği anlatmıyor.

---

## 4. Kaynak çalışmayı kullanmadan önce sınadık (2 dk)

*Sunumun en güçlü bölümlerinden biri. Buraya zaman ayırın.*

*(Özet raporda §4. Dinleyici belgeyi takip ediyorsa numarayı söyleyin.)*

> Çalışma mevcut bir NS-3 çalışmasının üzerine kurulu. Normal yol, onun senaryolarını alıp
> üzerine eklemek olurdu. **Biz önce onları koşup ölçtük, ve bu kararın sebebi şu:**
>
> **Bir saldırı senaryosunun çalıştığının kanıtı, hatasız derlenmesi değildir.** Kod hatasız
> derlenip hiçbir şey yapmıyor olabilir. Kanıt, ürettiği trafiğin normal koşudan **ölçülebilir
> biçimde farklı** olmasıdır. Biz bunu ölçtük.
>
> Koşulabilen dört saldırıdan **yalnızca biri** amaçladığı etkiyi üretiyor:
>
> - **DoS çalışıyor.** Saldırı akışında 2900 paket var, gerçek bir flood.
> - **DDoS etkisiz.** Saldırgan düğümlere IP adresi verilmiş ama **Wi-Fi kartı takılmamış**.
>   Üzerlerinde saldırı programı çalışıyor, ama paketi gönderecek ağ arayüzleri yok.
> - **MITM amaçlananı yapmıyor.** Saldırgan sadece kendisine gelen 36 baytlık yönetim
>   mesajlarını görüyor; hastanın 512 baytlık tıbbi verisine hiç ulaşmıyor.
> - **Blackhole hiçbir şey düşürmüyor.** Kayıp sıfır. Sebep bir tip hatası: kod, cihazın
>   donanım adresini ağ adresiyle karşılaştırıyor. **Bunlar hiçbir zaman eşit olmuyor**,
>   dolayısıyla "bu paketi düşür" koşulu hiç çalışmıyor.
> - **MQTT-flood'u koşamadık**; tek sürümü derlenmeyen bir klasörde.

**Aynı sonuca ikinci ve bağımsız bir yoldan da vardık:**

> Kaynak çalışma kendi ölçüm sonuçlarını da yayımlamış. Onları alıp aynı özellikleri çıkardık.
> **60 koşu, sadece 30 farklı sonuç veriyor.** `dos`, `ddos` ve `blackhole` koşuları on tohumun
> onunda da birbirinden ayırt edilemiyor; `mqtt` ile `normal` de öyle. **Altı farklı etiket,
> gerçekte üç farklı ölçüm.**
>
> Bunu vurgulamak istiyorum: bu kanıt için senaryo koduna hiç bakmadık, sadece kaynak
> çalışmanın kendi yayımladığı sonuçlarına baktık. Kod okumadan varılan sonuç, kod okuyarak
> varılanla aynı çıktı.

**Bu bulgunun bizi getirdiği karar:**

> Senaryoları yeniden yazdık. **Sebebi şu: bozuk bir senaryodan üretilen veriyle eğitilen
> model, "saldırı" etiketi taşıyan ama içinde saldırı olmayan koşular öğrenir.** O modelin
> yüksek skor alması bir şey ifade etmez, çünkü öğrendiği şey gürültüdür.
>
> Kaynaktan devraldığımız şey topoloji, trafik deseni ve saldırıların kurulma kalıbı. Yeniden
> yazdığımız şey saldırıların kendisi.
>
> Bunu kaynak çalışmayı kötülemek için anlatmıyorum. **Bir tasarım kararının gerekçesi olarak
> anlatıyorum**, ve o karar olmasaydı bu projenin bütün sonuçları geçersiz olurdu.

---

## 5. Sonuçlar (2 dk)

> **Saldırı var mı sorusu:** 255 koşu üzerinde, hiç görülmemiş şiddetlerle sınandığında saldırı
> F1'i **0.960**. Yanlış alarm oranı 0.150.
>
> **Hangi saldırı sorusu:** burada tablo **ikiye ayrılıyor**, ve bu ayrım tesadüf değil.
>
> **Paket düşüren saldırılar güvenilir biçimde tanınıyor:** grey-hole 0.958, blackhole 0.952.
> **Hacim saldırıları tanınmıyor:** dos 0.676, ddos 0.600.
>
*(Raporda **Şekil 2**, karışıklık matrisi. Dinleyiciye gösterin: satırlar gerçek sınıf,
sütunlar modelin tahmini. Köşegen doğru cevaplar.)*

> `dos` ve `ddos` birbirine karışıyor, ve karışma **çift yönlü**. Bu ayrıntı önemli: tek yönlü
> bir karışma eşik ayarıyla düzeltilebilir. Çift yönlü karışma **iki sınıfın ölçtüğümüz
> büyüklüklerde birbirinden ayrışmadığı** anlamına gelir, yani daha iyi bir model bunu çözmez.
> Sebebini §7'de göstereceğim.

**Tespit–şiddet eğrisi (istenen manşet çıktı):**

> Soru şu: saldırı zayıfladıkça tespit nereye kadar dayanıyor?
>
> **Dört saldırıdan yalnızca `dos`'ta gerçek bir çöküş var**, ve o kol tabana kadar iniyor.
> 100 paket/s üstünde tespit kusursuz; 50'de 0.80'e, 20'de 0.70'e, 10'da 0.40'a iniyor.
> **2–5 paket/s'de ise 0.20**, ve hatırlarsanız yanlış alarm tabanımız 0.150.
>
> Yani o hızlarda model saldırıyı **görmüyor**; sadece saldırısız koşularda da yaptığı hatayı
> yapıyor. Bunu ayrıca doğruladık: o hızlarda saldırının ölçtüğümüz büyüklüklerde bıraktığı iz,
> normal trafiğin kendi dalgalanmasının **onda biri** kadar. Ölçemeyeceğimiz kadar küçük.
>
> **Diğer üç kolun eğrisi ise dümdüz, her şiddette 1.00.** Grey-hole paketlerin sadece %2'sini
> düşürdüğünde bile kusursuz yakalanıyor.

*(Burada durun ve şu cümleyi kurun:)*

> **Bu sonuç fazla iyi. Bir saldırının %2 şiddette bile kusursuz yakalanması gerçekçi değil.
> Neden böyle çıktığını araştırdık, ve bu çalışmanın asıl bulgusu oradan geldi.**

---

## 6. Yeni saldırı: neden grey-hole seçtik (2 dk)

> Dördüncü çıktı, kaynak çalışmada olmayan yeni ve **sessiz** bir saldırıydı.
>
> **Neden sessiz olması gerekiyordu?** Çünkü kaynak çalışmadaki saldırıların hepsi gürültülü;
> ağı bariz biçimde bozuyorlar. Onları yakalamak için makine öğrenmesine ihtiyaç yok, basit bir
> eşik yeter. **Makine öğrenmesinin anlamlı olduğu yer, saldırının normal davranışın içinde
> saklandığı yerdir.**
>
> Seçtiğimiz saldırı **grey-hole**: yol üzerindeki ele geçirilmiş bir cihaz, paketlerin
> tamamını değil, `p` olasılıkla **bir kısmını** düşürüyor, gerisini normal biçimde iletiyor.
> Ağ çalışıyor görünmeye devam ediyor. Blackhole "her şeyi düşür" der; grey-hole "biraz düşür,
> kimse fark etmesin" der.

**Neden bunu seçtik, alternatifleri neden seçmedik:**

> Üç aday vardı.
>
> - **Darbeli DoS**'u eledik, çünkü bizim trafiğimizde sömürülecek bir mekanizma yoktu.
> - **Sahte veri enjeksiyonu**nu eledik, çünkü paket **içeriğini** bozmak akış seviyesindeki
>   ölçümlerimizde hiçbir iz bırakmıyor. Ölçemeyeceğimiz bir saldırının şiddet eğrisi de
>   çizilemez.
> - **Grey-hole**'ü seçtik, çünkü `p` doğal ve sürekli bir şiddet ayarı veriyor: sıfırdan bire
>   kadar çevirebileceğiniz bir düğme. Manşet çıktı olan tespit–şiddet eğrisi için tam olarak
>   böyle bir düğme gerekiyordu.

**Uygularken aldığımız kritik karar:**

> Kolay yol, kaynak çalışmanın bozuk blackhole kodunu düzeltmekti. **Yapmadık, ve sebebi
> önemli:** o koddaki sorun bir yazım hatası değil. Saldırgan düğüm **trafiğin geçtiği yolun
> üzerinde değil**. Yanından geçen trafiği hiç göremeyen bir düğüme "paketleri düşür" demenin
> anlamı yok.
>
> Bu yüzden grey-hole'ü ağ yoluna **fiilen yerleşen** bir uygulama olarak yazdık: EKG kaynağı
> paketleri saldırgana gönderiyor, saldırgan bir kısmını düşürüp gerisini monitöre iletiyor.
>
> **Çalıştığını doğruladık:** teslim oranı `p` ile düzenli biçimde düşüyor ve iki uçta beklenen
> değeri veriyor. `p = 0.5`'te teslim 0.458, `p = 0.9`'da 0.091. Ve `p = 1` verdiğinizde aynı
> kod **çalışan bir blackhole** oluyor; kaynak çalışmanın çalışmayan blackhole'ünün yerine
> geçen de bu.

---

## 7. Asıl bulgu: detektör neyi ölçüyor? (3 dk)

*Sunumun omurgası. Yavaş anlatın.*

> §5'te bir soru bırakmıştım: grey-hole neden %2 şiddette bile kusursuz yakalanıyor?
>
> **Kurduğumuz kontrol deneyi çok basit.** Saldırıyı ağdan çıkardık ama **aracı cihazı yerinde
> bıraktık**. Yani ağda fazladan bir düğüm var, trafik onun üzerinden geçiyor, ama o düğüm
> **hiçbir şey yapmıyor**: tek bir paket bile düşürmüyor, geciktirmiyor, değiştirmiyor. Sadece
> iletiyor.
>
> Sonra modele sorduk: bu ne? Model bu konfigürasyonu hiç görmemişti; eğitmedik, sadece ölçtük.
>
> **Sonuç: hiçbir zararlı davranışı olmayan bu cihaz, 40 koşunun 39'unda saldırı alarmı
> üretti.** Dahası rastgele bir sınıfa da atmadı: 36'sına özellikle **`greyhole`** dedi.
>
> Şimdi rakamları yan yana koyalım. Ortada aracı da saldırı da yokken model %15 oranında yanlış
> alarm veriyor. **Sadece zararsız aracıyı ekleyince bu %97.5'e fırlıyor.** Yani saldırıyı da
> açtığınızda geriye kalan pay sadece **%2.5**.
>
> **Grey-hole eğrisinin neden dümdüz olduğu böylece tamamen açıklanıyor: eğri zaten tavanda
> başlıyordu, saldırının oynatabileceği yer yoktu.**

**Aynı sonucu ikinci bir yoldan da gördük:**

> Kurban yolunun teslim oranını üç aşamada ölçtük:
>
> - Ağda aracı yok, saldırı yok: **0.9754**
> - Aracı var ama tamamen zararsız: **0.9023**
> - Aracı var ve saldırı açık: **0.8953**
>
> Yani teslim oranındaki düşüşün **%91'i sadece aracının orada olmasından**, **%9'u
> saldırıdan** geliyor.

**Bunun anlamı:**

> **Detektörümüzün fiilen cevapladığı soru şu: "bu ağda beklenmedik bir aracı var mı?"
> "Bu aracı kötü niyetli mi?" değil.**
>
> Bunu bir başarısızlık olarak sunmuyorum, çünkü ilk soru da gerçek bir sorudur; bir hastane
> güvenlik ekibi ağında tanımadığı bir cihaz olup olmadığını gerçekten bilmek ister ve model
> bunu iyi yapıyor. Ama **iki ayrı sorudur ve ayrı ölçülmelidir.**
>
*(Raporda **Şekil 5**. Taralı alan saldırının tabanın üstüne çıkan gerçek katkısı;
sunumun tezi tek bir resimde burada.)*

> Nitekim soruyu doğru sorduğumuzda gerçek bir eğri ortaya çıktı. Ayrımı `normal`'e karşı
> değil, **zararsız aracıya karşı** ölçtük: `p = 0.02`'de saldırı hâlâ görünmüyor, `p = 0.05`
> geçiş bölgesi, **`p = 0.1`'de ayrım netleşiyor.** Saldırının gerçekten görünür hale geldiği
> eşik bu. Aracının konumunu değiştirdiğimizde de aynı çıkıyor.

**Aynı desen iki kez daha tekrarladı:**

> - **`ddos` sınıfı** pratikte "saldırgan sayısı çok" değil **"hasar çok"** anlamına geliyor.
>   Gerçekleşen hasarı eşitlediğimizde `dos`/`ddos` ayrımı 0.475'e düşüyor; yazı tura 0.500.
>   Yani model saldırgan **sayısını** hiç okumuyormuş, sadece hasarın büyüklüğünü okuyormuş.
> - **Paketleri geciktiren bir saldırıyı** sınıf olarak eğittiğimizde model, hiçbir şey
>   yapmayan aracıya koşuların %80'inde o saldırının adını veriyor.
>
> **Üçünün ortak açıklaması, ve sunumdan aklınızda kalmasını istediğim cümle bu:**
>
> **Akış seviyesinde ölçtüğümüz büyüklükler, saldırganın niyetini değil kullandığı mekanizmayı
> görüyor.** Bir ölçüm vektörü "bu düğüm kötü niyetliydi" bilgisini taşımaz; "bu koşuda şu
> kadar paket kayboldu, şu kadar akış vardı" bilgisini taşır. Aynı mekanizmayı kullanan iki
> farklı niyet, bu ölçüm düzeyinde aynı şeydir.
>
> Bu aynı zamanda "daha çok saldırı çeşidi ekleyelim" önerisinin neden bilgi katmadığının da
> cevabı: bu ölçüm düzeyinde UDP flood, MQTT flood ve sahte bir cihaz aynı olay.

---

## 8. Sınırlılıklar ve neden açıkça yazdık (1 dk)

> Sınırlılıkları saklamıyoruz, çünkü çoğu tahmin değil **ölçülmüş sonuç**:
>
> - İkili tespit doygun; ölçtüğü şey saldırı değil, aracının varlığı.
> - Grey-hole `p < 0.1`'in altında görünmüyor. **Klinik olarak anlamlı bir sınır bu:**
>   telemetrinin %2'sini düşüren bir saldırgan bu detektörden kaçar.
> - `dos`/`ddos` ayrımı güvenilir değil; **bu model o ayrım için kullanılmamalı.**
> - Rakamlar bu topolojiye özgü. Taşınabilir olan yöntem, mutlak değerler değil.
>
> Bir şeyi ayrıca söylemek istiyorum, çünkü bence çalışmanın en olgun tarafı bu. **Bağımsız bir
> inceleme bizim çalışmamızda üç ayrı hata buldu. Üçü de ölçümün değil kaydın hatasıydı:**
> model her seferinde doğru çalışmış, rapora yazılan rakam yanlış yazılmıştı.
>
> Bunları tek tek düzeltmekle yetinmedik. **Her birine, aynı hatanın tekrar edilmesini imkânsız
> kılan bir otomatik kontrol koyduk.** Örneğin sürüm dondurma adımı artık test verisinin eğitim
> verisiyle çakışıp çakışmadığını **ölçüyor** ve çakışma bulursa sürüm kesmeyi **reddediyor**.
> Kontrolü önce yazmanın faydası hemen görüldü: inceleme 10 hatalı satır bulmuştu, kontrol 15
> buldu.

---

## 9. Kapanış (45 sn)

> Özetle: bir IoMT ağının NS-3 modeli üzerinde 285 koşuluk etiketli bir veri seti ürettik,
> saldırının varlığını ve türünü belirleyen bir detektör eğittik, ve kaynak çalışmada olmayan
> sessiz bir saldırıyı gerçekleyip detektöre karşı sınadık. Makro-F1 0.788, ikili saldırı-F1
> 0.960.
>
> **Ama çalışmanın asıl katkısı bu skorlar değil, skorların ne ölçtüğünü soran kontrol
> deneyleri.** Ağa yerleştirilmiş ama hiçbir zararlı davranışı olmayan bir cihazın detektörü
> 40 koşunun 39'unda alarma geçirmesi, tespit edilen şeyin büyük ölçüde saldırı değil **ağ
> yapısındaki bir değişiklik** olduğunu gösteriyor.
>
> **Bir detektörün skoru, neyi ölçtüğü sorulmadan yorumlanamaz.** Bu çalışmadan çıkardığım
> sonuç bu.

---

# Soru–cevap hazırlığı

**"0.788 düşük değil mi?"**
> Kolay sınavda 0.828 alıyoruz; aradaki fark zor sınavın bedeli ve bilerek ödendi. Asıl cevap
> şu: bu sayı **kalibre edilmiş bir taban üzerinde** ölçüldü. Devraldığımız gürültüsüz veri
> setinde skorlar 0.99'a çıkıyordu, ama o skor ağı değil kurulumun yapaylığını ölçüyordu.
> **Kazanımımız yüksek skor değil, ölçülmeye değer bir taban kurmuş olmak.**

**"Neyi tespit ediyor, saldırıyı mı aracıyı mı?"**
> Büyük ölçüde aracıyı, ve bunu tahmin etmiyoruz, ölçtük: zararsız aracı 40 koşunun 39'unda
> alarm üretiyor. Bu yüzden ikili tespiti bir başarı değil **doygun bir ölçüm** olarak
> raporluyoruz, ve gerçek ayrımı zararsız aracıya karşı ölçüyoruz. Orada çöküş noktası
> `p = 0.1`.

**"Neden kaynak çalışmanın senaryolarını kullanmadın?"**
> Kullanmayı denedik ve önce ölçtük. Koşulabilen dört saldırıdan üçü ağ üzerinde hiçbir etki
> üretmiyor; sebepleri kodda tek tek gösterilebiliyor. Bozuk bir senaryodan üretilen veriyle
> eğitilen model, saldırı etiketli ama saldırı içermeyen koşular öğrenir.

**"Kaynak çalışmanın verisinde neden çöküyorsunuz?"**
> Çünkü o veride altı etiket üç ölçüme karşılık geliyor; **herhangi bir modelin** oradaki tavanı
> yaklaşık 0.36. Ayrıca özelliklerin yarısı bizim eğitim aralığımızın tamamen dışında. Ölçtüğümüz
> şey detektörün başarısızlığı değil, iki veri kümesinin **aynı ölçüm evreninde olmadığı**. Bu
> yüzden onu bir başarım ölçütü olarak değil **uyumsuzluk probu** olarak sunuyoruz, ve skoru
> yükseltmeye bilerek çalışmadık: etiketlerin bir kısmı birbirinin kopyası olduğu için her
> kazanç kopyaya uydurmaktan gelirdi.

**"Gerçek bir hastanede çalışır mı?"**
> Bu haliyle hayır, ve raporda açıkça yazıyoruz. Tek topoloji, basitleştirilmiş trafik.
> **Taşınabilir olan yöntem**, özellikle kontrol deneyi fikri: bir şiddet eğrisi, taradığınız
> değişkenin yanında **her noktada sabit duran** şeyi de ölçer, ve onu ayrıca ölçmezseniz
> eğrinin ne kadarının saldırıya ait olduğunu bilemezsiniz.

**"Test verisi gerçekten eğitimin dışında mı?"**
> Evet, ve bu artık bir iddia değil **ölçülen bir sonuç**. İlk sürümde değildi: 40 test
> satırının 15'i eğitim satırlarının birebir kopyasıydı. Şimdi sürüm dondurma adımı bunu
> kontrol ediyor ve çakışma bulursa **çalışmayı reddediyor**.

**"Neden daha çok saldırı türü eklemediniz?"**
> Çünkü akla gelenler aynı üç eksene düşüyor: sahte cihaz bir akış fazla, tekrarlama saldırısı
> hacim artışı, pil tüketme hiçbir şey. Bu ölçüm düzeyinde UDP flood ile MQTT flood **aynı
> şey**. Bilgi katan tek ekleme, boş bir eksene düşendir.

---

# Sunum sırasında dikkat

- **"%97.5 doğrulukla tespit ediyoruz" demeyin.** O sayı zararsız aracıya verilen alarm oranı,
  bir başarı metriği değil. Yanlış anlaşılırsa bütün §7 çöker.
- **`blackhole` 0.952 ile `greyhole` 0.958'i "ikisi de güvenilir" diye yan yana koymayın.**
  İkisi farklı zorlukta sınavdan geçti: grey-hole hiç görmediği bir şiddetle, blackhole
  eğitimde gördüğü tek ayarla. Sorulursa böyle açıklayın.
- **İki makro-F1 var ve çelişki değil:** 0.788 katların ortalaması, 0.797 bütün tahminlerin tek
  tabloda toplanmış hali. Sınıf tablosu ikincisinden geliyor.
- **Kaynak çalışmayı kötülemeyin.** "Şu senaryolar bozuk" değil; "ölçtük, üçü etki üretmiyor,
  bu yüzden yeniden yazdık" çerçevesi. Bulgu aynı, tonu farklı.
- Dinleyici teknik değilse **§7'ye zaman aktarın**, §3'ün kararlarını kısaltın. §7 anlaşılmazsa
  sunumun tezi anlaşılmamış olur.

---

# Sorulursa: raporda olmayan ek kanıtlar

Teslim edilen belgede yok. **Kendiliğinizden anlatmayın**, ama itiraz gelirse elinizde olsun.

**"Bu bulgu sadece fazladan bir akış saymaktan kaynaklanıyor olabilir mi?"**
> Ölçtük, hayır. Akış sayısıyla ilgili bütün özellikleri modelden çıkardığımızda aracının
> eklediği tespit azalıyor ama kaybolmuyor. Yapıyla **ve** zamanlamayla ilgili yedi özelliği
> birden çıkarıp geriye sadece hacim ve teslim bırakınca bile, zararsız aracı 40 koşunun
> 30'unda alarm alıyor.

**"Zamanlama saldırısını sınıf olarak eğitseydiniz?"**
> Denedik. F1 0.859 alıyor, ama **hiçbir şey yapmayan aracıya 40 koşunun 32'sinde o saldırının
> adını veriyor.** Düşük şiddetli ayarları dışladığımızda bu oran yarıya iniyor. Ama zararsız
> aracı **her iki durumda da 40/40 koşuda "saldırı"** damgası yiyor: sınıf eklemek doygunluğu
> kırmıyor, sadece harcanacak yeni bir etiket veriyor.
