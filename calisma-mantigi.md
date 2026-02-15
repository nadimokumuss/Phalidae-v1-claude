Şimdi bu projeyi seninle farklı bir seviyeye getireceğiz.

Ben bu botun bana sadece maksimum son 200 mumu tarayıp, belli başlı indikatörleri çalıştırıp, destek direnç çizgileri çekip işlem vermesini istemiyorum. Kendi kendine piyasayı öğrensin istiyorum. Peki nasıl olacak? Dikkat etmemiz gereken birkaç nokta var önce onları listelemek istiyorum.

1- Bu bot arkaplanda sürekli çalışan bir bot olmalı. Potansiyeli olan tüm coinleri her dakika tarayacak ve fiyatlarını veritabanına kaydedecek. Yani sadece "piyasayı tara" dediğimde son 200 mumu tarayıp yoluna devam etmeyecek. 200 mum saatlik periyotta 8 gün eder ve bu kripto para borsası için hiç yeterli bir zaman dilimi değil. Bu bot belki aylarca biriktirdiği veri ile para kazandırmaya başlayacak. Bu yüzden top 30 ya da 50 coinin tüm fiyat hareketleri arkaplanda her dakika ya da bu çok maliyetli olacaksa her 5 ya da 15 dakikada bir kaydedilnmeli.

2- Bot arkaplanda coinlerin fiyatlarını toplarken aynı zamanda işlem potansiyeli var mı yok mu bunu da analiz etmeli. Yaptığı analizlerde çıkan sonuçları da sanki o işleme girmiş gibi ayrı bir yere kaydetmeli. Örneğin "BTCUSDT - Long | Giriş: 71.546 USD – TP: 74.356 USD – SL: 67.554 USD | Kaldıraç: 15x – Likidasyon Fiyatı: 65.876 USD" gibi işlemlere simüle bir şekilde girmeli ve bunların da kaydını tutmalı. Sonrasında girdiği işlemleri düzenli olarak takip edip karda mı zararda mı olduğunu da bakmalı ve bunun da kaydını tutmalı. Hatta hangi coine hangi işlemi neden girdiğine dair açıklama da yapmalı ki ben nasıl bir mantıkla ilerlediğini görebileyim. 

3- İndikatörleri, mum formasyonlarını, destek & direnç çizgilerini, fibonacci, pivot points vs. seviyelerini, S/R yöntemlerini ve diğer tüm grafikleri kafasına göre kullanmamalı.Bot, analiz felci geçirmemeli. Her bir indikatörü, mum formasyonunu, grafikleri, çizgileri vs. her şeyi birbirleriyle uyumlu olacak şekilde kullanmalı yani deneyebildiği her varyasyonu denemeli ve bu denediği varyasyonların da sonuçlarını kaydedip zamanla kusursuz bir analiz stratejisine ulaşabilmeli. Örneğin bir coine baktığı zaman "Bu mum grafiğinde ve formasyonunda rsı bandı ve tema indikatörü daha iyi çalışıyor. Öyleyse bu senaryoda bu denklemi kullanmalıyım. Analiz sonucunda işlem Short..." şeklinde bir analiz çıkartabilmeli. Bunu yapmazsak indikatörler birbirleriyle çelişebilir, mum formasyonları kafa karıştırabilir ya da doğru analiz yanlış sonuca çıkabilir. Aşağıda bir örnekle sana olası senaryoyu anlatayım.

Bitcoin $90.000'den $95.000'e sert bir mumla çıktı diyelim.

1. Trend İndikatörleri (Örn: EMA, SuperTrend): "Fiyat ortalamanın üstüne çıktı, trend çok güçlü! AL (LONG)" diye bağırır.
2. Momentum İndikatörleri (Örn: RSI, Stochastic): Fiyat çok hızlı yükseldiği için aşırı alım (Overbought) bölgesine girer. RSI 80 olur. Bu indikatörün kuralı şudur: "Aşırı şişti, düzeltme gelecek. SAT (SHORT)".

4- Her bir coinin tarihi, geleceği, teknolojisi, yazılımı ve vadettiği şeyler farklıdır. Test ettiği analiz varyasyonlarını her coine uygulamamalı. Her coin için ayrı varyasyon testi yapılmalı. 

5- Kaydı tutulan ve alınan her işlemi, her bir detayı panelde görmek istiyorum. Ben de neyin kayıt edildiğini, neyin dikkate alındığını ve nasıl hareket edildiğini görmeliyim.

Anlatabildim mi? Senden basit bir denklemle çalışıp mantıklı gördüğü işlemi veren bir bot yapmanı istemiyorum. Senden düşünen, test ve analiz eden, kayıt tutan ve en iyi varyasyonlar ile en iyi uyumu yakalayıp yüksek doğruluk oranı olan bir canavar yapmanı istiyorum. Unutma başarılı bir bot, rastgele 10 indikatör değil, farklı kategorilerden seçilmiş 3 indikatör kullanır. Buna "Confluence" (Kesişim) denir. Yani:

Tüm indikatörleri kullanmak yerine, onları bir "Onay Mekanizması" (Filter Hierarchy) olarak kullanmalısın.
Botumuza şu hiyerarşiyi öğretmeliyiz:
1. Kral (Trend): Önce Büyük Resme bak. (Örn: Fiyat EMA 200'ün üstünde mi? Evet. O zaman sadece LONG ara. Asla SHORT bakma).
2. Vezir (Giriş): Şimdi RSI'a bak. Düşüş var mı? (Örn: Trend yukarı ama RSI düştü -> Alım Fırsatı).
3. Asker (Hacim): Bu yükselişi destekleyen hacim var mı? (Onay).

Bunu sadece EMA ya da RSI üzerinden düşünme, devreye mum formasyonlarını, fibonacci verilerini ve diğer her şeyi dahil edebilirsin. Amaç birbiriyle uyumlu ve her durumda doğru sonuç veren çeşitliliği bol stratejiler yaratmak.
