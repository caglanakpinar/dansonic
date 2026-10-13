# Dansonic v1

Tek kamera ile dansçilarin hareketlerini algilar; arkada surekli donen davul
loop'unun ustune, vurusa oturan vokal seslerini calar. GPU gerekmez.
Sahnede birden fazla dansçi olsa da yalnizca biri takip edilir. `v0/`
klasorunden bagimsizdir.

## Prova duzeni

- Arka plan: `sounds/drums-loop.mp3` surekli doner (132.9 bpm).
- Hareketle calinan 8 ses: `ab`, `ab-ab`, `been`, `thin`, `wha-been`, `two-been-thin`,
  `ab-wha-two-been-thin`, `ab-ow-ab-ow-thin`. Sesler dans videosunun vokal
  kaydindan kesildi (`sounds/video/`, bkz. "Videodan alinan sesler").
- Ilk bes ses sarkinin vurus sirasidir: 1. vurusta `ab` (iki kolla vurulursa
  2. vurusta ikinci `ab` gelir: `ab-ab`), 2. `been`, 3. `thin`, 4. `wha-been`.
  Dansci ritme vurdukca o vurusun sesi calar (bkz. "Vurus modu").
  Son uc ses uzun ifadelerdir ve kendi hareketleriyle calar.
- Her hareket poz basladigi anda bir kez tetikler. Tekrar icin dansçi pozdan
  cikip yeniden girmelidir. Poz tutuluyorsa ses her vurusta devam eder.
- Eski mod, her sese kendi hareketini veren `config.gestures.yaml`, hala var.

## Takip edilen dansçi

Sistem tek bir dansçiya kilitlenir (`pose.mode: single`); kadrajdaki diger
kisiler gri iskeletle cizilir ve ses tetiklemez.

- Ilk secim `pose.select` ile yapilir: `center`, `largest`, `left`, `right`.
- Sonra ayni kisi hem konumundan hem ust kiyafetinin renginden takip edilir.
  Dansçilar caprazlasinca veya biri digerini kapatinca kilit sasmaz.
- Takip edilen dansçi kisa sure gorunmezse sistem bekler, digerine atlamaz.
  1 saniyeden uzun kaybolursa kiyafeti eslesen kisi yeniden secilir.
- Yanlis kisi secildiyse T tusu kilidi digerine gecirir.

Kopmasiz performans icin:

- Ses calan dansçi digerinden belirgin farkli renkte bir ust giymeli
  (ornegin biri siyah, digeri beyaz veya renkli). Ayni kiyafette takip
  yalnizca konuma dayanir ve tam kapanmada sasabilir.
- Dansçilar bastan ayaga kadrajda kalmali, arkadan guclu isik olmamali.
- Kamera sabit durmali ve gosteri boyunca yeri degismemeli.

## Kurulum ve calistirma

Python 3.11 veya 3.12 gerekir.

```bash
cd v1
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run.py
```

macOS ilk calistirmada kamera izni ister; komutu Terminal.app'ten calistirin.

| Komut | Islev |
|-------|-------|
| `run.py` | canli performans |
| `run.py --no-camera` | kamerasiz, sesleri 1-8 tuslariyla dene |
| `run.py --source klip.mp4` | kamera yerine video dosyasi |
| `run.py --source dansonic.mp4` | dans videosu: loop'un tempo'suna ve olcusune hizalanir (bkz. "Video ile deneme") |
| `run.py --config config.gestures.yaml` | eski mod: her sese kendi hareketi, vurusa bakmaz |
| `run.py --record AD` | tutulan pozu AD adli hareket olarak kaydet |

Tuslar: SPACE dur/devam, R loop'u basa al (olcunun 1. vurusu), G kuantalama
ac/kapa, M ayna, T takip edilen dansçiyi degistir, B en yakin vurusu 1. vurus
yap, O acilisi beklemeden baslat, K kendi ab-ab'ni ogret (bkz. "Acilis"), Q cikis,
1-8 sesleri sirayla calar.

## Vurus modu (varsayilan)

Videonun sarkisinda her olcu ayni sirayla gider: 1. vurusta `ab`, 2. vurusta
`been`, 3. vurusta `thin`, 4. vurusta `wha-been`. Uygulama bu siraya uyar: dansci
bir hareket (vurus) yaptiginda, o hareketin dustugu vurusun sesi calar. Hangi
hareketi yaptigi onemli degil, ritme vurmasi yeterli. Boylece ayni durus
1. vurusta `ab`, 4. vurusta `wha-been` calar, tipki videodaki gibi.

### 1. vurus: tek `ab` ve cift `ab ab`

Sarkida 1. vurus iki sekilde soylenir: cogu olcuda tek `ab`, videonun 1., 3. ve 8.
olcusunda `ab ab` (1. ve 2. vurus). Uygulama ikisini de calar:

- 1. vurusa vuran hareket `ab`'i hemen calar, bekleme yok.
- Ardindan `beats.group` (0.25 sn) icinde iki kol da vurursa (iki el gogusa, iki kol
  birlikte yukari, sol ve sag kolun birlikte savrulmasi) 2. vurusta `been` yerine
  `ab-ab` kaydinin ikinci `ab`'i gelir. `ab-ab` kaydinin ilk yarisi `ab` ile ayni kesit
  oldugundan ikisi birlikte videodaki `ab ab` olur. Tek kolla vurulursa 2. vurusta
  `been` calar.
- `config.yaml`'da bu, `ab` girisinin yanindaki `both_arms: true` olan `ab-ab`
  girisidir; `span: 2` iki vurusu kapsadigini soyler (2. vurusa gelen hareket `been`
  calmaz). Sesi tuslarla denerken (2) kaydin tamami calar.
- Hangi kolun vurdugu hareketin adindan bilinir: `left_*` sol, `right_*` sag;
  `hands_chest`, `both_hands_up`, `t_pose` gibi iki kollu hareketler iki kol
  (`dansonic/actions.py` > `TWO_ARMED`, `beats.two_armed` ile genisletilir).
  Tutulan bir poz yalnizca kendisi iki kolluysa iki kol sayilir; iki ayri tek kollu
  pozun birlikte tutulmasi cift degildir (videoda 9. olcuda iki kol yukarida duruyor,
  sarkida cift `ab` yok). Goruntudeki hareket (`motion`) kol bilgisi tasimaz.
- Videoda: 1. olcu (iki el gogusa) ve 8. olcu (iki kol birlikte yukari) `ab ab`; 2. ve
  4. olcu (tek kol) tek `ab`. Kural `ab` ile baslayan 5 olcunun 4'une uyar. Istisna 3.
  olcu: `ab ab` soyleniyor ama yalnizca sag kol yukarida; uygulama orada tek `ab` calar.
  5. ve 9. olcu `ab` ile degil `been` ile basliyor (`been been`); uygulama orada da
  vurusun sirasina uyup `ab` calar. Orneklem cok kucuk (5 olcu): baska danslarda
  kural tutmayabilir, o zaman `config.yaml`'dan `ab-ab` girisini silmek yeterli.

Ayarlar `config.yaml` > `beats`:

- `hits`: vurus sayilan hareketler: dort kol savurmasi, videodaki pozlar
  (`hands_chest`, `squat_wide`, `arm_sweep`, `right_arm_diag`, `right_hand_head`)
  ve yerlesik kurallar (`right_hand_up`, `left_hand_up`, `right_arm_out`,
  `left_arm_out`, `t_pose`, `hands_on_hips`).
- Her vurusta en fazla bir ses. `min_gap` (0.1 sn): bu kadar yakin iki hareket
  tek vurustur (iki kol birlikte savrulur). `lookahead` (0.4): vurusun son %40'ina
  denk gelen hareket bir sonraki vurusa sayilir ve onu bekler; digerleri hemen,
  bir sonraki 16'lik notada calar.
- `sustain: true`: vurus sayilan bir poz tutuldukca her vurusta ses calar. Videoda
  iki kolun yukarida durulan bolumde (16.4-19.4 sn) sarki boylece devam eder.
- `motion: 0.0003`: goruntude herhangi bir hareket de cizgiyi vurusa oturtarak
  surdurur; poz takibinin gormedigi bir dansci ya da bilinen bir hareket olmayan
  hareket de. Ses, kareler arasinda degisen piksel oranina bakar (`dansonic/motion.py`).
  Hareketsiz goruntu 0.00001 civarinda, dansci 0.001-0.03: gurultulu bir kamerada
  hareket yokken ses geliyorsa degeri artirin, `0` kapatir. Video basa sarinca ya
  da yeniden baslayinca kare farki sayilmaz.
- Uc ifade kendi hareketleriyle calar (`mappings` > `gestures`): `right_hand_high`
  -> `two-been-thin`, `right_arm_side` -> `ab-wha-two-been-thin`, `arms_flail`
  ve `both_hands_up` -> `ab-ow-ab-ow-thin`. Calarken vurus sesleri onu kesmez
  (`protect`) ve bastan baslamaz (`cooldown`). `ab-ow-ab-ow-thin` icin `cooldown: 2.5`
  bir olcudan uzun: ifade calindiktan sonraki olcuda ayni hareket (iki kol yukari)
  ifadeyi degil `ab ab`'i calar, videoda 7. olcunun ardindan 8. olcu gibi. Ifade ikinci
  `ab`'dan once baslarsa o `ab` calmaz.
- Olcu, dongunun ilk vurusundan baslar (`loop.downbeat_index: 0`). Dansa baslarken
  R'ye basin ya da dansin 1. vurusunda B'ye basin. Paneldeki dort nokta olcudeki
  vurusu gosterir.

## Acilis: ab-ab

Dans (senkron) `ab ab` ile acilir (videoda 2.2 sn civari, iki el gogusa). `ab-ab`
hareketi gorulmeden dansin hicbir sesi calmaz: vurus da, tutulan poz da, goruntudeki
hareket de, ifadeler de. Video basinda ya da dansciyi beklerken olusan hareket
gurultusu bu yuzden ses cikarmaz. Tek istisna, asagidaki tek hareketlerdir.

Acilis esnektir. `config.yaml` > `opening` bolumunde uc yol vardir:

| yol | ne zaman acar |
|-----|---------------|
| `motions`: `hands_chest`, `hands_on_chest` | hareket net yakalaninca, tek kare yeter: poz esigini `margin` (0.03 govde boyu) asmali |
| `loose`: `hands_near_chest`, `both_forearms_up` | ab-ab daha serbest yapilinca: poz `hold` (0.3 sn) tutulunca. `grace` (0.15 sn) kadar kisa kopmalar (izleyici elleri bir kare kaybeder) sayimi sifirlamaz |
| ogretilen poz (K tusu) | dansicinin kendi ab-ab'si: `motions` gibi, tek kare yeter |

- `hands_chest`: videodaki dansciyla kaydedilmis poz. `hands_on_chest`: yerlesik, her
  dansci icin: iki el gogusta, capraz degil, kameraya donuk. Videodaki gercek acilis
  bu iki kuralda yaklasik 0.12-0.15'e cikar (esik 0.03).
- `hands_near_chest`: iki el ust govdede, omuzdan govde boyunun 0.7'sine kadar (kabaca
  gobege yakin); eller ust uste ya da biraz capraz olabilir, govde biraz donuk olabilir,
  bilekler yarim gorunur olabilir (eller birbirini ortunce izleyici emin olamaz).
  Gevsek oldugu icin ancak `hold` kadar tutulunca acar.
- `both_forearms_up`: iki on kol dik, eller omuz ile cene arasinda, birbirinden ayri
  (`ab` cizimlerinin iki kollu hali). Yine `hold` kadar tutulunca.
- K tusu: geri sayim (3 sn), sonra kendi `ab-ab` pozunu yap ve 1.2 sn tut. Uygulama
  dirsek ve bilek konumlarini `poses/ab_ab_N.json` olarak kaydeder; bundan sonra bu poz
  da acar (govde boyunun 0.25'i kadar toleransli). Yanlis ogrendiyse o dosyayi sil.
  Ogretilen poz baska dans hareketlerine benziyorsa kapali kapidayken onlar da acabilir:
  dansin bir hareketi yerine ab-ab'ye ozgu bir poz ogret. K yalnizca kamerayla calisir.
- Acilan pozlar (`tests/test_opening_pose.py`, her biri gurultu, beden boyu ve kamera
  mesafesi degisimiyle 60-80 kez): eller gogusta (yakin, uzak, yuksek), eller alcakta,
  ust uste ya da hafif capraz, iki on kol dik. Acilmayanlar: kollar inik, eller cepte,
  eller karinda kenetli, kollar kavusturulmus, eller belde, T pozu, iki el havada, tek el
  havada, tek el gogusta, eller yuzde ya da ensede.
  Sinir: eller gogus ortasinda birlestirilirse (namaste) hemen, gogsun altinda
  birlestirilip 0.3 sn tutulursa da acilir. ab-ab'nin birlesik ellerle yapilan hali ayni
  poz oldugu icin bunlar ayirt edilemez. Cok sik yanlis aciyorsa `hold` degerini
  artirin ya da `loose` listesini kisaltin.
- Gorulunce o an olcunun 1. vurusu olur (B tusuna basmak gibi), `ab` calar ve ikinci
  `ab` 2. vurusa tam oturur: acilis her zaman `ab ab`dir, hareket tek kollu olsa da.
  Ilk `ab`, hareket gorulene kadar beklendigi icin videodaki ilk vurustan yaklasik
  0.1 sn sonra calar (bu surede el gogse varir).
- Kapi R'ye basinca, video basa sarinca ya da senkron bitince kapanir; o anda hala
  tutulan bir poz yeni bir acilis sayilmaz: once birakilmali (en az `grace` kadar),
  sonra yeniden yapilmali.
- Ekranda ust seritte `ab-ab bekleniyor (O: basla)` yazar; panelin altinda `Acilis
  hareketi:` (net yakalananlar), `Yakin:` (tutulunca acanlar) ve tek hareketler. O tusu
  beklemeden acar (ses calmaz, o an 1. vurus olur). `opening` bolumunu silerseniz ilk
  kareden itibaren calar.

Sonuc (video 1.1025 hizinda, uygulama dongusu kareleri atlayarak, 20 kosu x 2 tur
simulasyonu):

| | kapi yok | kapi var |
|-|----------|----------|
| acilistan once calan ses | 39 turda, ortalama 1.6 (videonun 0.3. saniyesinde `ab` gibi) | hic |
| acilis `ab` + `ab-ab` | 36 turda; 4'unde `ab` + `been` | 40 turda 40 |
| vurus puani (40 vurustan) | 33.9 | 34.0 |

Acilisi esnek yapmanin etkisi (her satir 40 kosu; "siki" onceki surum: yalnizca
`hands_chest` ve `hands_on_chest`, `margin` 0.05):

| acilis hareketi yakalanan kosu | 30 kare/sn | 20 | 15 | 12 | 10 |
|--------------------------------|-----------:|---:|---:|---:|---:|
| siki | 40 | 40 | 40 | 38 | 31 |
| esnek | 40 | 40 | 40 | 40 | 40 |

Kapi kapaliyken yanlis acilma: dansci videonun 2.7 ile 25.7. saniyeleri arasinda her
0.5 sn'de baslayip dans etmeye devam ettirildi (188 kosu): hic yanlis acilis olmadi. Videodaki
en uzun serbest pozlar 0.23 sn surer (`hold` 0.3 sn). Videonun sonunda ikinci dansci
ayni hareketi 26.7 sn'de yapar ve bir sonraki turun acilisi sayilir.

Kolay kismi videonun kendisi: acilis orada yalnizca 0.2-0.3 sn tutulur ve dansci
karsidan, kameraya donuk durur. Canli kamerada acilis hareketi sizin boyunuza, kamera
mesafesine ve acisina gore degisir; yakalamazsa once `Yakin:` satirina bakin, sonra K ile
kendi pozunuzu ogretin, olmazsa O ile elle baslatin. Canli kamerayla denenmedi.

### Tek hareketler

Senkron baslamadan (program acilirken, R'den sonra, video basa sarinca) `config.yaml`
> `individual` altindaki hareketler tek basina calar: her biri kendi sesini hemen
calar ve senkronu baslatmaz; senkronu yalnizca acilis `ab-ab` baslatir. Senkron
baslayinca bu hareketler susar ve yerine vurus sesleri gelir.

```yaml
individual:
  - sound: ab
    gestures: [left_hand_up, right_hand_up]     # bas ustunde bir el, sol ya da sag
```

- Simdilik tek atama var: el yukari (sol ya da sag) -> `ab`. Baskalari ayni bicimde
  eklenir: her giris bir ses (`mappings` icindeki), bir `gestures` listesi, istege bagli
  `cooldown` (varsayilan 0.3 sn), `quantize`, `gain`, `dancer`. Bir hareket tek sese,
  acilis hareketleri tek hareket olarak yazilamaz.
- Ses, hareket baslarken bir kez calar (bir sonraki 16'lik notada); tekrar icin el inip
  yeniden kalkmali. Iki el birlikte kalkarsa ses bir kez calar.
- Senkron icinde el yukari artik tek hareket degil, bir vurustur: `config.yaml` >
  `beats` > `hits` listesindedir ve dustugu vurusun sesini calar. Yani ayni hareket
  senkron oncesinde `ab`, senkron icinde vurusa gore calar.
- `opening` bolumu yoksa dans hep senkrondadir ve tek hareketler hic calmaz.
- Videonun ilk 2.4 saniyesinde el kalkmaz, bu yuzden videonun basi degismedi. Elin
  kalktigi anlar (4.2 sn'den sonra) senkronun icindedir. Tek hareketi videoyla gormek
  icin `tools/make_handup_clip.py` once el kaldiran, sonra videonun basindan baslayan
  bir klip yapar: el kalkinca `ab`, sonra acilisa kadar sessizlik, acilistan sonra
  senkron (orada el kalkinca vurus sesi calar); video basa sarinca ayni sira yeniden.

```bash
.venv/bin/python tools/make_handup_clip.py ~/Downloads/dansonic.mp4 el_sonra_dans.mp4
.venv/bin/python run.py --source el_sonra_dans.mp4
```

### Senkronun sonu

Senkron son sesle biter. `config.yaml` > `senkron` > `bars` olcu surer (10: sarkinin
soylenen kismi 40 vurus; videoda soz 21.8 sn'de biter ve vokal kaydi 22. saniyeden
sonuna kadar sessizdir). Son vurus calar, sonra kapi kapanir: dansciler ne yaparsa
yapsin dansin hicbir sesi calmaz, ta ki acilis hareketi (ilk hareket) yeniden
gorulene kadar.

```yaml
senkron:
  bars: 10
```

- Sure acilistan sayilir: acilis hareketinin dustugu vurus 1. vurustur. Son vurusta
  yapilan hareket hala calar; sonraki vurusa dusen (son vurusun sonunda yapilan)
  hareket calmaz. Calmakta olan ses kesilmez.
- Bitince ekranda `bitti: ab-ab bekleniyor` yazar, tek hareketler yeniden calar ve
  yeni senkronu yalnizca acilis hareketi baslatir. Acilis pozu bitis anindan once
  yapilip hala tutuluyorsa sayilmaz: birakilip yeniden yapilmali.
- R'ye basinca ve video basa sarinca kapi yine kapanir. `senkron` bolumunu silerseniz
  senkron loop'a ya da videonun basa sarmasina kadar surer.
- Videoda (20 simule kosu): sarkinin son sesinden (22.1 sn) sonra eskiden her kosuda
  yaklasik 10 ses calardi (hareketle, bir ifade dahil); simdi en fazla 1, o da son
  vurusun kendi sesi. Videonun sonunda ikinci dansci acilis hareketini yapar
  (26.8 sn): bu sonraki turun ilk hareketidir ve gorulurse senkron yeniden baslar.
  Gercek uygulamayla ayni sira: acilis 2.3 sn, `senkron bitti` 20.1 sn'de (video
  22.1 sn), video basa sarinca yeniden acilis, ikinci `senkron bitti`.

## Video ile deneme

`run.py --source dansonic.mp4` videoyu loop'un tempo'suna getirir. Videonun muzigi
sarkinin 0.907 hizina yavaslatilmis, bu yuzden video 1.1025 kat hizli oynar ve
1. olcusu (2.19. sn) loop'un bir olcusune oturur; video basa sarinca loop yeniden
hizalanir. Ayar `config.yaml` > `video_sync`'te dosya adina gore; baska bir video
icin `--speed` ve `--downbeat` verin. Sonuc, videodaki dansci ile:

- Koreografinin 40 vurusunun 34'unde videodaki sesin aynisi calar (`ab-ab` iki vurus
  sayilir). Hareket basina ses modunda 13'tu, `ab-ab` eklenmeden once 31. Ilk iki
  olcu `ab`, `ab-ab`, `thin`, `wha-been`, `ab`, `been`, `thin`, `wha-been` sirasiyla
  calar; videodaki sira da bu.
- Cift `ab`: 1. ve 8. olcude `ab` hemen, ikinci `ab` 2. vurusta calar, videodaki
  gibi. Tek `ab`: 2. ve 4. olcu. Hareketten sese gecikme (vurusa oturtma dahil) her
  vurusta ortanca 160 ms; 1. vurus cift ihtimali yuzunden beklemez. 1. olcu istisna:
  acilis hareketi gorulene kadar beklenir (bkz. "Acilis").
- Senkron icinde ses hareket olan her yerde calar: hareketli surenin %99'unda bir ses var
  (`motion` olmadan %78). Ikinci dansci (bej yelek) poz olarak bulunamiyor ama
  9.7-13.6 sn'deki solosunda hareketi cizgiyi her vurusta surduruyor. Acilis `ab-ab`
  gorulene kadar (videoda 2.4 sn) ve senkron bittikten sonra (22.1 sn) ses calmaz.
- Sesler vurusa oturur: videoda calan 38 sesin 34'u tam vurusta, 4'u bir 16'lik sonra
  (acilisin ilk `ab`'i, iki ifade ve bir `wha-been`); hicbiri vurustan once degil.
- Kalan farklar (6 vurus): 3. olcunun 2. vurusunda videoda ikinci `ab` var, burada
  `been` (iki kol yok); 5. ve 9. olcunun 1. vurusunda videoda `been` var, burada `ab`;
  6. olcunun 1.-3. vurusunda videoda ikinci dansci icin dolgu ifadesi calar, burada
  duz vurus sesleri; ifadelerdeki yarim vurus heceleri (`ow`) yalnizca ifadeyle gelir.
- `tools/review/app_on_video.wav`: uygulamanin bu videoda calacagi ses (davul ve
  seslerle, video 1.1025 hizinda). Videonun kendi sesiyle karsilastirabilirsiniz.

## Hareket basina ses modu (`config.gestures.yaml`)

Her sese kendi hareketi verilir, vurusa bakilmaz. Videodan cikarilan eslesmeler:

| Ses | Hareket | Videoda | Not |
|-----|---------|---------|-----|
| ab | `right_arm_diag`: sag kol capraz yukari, sol kol asagida | 4.2 sn, 2. olcu 1. vurus | tek kol, tek `ab` |
| ab-ab | `hands_chest`: iki el gogusa | 2.3 sn, 1. olcu 1. vurus | iki kol, cift `ab` |
| been | `arm_sweep`: sag kol yana acik gogus hizasinda, sol on kol gogusun onunde | 8.7 sn, 4. olcu 2. vurus | 0.2 sn surer |
| been | `left_arm_out`: sol kol yana | - | v0 eskizi, videoda yok; her dansci icin calisir |
| thin | `squat_wide`: genis comelme, dirsekler disarda | 3.2 sn, 1. olcu 3. vurus | |
| thin | `right_hand_head`: sag el basa, sol kol yana | 5.2 sn, 2. olcu 3. vurus | |
| thin | `hands_on_hips`: eller belde | - | v0 eskizi, videoda yok; her dansci icin calisir |
| wha-been | `left_swipe_down`: sol kol hizla asagi | 3.7 sn (1. olcu 4. vurus), 19.9 sn (9. olcu 4. vurus) | 4. vurustaki kapanis hareketi |
| wha-been | `t_pose`: iki kol yana | - | videoda yok (19.6 sn'deki T bir kare surer); her dansci icin calisir |
| two-been-thin | `right_hand_high`: sag el yukarida, dirsek bukuk | 20.4 sn, 10. olcu | |
| ab-wha-two-been-thin | `right_arm_side`: sag kol yana, sol kol asagida | 20.2 sn, 10. olcu 1. vurus | `cooldown: 1.4` |
| ab-ow-ab-ow-thin | `arms_flail`: kollar sirayla yukari asagi | 14.1-16.2 sn, 7. olcu | `both_hands_up` da ayni sesi calar; `cooldown: 1.4`, `protect: 1.4` |

Videodan kaydedilen pozlar (`poses/*.json`) videodaki dansciya gore ayarli; esikleri
videoda baska bir harekette yanlis tetiklemeyen en genis deger (0.15-0.35).
Yerlesik kurallar (`t_pose`, `hands_on_hips`, `left_arm_out`, kol savurmalari)
vucut olcusune gore normallestirilmis ve her dansci icin calisir. Birisi bir pozu
tetikleyemiyorsa pozu `--record` ile onun ustune kaydedin
(`python run.py --record hands_chest --threshold 0.25`).

Bu modda videodaki dansci ile 8 sesin hepsi calar, ama ayni durus videoda farkli
vurusta farkli hecede tekrarlandigi icin 40 vurusun yalnizca 13'unde dogru ses
tetiklenir (simulasyon). Vurus modu bu yuzden varsayilan.

## Videodan alinan sesler

Videonun sesi, `Dansonic_blablabla_vocals.mp3` kaydinin 26.16. saniyesinden
baslayan 0.907 hizli bir kesiti. Sesler video yerine bu kaydin tam hizli
halinden kesildi: boylece davul loop'uyla (132.9 bpm) ayni tempoda.

- Kayitta her vurusta yeni bir hece baslar. Kesimler hecenin basladigi ana
  oturur ve bir sonraki hecenin hemen oncesinde biter; tek heceler 1 vurus
  (0.45 sn), `ab-ab` ve `two-been-thin` 2, diger iki ifade 3 vurus uzunlugundadir.
- `ab` olcu basi, `been` 2. vurus, `thin` 3. vurus, `wha-been` 4. vurustaki
  hecedir (olculerin cogunda ayni siralama). `ab-ab` 1., 3. ve 8. olcunun ilk iki
  vurusudur (`ab ab`), 0.91 sn; ilk yarisi `ab` ile ayni, ikinci `ab` ikinci yarisi.
  `ab-wha-two-been-thin` 6. ve 10. olcude, `ab-ow-ab-ow-thin` 7. olcude calan ifadedir.
- Eski `two-been-thin` bir sonraki hecenin (`wha`) basini da iceriyordu; yeni
  kesim tam vurusta biter.
- Kesim tablosu `sounds/video/cuts.json` icinde. Yeniden uretmek icin:
  `python tools/crop_sounds.py --vocals ~/Downloads/Dansonic_blablabla_vocals.mp3`
- Eski sesler `sounds/*.mp3` olarak duruyor. Onlara donmek icin `config.yaml`
  icinde `sounds_dir: sounds` yazin.

## Yeni hareket tanimlama

Koreografideki bir poz hazir listede yoksa kaydedilir:

```bash
.venv/bin/python run.py --record ab_sol_diz --legs
```

5 saniyelik geri sayimdan sonra pozu 1.5 saniye tutun. `poses/ab_sol_diz.json`
olusur ve `ab_sol_diz` artik `config.yaml` icinde hareket adi olarak
kullanilabilir. `--legs` dizleri ve ayak bileklerini de karsilastirmaya katar;
yoksa yalnizca kollar kullanilir. `--threshold` (varsayilan 0.3) toleransi
belirler: dusuk deger daha siki eslesme ister.

Pozlar govde uzunluguna gore normalize edilir, bu yuzden kayit yapan kisi ile
sahnedeki dansçinin boyu veya kameraya uzakligi farkli olabilir.

## Zamanlama

- `audio.quantize: 4`: tetiklenen ses bir sonraki 16'lik notaya oturtulur
  (en fazla ~113 ms bekler), boylece davulla ritimde kalir. `0` yapilirsa
  veya canlida G'ye basilirsa ses hareket algilandigi anda calar.
- `audio.choke: true`: yeni ses, hala calmakta olani keser.
- `cooldown` (`mappings` icinde, saniye): o ses calarken ayni sesi tetikleyen
  hareketler sesi bastan baslatmaz. Uzun ifadelerde (1.4 sn) kullanildi.
- `protect` (`mappings` icinde, saniye): o ifade calarken baska seslerin
  hareketleri onu kesmez, vurus sesleri de calmaz. Ifadenin biraz altinda tutulur
  (1.3 sn), boylece ifade biter bitmez vurus sesleri devam eder.
- Ses dosyalarinin basindaki sessizlik yuklemede kirpilir.
- Farkli bir loop dosyasi kullanilirsa `loop.bpm` ve `loop.beat_offset`
  degerleri guncellenmelidir.

## Ayar ipuclari

- Dansçilar bastan ayaga kadraja sigmali (ayak hareketleri icin bilekler gorunmeli).
- Cam arkasindan cekimde kamerayi cama yakin ve hafif acili koyun.
- Hareket kolay tetikleniyorsa `gestures.hold_frames` artirilir.
- Tum dansçilarin tetiklemesi istenirse `pose.mode: multi` yapilir.
- Acilis yakalanmiyorsa: ekranda `Yakin:` satirina bakin (hangi pozlar sayiliyor), K ile
  kendi ab-ab'nizi ogretin, `opening.margin` kucultulur (0.03 -> 0.0) ya da `hold`
  kisaltilir (0.3 -> 0.2); O tusu elle baslatir.
- Acilis yanlislikla aciliyorsa: `hold` artirilir (0.3 -> 0.5) ya da `loose` listesi
  kisaltilir; K ile yanlis ogrenilen pozun `poses/ab_ab_N.json` dosyasi silinir.
  Hafif poz modeliyle (`pose_landmarker_lite`) izleyici bazen tek karelik hatali bir poz
  verir: videoda dansin 13.86. saniyesinde `hands_on_chest` bir karede 0.027'ye cikar
  (tam modelde en fazla 0.003). `margin` 0.02 iken kapi kapaliyken bu kendiliginden
  aciyordu (188 kosunun 90'inda); 0.03'te hic acmadi. Gercek acilis 0.12-0.15'tedir.

## Dosyalar

```
run.py                canli dongu ve poz kaydi
config.yaml           loop, ses, kamera, hareket esikleri, vurus modu ve eslemeler
config.gestures.yaml  eski mod: her sese kendi hareketi
sounds/               drums-loop.mp3 ve onceki 7 ses
sounds/video/         videodan kesilen 8 ses ve cuts.json (kesim tablosu)
poses/                kaydedilen pozlar (5 tanesi videodan) ve K tusuyla ogretilen ab_ab_N.json dosyalari
tools/crop_sounds.py  vokal kaydindan sesleri keser
tools/make_handup_clip.py  tek hareketi denemek icin: once el kaldiran, sonra videonun basindan baslayan klip
tools/review/         index.html: sesleri dinle, kesimleri ve hareketleri kontrol et;
                      app_on_video.wav: uygulamanin dans videosunda calacagi ses
tests/                test_mapper.py: vurus modu, cift ab, acilis kapisi, tek hareketler ve senkronun sonu;
                      test_opening_pose.py: acilis hareketi baska pozlarla karismiyor, serbest hali yakalaniyor;
                      test_teacher.py: K tusuyla kendi ab-ab'ni ogretmek
                      (python -m unittest discover -s tests)
dansonic/
  audio_engine.py     loop + tek atimlik sesler, kuantalama, choke, bir sesin ortasindan baslatma
  sounds.py           ses yukleme, sessizlik kirpma
  gestures.py         hareket kurallari, kayitli pozlar, durum makinesi
  pose_tracker.py     MediaPipe PoseLandmarker (CPU, coklu kisi)
  dancers.py          tespitleri dansçi slotlarina atama
  actions.py          hareket -> ses (vurus modu, tek/cift ab, acilis kapisi, cooldown, protect)
  ui.py               goruntu uzeri cizim ve ses paneli
  song.py             vurus gridi
  camera.py           kamera/video okuyucu (video hizi, basa sarma)
  motion.py           goruntudeki hareketi kare farkiyla bulur (beats > motion)
assets/models/        MediaPipe poz modelleri
```
