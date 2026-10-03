# Dansonic v1

Tek kamera ile dansçilarin hareketlerini algilar; arkada surekli donen davul
loop'unun ustune, her harekete atanmis vokal sesini calar. GPU gerekmez.
Sahnede birden fazla dansçi olsa da yalnizca biri takip edilir. `v0/`
klasorunden bagimsizdir.

## Prova duzeni

- Arka plan: `sounds/drums-loop.mp3` surekli doner (132.9 bpm).
- Hareketle calinan 7 ses: `ab`, `been`, `thin`, `wha-been`, `two-been-thin`,
  `ab-wha-two-been-thin`, `ab-ow-ab-ow-thin`.
- Her sese en az bir hareket atanir (`config.yaml` > `mappings`). Bir sese
  birden fazla hareket yazilabilir; ornegin her "ab" icin ayri hareket.
- Ses, poz basladigi anda bir kez calar. Tekrar calmasi icin dansçi pozdan
  cikip yeniden girmelidir.

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
| `run.py --no-camera` | kamerasiz, sesleri 1-7 tuslariyla dene |
| `run.py --source klip.mp4` | kamera yerine video dosyasi |
| `run.py --record AD` | tutulan pozu AD adli hareket olarak kaydet |

Tuslar: SPACE dur/devam, R loop'u basa al, G kuantalama ac/kapa, M ayna,
T takip edilen dansçiyi degistir, Q cikis, 1-7 sesleri sirayla calar.

## Varsayilan eslemeler

v0'daki eskizlerden (`v0/dansonic_move/*.jpeg`) yola cikilarak secildi;
koreografiye gore `config.yaml` icinden degistirilir.

| Ses | Hareket | Aciklama |
|-----|---------|----------|
| ab | right_hand_chest, left_hand_chest | el ayni taraftaki omuza/goguse |
| been | right_foot_up, left_foot_up | bir ayak yerden kalkik |
| thin | hands_on_hips | eller belde, dirsekler disarda |
| wha-been | right_forearm_front, left_forearm_front | on kol govdenin onunde, diger kol asagida |
| two-been-thin | t_pose | iki kol yana acik |
| ab-wha-two-been-thin | both_hands_up | iki el basin ustunde |
| ab-ow-ab-ow-thin | arms_crossed | kollar gogus onunde capraz |

Diger hazir hareketlerin listesi `config.yaml` basindadir.

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
- Ses dosyalarinin basindaki sessizlik yuklemede kirpilir.
- Farkli bir loop dosyasi kullanilirsa `loop.bpm` ve `loop.beat_offset`
  degerleri guncellenmelidir.

## Ayar ipuclari

- Dansçilar bastan ayaga kadraja sigmali (ayak hareketleri icin bilekler gorunmeli).
- Cam arkasindan cekimde kamerayi cama yakin ve hafif acili koyun.
- Hareket kolay tetikleniyorsa `gestures.hold_frames` artirilir.
- Tum dansçilarin tetiklemesi istenirse `pose.mode: multi` yapilir.

## Dosyalar

```
run.py                canli dongu ve poz kaydi
config.yaml           loop, ses, kamera, hareket esikleri, eslemeler
sounds/               drums-loop.mp3 ve 7 ses
poses/                kaydedilen pozlar
dansonic/
  audio_engine.py     loop + tek atimlik sesler, kuantalama, choke
  sounds.py           ses yukleme, sessizlik kirpma
  gestures.py         hareket kurallari, kayitli pozlar, durum makinesi
  pose_tracker.py     MediaPipe PoseLandmarker (CPU, coklu kisi)
  dancers.py          tespitleri dansçi slotlarina atama
  actions.py          hareket -> ses
  ui.py               goruntu uzeri cizim ve ses paneli
  song.py             vurus gridi
  camera.py           kamera/video okuyucu
assets/models/        MediaPipe poz modelleri
```
