@echo off
title Bilgi Yarismasi - Test Sunucusu
cd /d "%~dp0"

if not exist "index.html" (
  echo [HATA] index.html bulunamadi. Bu dosyayi sitenin klasorune koy.
  pause
  exit /b 1
)

set "PYC="
where python >nul 2>nul && set "PYC=python"
if not defined PYC where py >nul 2>nul && set "PYC=py"
if not defined PYC (
  echo [HATA] Python bulunamadi. python.org adresinden kur ve "Add Python to PATH" kutusunu isaretle.
  pause
  exit /b 1
)

set "PY=%TEMP%\bilgi_sunucu.py"
>"%PY%" echo import http.server, webbrowser, threading
>>"%PY%" echo class H(http.server.SimpleHTTPRequestHandler): end_headers=lambda self:(self.send_header("Cache-Control","no-store"),http.server.SimpleHTTPRequestHandler.end_headers(self))[1]; log_message=lambda *a:None
>>"%PY%" echo s=http.server.ThreadingHTTPServer(("127.0.0.1",0),H)
>>"%PY%" echo p=s.server_address[1]
>>"%PY%" echo print(f"Calisiyor: http://localhost:{p}/  (kapatmak icin bu pencereyi kapat)")
>>"%PY%" echo threading.Timer(0.5,lambda:webbrowser.open(f"http://localhost:{p}/")).start()
>>"%PY%" echo s.serve_forever()

%PYC% "%PY%"
