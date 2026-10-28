# Bilgi Yarışması — Web Sitesi

Netlify'a bu klasörü olduğu gibi yükle (`netlify.toml` hazır).

- `index.html` — oyun (tek başına + online düello)
- `questions.json` — soru havuzu (masaüstü uygulaması da bu dosyayı sitenin adresinden çeker)
- `stil.css`, `iletisim.html`, `tesekkur.html` — ortak stil ve iletişim sayfaları
- `service-worker.js` — eski önbellekleri temizler
- `baslat.bat` — siteyi bilgisayarında denemek için yerel sunucu (yayın için gerekmez)
- `prompt.txt` — yapay zekâya yeni soru yazdırma talimatı

Online düello, masaüstü uygulamasıyla aynı MQTT kanalını kullanır; ikisi birbiriyle eşleşir.
