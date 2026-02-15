Sen, kripto piyasasında **sürekli çalışan**, **veri toplayan**, **strateji varyasyonlarını test eden**, **simülasyonla işlem açıp performansını ölçen** ve zamanla **coin bazında en iyi confluence setlerini öğrenen** bir trading botu tasarlayan kıdemli bir quant engineer + backend architect’sin.

Hedef: “Son 200 mum + birkaç indikatör” değil; **aylarca veri biriktirip** coinlerin davranışlarını öğrenen, stratejileri sistematik şekilde deneyen ve yalnızca **uyumlu sinyallerin kesişimi** ile işlem üreten **kendini optimize eden bir sistem** kurmak.

### 0- Kapsam ve Çalışma Modu (Always-on)

* Bot **7/24 arkaplanda** çalışacak.
* Top **30–50 coin** (konfigüre edilebilir) her **1 dakika** (maliyet yüksekse 5/15 dk opsiyonu) taranacak.
* Her taramada:

  * OHLCV (mum) verisi
  * Orderbook/Spread (varsa)
  * Volatilite ölçümleri
  * Funding / Open Interest (varsa)
  * Market regime etiketleri (trend, range, high vol vb.)
  * Tüm veriler **zaman serisi DB’ye** kaydedilecek.

**Önemli:** Bot, sadece manuel “tara” komutuyla çalışan bir script olmayacak; veri akışı sürekli olacak ve veri büyüdükçe analiz kalitesi artacak.

---

### 1- İki Paralel Motor: Data Collector + Strategy Lab

Bot iki ana süreçten oluşmalı:

#### A- Data Collector (Toplayıcı)

* Her coin için seçilen timeframelerde (örn. 1m/5m/15m/1h/4h/1d) veriyi düzenli toplar.
* Veri bütünlüğü: eksik mum tamamlama, gecikme/duplikasyon kontrolü, timestamp doğrulama.
* Gerekirse “backfill” (geçmiş veriyi tamamlama) yapar.

#### B- Strategy Lab (Öğrenen/Test Eden)

Data Collector veri yazarken, Strategy Lab sürekli şu işleri yapar:

* Her coin için “strateji varyasyonları” üretir ve dener.
* Her varyasyonun performansını ölçer.
* Zamanla **coin bazında** en iyi performans veren confluence setlerini seçer (global değil, coin’e özel).

---

### 2- Simülasyon (Paper Trading) ve Kayıt Disiplini

Bot, sinyal gördüğünde **gerçek emir açmadan** simülasyon pozisyonu açar ve bunu ayrıntılı kaydeder:

Örnek kayıt formatı:

* `BTCUSDT | LONG`
* Entry: 71,546
* TP: 74,356
* SL: 67,554
* Leverage: 15x
* Estimated liquidation: 65,876
* Risk:Reward: 1:2.4
* Timeframe: 1h (confluence 15m + 4h)
* Fee/Slippage varsayımları
* “Bu işlemi neden açtın?” açıklaması (insan okuyabilir şekilde)

Sonra bot:

* Açık simülasyon işlemlerini düzenli takip eder (bar-by-bar).
* TP/SL/Time-stop/Trailing gibi çıkış kurallarına göre kapatır.
* Her işlem için sonuç üretir:

  * PnL, MFE/MAE, drawdown, winrate, expectancy
  * İşleme girilen anın “market regime” etiketi
  * Hangi sinyaller işe yaradı/yaramadı

---

### 3- Analiz Felcini Önlemek: Filter Hierarchy + Confluence

Bot **her şeyi aynı anda** kullanmayacak. “Onay Mekanizması” kurallarıyla çalışacak:

#### Filter Hierarchy (örnek yapı)

1. **Kral – Trend Filtresi (Bias)**

   * Büyük resimde yön belirle.
   * Örn: 200 EMA üstüyse yalnızca LONG; altındaysa yalnızca SHORT.
   * Alternatif trend tanımları varyasyon olarak denenebilir (EMA200, SuperTrend, Market Structure vb.)

2. **Vezir – Giriş Mantığı (Trigger)**

   * Trend yönünde “en iyi giriş” sinyali.
   * Örn: RSI pullback, market structure retest, belirli mum formasyonları, fib retracement, pivot reclaim vb.
   * Aynı anda yalnızca 1–2 trigger seçilir (varyasyon olarak test edilir).

3. **Asker – Onay (Confirmation)**

   * Hacim, volatilite, orderflow, OBV, volume profile, ATR koşulları vb.
   * “Bu hareket gerçekten destekleniyor mu?” kontrolü.

**Kural:** Başarılı bot = rastgele 10 indikatör değil; farklı kategorilerden seçilmiş 3 onaylı araç.
Bot, her sinyalde en fazla **N adet bileşen** kullanır (örn N=3 veya 4). N konfigüre edilebilir ama default küçük olmalı.

---

### 4- Çelişen İndikatörleri Yönetme (Regime-Aware Seçim)

Bot şu problemi çözmeli: Trend indikatörü LONG derken momentum SHORT diyebilir.

Bu yüzden bot:

* Piyasayı “rejim” olarak sınıflandırır: **Trend / Range / High Vol / Low Vol / Breakout / Mean Reversion**
* Her rejimde hangi confluence setinin iyi çalıştığını öğrenir.
* Örnek çıktı üretebilmelidir:

  * “BTC 1h grafikte trend güçlü (bias long). RSI overbought görünse de bu rejimde RSI sell sinyali düşük başarı veriyor. Bu yüzden RSI’yı exit/filtre olarak kullanıp giriş tetikleyicisini structure retest + volume confirm seçiyorum.”

---

### 5- Coin Bazında Öğrenme (Her coin kendi karakteri)

* Strateji varyasyonları **tüm coinlere körlemesine** uygulanmayacak.
* Her coin için:

  * Volatilite profili
  * Likidite
  * Trend davranışı
  * Mean-reversion eğilimi
  * Haber/etki hassasiyeti (opsiyonel)
    gibi özelliklere göre ayrı test havuzu tutulacak.
* Sonuçta bot “coin X’te en iyi çalışan confluence seti Y” diyebilmeli.

---

### 6- Strateji Varyasyon Üretimi ve Öğrenme Döngüsü

Botun öğrenme döngüsü:

1. Strateji şablonları tanımla (Trend + Trigger + Confirmation + Risk)
2. Bu şablonlardan varyasyonlar türet:

   * Parametre aralıkları (EMA periyodu, RSI bandı, ATR katsayısı…)
   * Farklı mum formasyonu setleri
   * Fibo/pivot kullanım biçimleri
3. Her varyasyonu paper trade ile dene.
4. Performansını ölç.
5. Zayıf varyasyonları eler, iyi varyasyonları “aktif set” yapar.
6. Overfitting’e karşı:

   * Walk-forward / rolling validation
   * Out-of-sample test
   * Rejim bazlı skorlar
7. Sonuçları coin bazında saklar.

----

### 7- Risk Yönetimi (Zorunlu)

Botun asla ihmal etmemesi gerekenler:

* Pozisyon boyutu: fixed risk (örn %0.5–1)
* SL zorunlu (yoksa işlem yok)
* RR alt limiti (örn 1:1.8 altı işlem açma)
* Maks açık pozisyon sayısı
* Correlation kontrolü (aynı yönde 10 coin açıp “tek trade” gibi risk almak yok)
* Günlük max drawdown limiti (limit aşılırsa “cooldown”)

---

### 8- Panel ve Şeffaflık (Ben her şeyi göreceğim)

Ben bu sistemi bir panelden izleyeceğim. Panelde:

* Toplanan verilerin durumu (hangi coin, hangi timeframe, son güncelleme)
* Her coin için:

  * Aktif strateji seti (confluence bileşenleri + parametreleri)
  * Son sinyaller ve nedenleri (açıklamalı)
  * Açık simülasyon işlemleri + canlı PnL
  * Kapanmış işlemler (rapor)
* “Deney Laboratuvarı” ekranı:

  * Denenen varyasyonlar
  * Başarı skorları (winrate, profit factor, expectancy, max DD)
  * Rejim bazlı performans
* Her işlem için “Decision Trace”:

  * Bias neydi?
  * Trigger neydi?
  * Confirmation neydi?
  * Neden bu set seçildi?
  * Hangi alternatifler elendi?

---

### 9- Çıktı Formatı (Botun Dili)

Botun ürettiği her sinyal/işlem kaydı şu formatta olmalı:

**Sinyal Özeti**

* Coin / Yön / Timeframe
* Entry / SL / TP / Leverage / Liq
* Risk-Reward
* Güven skoru (0–100)

**Gerekçe (Confluence Trace)**

* Trend filtresi sonucu:
* Giriş tetikleyicisi:
* Onay mekanizması:
* Rejim sınıflandırması:
* Bu coin’de bu setin geçmiş başarımı:

**Simülasyon Takibi**

* İşlem açıldı / açık / kapandı
* Anlık PnL, MFE/MAE
* Kapanma nedeni (TP/SL/Time stop/Trailing)

---

### 10- İstediğim Çıktı: Sen bana ne üreteceksin?

Şimdi bu prompta göre:

1. Uygulanabilir bir **sistem mimarisi** (modüller, servisler, veri akışı)
2. DB şeması taslağı (fiyat verisi, sinyal, trade, strateji, varyasyon, skor)
3. Strateji şablon formatı (JSON gibi)
4. Öğrenme döngüsü / seçim algoritması (basit başlayıp gelişen)
5. Panel için ekran listesi + API uçları

şeklinde ilerleyebilirsin.