# Bilgi Yarışması — Windows (wxPython) Uygulaması

Ekran okuyucu uyumlu masaüstü sürümü. Tek başına oyun + online düello (sitedeki oyuncularla eşleşir).

## Çalıştırma
`calistir.bat` — gerekli paketleri kurar ve uygulamayı açar.

## Taşınabilir EXE (32 bit)
`exe_olustur.bat` — 32 bit Python (3.11 önerilir) ile `BilgiYarismasi_tasinabilir.zip` üretir.

## Dosyalar
- `bilgi_yarismasi.py` — ana uygulama ve arayüz
- `online.py` — MQTT taşıyıcı, eşleşme, düello kuralları
- `online_ui.py` — online ekranları
- `questions.json` — internet yokken kullanılan yedek soru havuzu (normalde sitenin adresinden çekilir)
- `requirements.txt` — paketler

Sorular her oyunda `https://bilgiarena.netlify.app/questions.json` adresinden yenilenir.
