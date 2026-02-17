## Geliştirilmiş Prompt (V2 – Debug + Upgrade Master Spec)

Sen, halihazırda çalışan (ama eksikleri olan) kripto trading asistan/bot sistemimi **profesyonel seviyeye** çıkarmakla görevli “lead quant engineer + backend architect + reliability engineer”sın.

Mevcut durum: Bot sinyal veriyor ve TradingView paper trading ile genel anlamda kâr var; fakat sistemin **kendini eğitmesi**, **işlemleri takip etmesi**, **haber ve gerçek insan analizlerinden ders çıkarması**, **geçmiş veriyi biriktirmesi**, **açıklamalı ve güven skorlu sinyal üretmesi**, **risk/portföy yönetimi** ve **agent’ların gerçekten çalışması** konusunda ciddi eksikler var.

Bu çalışmada iki hedefin var:

1. **Kapsamlı Teşhis (Root-cause analysis):** Sistem neden arkaplanda düzgün çalışmıyor? (ör. dashboard’da 10 dk OHLCV yok, auto signals yok, bot kendi sinyaline girmiyor)
2. **Sistematik Geliştirme Planı + Uygulama Tasarımı:** Aşağıdaki özellikleri ekle ve uçtan uca doğrulanabilir hale getir.

---

# A) Öncelikli Eksikler (Eklenmesi Gereken Yetenekler)

## 1) Haber Takibi ve Etki Analizi (News Engine)

* Sistem; coin/market ile ilgili haberleri ve makro olayları takip edecek.
* Her haber için:

  * İlgili coin(ler), etki yönü (bullish/bearish/neutral), etki şiddeti (0–1)
  * “Event window”: haber öncesi/sonrası volatilite ve fiyat davranışı analizi
  * Sinyal üretiminde **risk filtresi**: “yüksek belirsizlikte pozisyon küçült / işlem açma”
* Çıktı: dashboard’da “Today’s Market Events” + coin bazlı “news risk score”.

## 2) “Gerçek İnsan Analizlerinden Ders Alma” (External Analysis Notebook)

* Sistem, X / forum / yayın / analiz paylaşım platformlarından gelen **başarılı analiz örneklerini** bir “Analiz Kütüphanesi”ne ekleyecek.
* Her örneği:

  * İçerik özeti (teknik argümanlar)
  * Kullanılan araçlar (S/R, formasyon, fib, makro, orderflow vs.)
  * Sonucun doğrulanması (sonraki fiyat hareketi ile “haklı mı/haksız mı?”)
  * “Neyi iyi yaptı?” → sistem için öğrenme notu (pattern/heuristic)
* Bu kısım “kopyala-yapıştır sinyal” değil; **gerçek dünyadan ders çıkarma** mekanizması olacak.

## 3) TP/SL Yönetimi ve Kademeli Çıkış (Trade Management)

Mevcut sorun: TP’ler çok uzak ve takip yok.

İstediğim:

* İşlem kâra geçince otomatik “trade management”:

  * Break-even: belirli kâr seviyesinde SL girişe çekilsin
  * Partial take profit: örn +20$ PnL’de %50 kar al
  * TP2/TP3 kademeleri
  * Trailing stop opsiyonu (ATR tabanlı veya structure tabanlı)
  * Time-stop: hedefe makul sürede gitmiyorsa çık
* Bunun için sistem, açtığı tüm paper trades’i **sürekli izlemeli** ve her güncellemede karar log’u tutmalı.

## 4) Derin Geçmiş Veri (Backfill + Continuous Storage)

* “Son 200 mum” yetersiz.
* Sistem her coin için mümkün olan en eski tarihe kadar backfill yapacak ve DB’ye yazacak.
* Her backtest/analiz sonucu:

  * versiyonlanmış şekilde kaydedilecek
  * panelde görülebilecek
  * “hangi dönemde hangi strateji işe yaradı?” raporu çıkarılacak.

## 5) Sürekli Güncellenen Otomatik Analiz (Always-on Commentary)

* Her sayfanın başında “son güncellenme + otomatik yorum” olacak.
* Sistem sadece ham veriyi göstermeyecek; şunu yazacak:

  * “Şu an market rejimi: trend/range”
  * “Coin’de kritik seviyeler”
  * “Yakın vadede risk: news/volatility/liquidity”
  * “Sinyal üretmedim çünkü … / ürettim çünkü …”

## 6) Açıklamalı Sinyal Zorunluluğu (Decision Trace)

Her sinyal şu formatta olmalı:

* Bias (trend filtresi) → neden?
* Trigger (giriş) → hangi şart tetikledi?
* Confirmation → ne onayladı?
* Risk planı (SL, TP, RR, leverage) → nasıl belirlendi?
* Alternatif senaryolar → neden elendi?
* “Invalidation” → hangi koşulda sinyal iptal?

## 7) “High Confidence” Sinyal Mantığı

Şu ana kadar yüksek güvenlikli sinyal yok → Demek ki:

* ya eşik çok sıkı
* ya skorlaman yanlış
* ya da confluence setlerin zayıf

İstediğim:

* Güven skoru 0–100 üret.
* High confidence = örn 75+ (konfigüre edilebilir)
* Skor; confluence sayısı, rejim uyumu, volatilite, likidite, news riski, geçmiş performans gibi bileşenlerden gelsin.
* Panelde: “neden 62 geldi, neden 81 geldi?” şeffaf olsun.

## 8) Paper Portfolio: 1000$ ile Risk/Portföy Yönetimi

* Sistem 1000$ başlangıç sermayesiyle **kendi paper trading** yapacak.
* Her coin’e aynı riskle girilmeyecek:

  * Coin volatilitesi (ATR), likidite, spread, news riski, korelasyon → pozisyon boyutunu etkilesin
* Kurallar:

  * Max günlük DD
  * Max açık pozisyon sayısı
  * Korelasyon filtresi (BTC ile aşırı korele altları aynı anda şişirme)
  * İşlem başına risk % (dinamik)

## 9) “Hedefe Tahmini Süre” (ETA) Zorunlu

* Her sinyal, hedefe ulaşma tahmini süre versin (örn: 6–18 saat, 1–3 gün).
* ETA; geçmiş benzer setup’ların “time-to-target” dağılımından türetilsin.
* Ayrıca “bu kadar beklemek normal mi?” sorusuna cevap verecek “time-stop” kuralı tanımlansın.

## 10) Agent’lar Gerçekten Çalışıyor mu? (Reliability + Observability)

Sistemde şu agent’lar var varsayımı:

* Data fetcher
* Analyzer
* Commentator
* Signal generator
* Portfolio manager
* DB ↔ Site validator

İstediğim:

* Her agent için “heartbeat” (son çalışma zamanı)
* İş kuyruğu metrikleri (kaç job bekliyor)
* Hata logları ve retry sayıları
* Dashboard’da “Agent Health” paneli (çalışmayan agent maaş almamalı 😄)

---

# B) Şu Anki Hatalar (Bug Report) – Teşhis ve Fix Beklentisi

## Kritik Bug 1: Arkaplanda çalışmıyor gibi

* 10 dakika geçiyor, dashboard’da OHLCV yok.
  İstediğim:
* Fetch döngüsü var mı?
* Cron/worker ayakta mı?
* API rate limit mi?
* DB write fail mi?
* UI cache mi?
* Gözlemlenebilirlik yoksa önce telemetry ekle.

## Kritik Bug 2: Sistem sinyale kendi girmiyor → öğrenemiyor

* Paper trading modülü tetiklenmiyor olabilir.
  İstediğim:
* Sinyal üretilince otomatik “paper order create” çalışmalı.
* Sonra takip ve kapanış otomatik olmalı.
* Her adım loglanmalı (signal_id → trade_id mapping).

## Kritik Bug 3: “Otomatik sinyal üretilmedi” ekranı hiç dolmuyor

* Analyzer ilk çalıştığında doldurması gerekirken dolmuyor.
  İstediğim:
* Bu alanın veri kaynağı nedir?
* Sinyal tablosu yazılıyor mu?
* UI hangi endpoint’i çağırıyor?
* Validasyon agent’ı data mismatch buluyor mu?

---

# C) İstediğim Çıktılar (Bu Prompt’a Cevabın)

Bu prompta cevap verirken şu deliverable’ları üret:

1. **Root-cause checklist**: yukarıdaki 3 bug için olası nedenler + test adımları + kesin fix stratejisi
2. **Yeni modül tasarımı**: News Engine + External Analysis Notebook + Trade Management + Portfolio
3. **Veritabanı şeması önerisi**: candles, signals, trades, trade_updates, strategy_variants, confidence_scores, news_events, external_analyses, agent_health, audit_logs
4. **Event-driven akış**: “candle geldi → analiz → sinyal → paper trade → trade management → sonuç → öğrenme”
5. **Panel ekranları**: Market Overview, Coin Detail, Signals, Trades, Strategy Lab, News, External Library, Agent Health, Data Integrity
6. **MVP→V1→V2 roadmap**: En hızlı şekilde “çalışır” hale getir, sonra öğrenme ve dış kaynakları ekle.

Öncelik sırası:

1. Always-on veri + agent health + auto signals (çalışıyor mu?)
2. Paper portfolio + trade tracking + kademeli TP/SL
3. Backfill + geçmiş analiz raporları
4. News + external analysis library
5. High confidence scoring + ETA + rejim uyumu optimizasyonu

---

Bu sistemi tasarlarken “analiz felci” yasak:

* Default: Trend bias + 1 trigger + 1 confirmation (+ risk)
* Her coin için ayrı öğrenme
* Her karar açıklamalı ve ölçülebilir

Ve son şart:

* Ben panelde her şeyi göreceğim: veri geldi mi, sinyal üretildi mi, trade açıldı mı, güncel PnL ne, agent’lar çalışıyor mu, sistemin yorumu ne.

Son olarak arayüzün biraz daha güzel görünmesini istiyorum. ufak iyileştirmeler yaparsan sevinirim.