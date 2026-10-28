# -*- coding: utf-8 -*-
"""
Bilgi Yarışması - erişilebilir wxPython sürümü (tek başına oyun)

- Sorular her oyunda https://bilgiarena.netlify.app/questions.json adresinden çekilir.
  İnternet yoksa son indirilen kayıtlı kopya, o da yoksa yanındaki questions.json kullanılır.
- Sesler Python ile üretilir (ek ses dosyası gerekmez), ilk açılışta bir kez oluşturulup saklanır.
- Sorular ve sonuçlar ekran okuyucuya kendiliğinden okutulur (accessible_output2 ya da SAPI).
- Kısayollar: 1-4 şık seç, C soruyu oku, T kalan süre, P durum, J yarı yarıya jokeri,
  Yön tuşları şıklar arasında gezer, Esc oyundan çıkar.
"""
import array
import json
import math
import os
import random
import sys
import threading
import time
import urllib.request
import wave
import webbrowser

import wx

import online as ol
from online_ui import OnlineMixin, ONLINE_SCREENS

ONLINE_SCREENS_KEYS = ONLINE_SCREENS

try:
    import winsound  # yalnızca Windows
except ImportError:  # pragma: no cover
    winsound = None

APP_NAME = "BilgiYarismasi"
APP_TITLE = "Bilgi Yarışması"
QUESTIONS_URL = "https://bilgiarena.netlify.app/questions.json"
CONTACT_URL = "https://bilgiarena.netlify.app/iletisim.html"
WAIT_MESSAGE = "Lütfen bekleyin, ufak birkaç işlem yapıyoruz…"
LETTERS = "ABCD"
SOUND_VERSION = "2"
TIME_CHOICES = [0, 15, 30, 45, 60, 90]
ROUND_COUNT = 10


def base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def data_dir():
    if getattr(sys, "frozen", False):  # taşınabilir: veriler exe'nin yanındaki "veri" klasöründe
        d = os.path.join(base_dir(), "veri")
        try:
            os.makedirs(d, exist_ok=True)
            test = os.path.join(d, ".yazma_testi")
            with open(test, "w") as f:
                f.write("1")
            os.remove(test)
            return d
        except OSError:
            pass
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") \
        or os.path.join(os.path.expanduser("~"), ".local", "share")
    d = os.path.join(root, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


# =====================================================================
#  SES ÜRETİMİ (saf Python, ek paket gerekmez)
# =====================================================================
SR = 22050


class Mix:
    """Tek kanallı, float karışım tamponu."""

    def __init__(self, dur):
        self.n = int(SR * dur)
        self.b = [0.0] * self.n

    def tone(self, f, t, d, kind="sine", v=0.35, f2=None, lp=None):
        s0 = int(t * SR)
        n = min(int(d * SR), self.n - s0)
        if n <= 0:
            return
        att = 0.012
        ratio_log = math.log(0.0001 / v)
        sweep = math.log(f2 / f) if f2 else 0.0
        a = 1 - math.exp(-2 * math.pi * lp / SR) if lp else 0.0
        y1 = y2 = 0.0
        ph = 0.0
        buf = self.b
        two_pi = 2 * math.pi
        for i in range(n):
            x = i / SR
            fr = f * math.exp(sweep * x / d) if f2 else f
            ph += fr / SR
            p = ph % 1.0
            if kind == "sine":
                w = math.sin(two_pi * ph)
            elif kind == "triangle":
                w = 4 * abs(p - 0.5) - 1
            elif kind == "sawtooth":
                w = 2 * p - 1
            else:  # square
                w = 1.0 if p < 0.5 else -1.0
            if lp:
                y1 += a * (w - y1)
                y2 += a * (y1 - y2)
                w = y2
            e = v * x / att if x < att else v * math.exp(ratio_log * (x - att) / (d - att))
            buf[s0 + i] += w * e

    def noise(self, t, d, v=0.25, hp=800):
        s0 = int(t * SR)
        n = min(int(d * SR), self.n - s0)
        if n <= 0:
            return
        rc = 1 / (2 * math.pi * hp)
        a = rc / (rc + 1 / SR)
        px = py = 0.0
        buf = self.b
        rnd = random.random
        for i in range(n):
            x = (rnd() * 2 - 1) * (1 - i / n) ** 2
            y = a * (py + x - px)
            px, py = x, y
            buf[s0 + i] += y * v

    def save(self, path):
        pcm = array.array("h")
        for s in self.b:
            pcm.append(int(max(-1.0, min(1.0, math.tanh(s * 1.5))) * 32767 * 0.9))
        if sys.byteorder == "big":
            pcm.byteswap()
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm.tobytes())


def _pick(m, t=0.0):
    m.tone(523.25, t, 0.22, "triangle", 0.28, 392)
    m.tone(659.25, t + 0.05, 0.26, "sine", 0.2)


def build_effect(name):
    if name == "tick":
        m = Mix(0.12)
        m.tone(1200, 0, 0.08, "triangle", 0.22)
    elif name == "start":
        m = Mix(2.6)
        for i, f in enumerate([130.81, 164.81, 196]):
            m.tone(f, i * 0.14, 2.4, "sawtooth", 0.12, lp=900)
        for i, f in enumerate([392, 523.25, 659.25, 783.99]):
            m.tone(f, 0.6 + i * 0.14, 1.2, "triangle", 0.28)
        m.noise(0.6, 0.5, 0.12, 2000)
    elif name == "joker":
        m = Mix(0.35)
        _pick(m)
    elif name == "kilit":  # şık kilitlenir + kalp atışı
        m = Mix(1.7)
        _pick(m)
        for i in range(3):
            m.tone(60, i * 0.5, 0.32, "sine", 0.85, 42, lp=220)
            m.noise(i * 0.5, 0.08, 0.2, 1200)
    elif name == "ok":
        m = Mix(1.2)
        for i, f in enumerate([523.25, 659.25, 783.99, 1046.5]):
            m.tone(f, i * 0.09, 0.8, "triangle", 0.32)
            m.tone(f * 2, i * 0.09, 0.5, "sine", 0.12)
        m.noise(0.02, 0.2, 0.14, 3000)
    elif name == "no":
        m = Mix(1.2)
        m.tone(196, 0, 0.55, "sawtooth", 0.30, 146, lp=900)
        m.tone(174.61, 0.06, 0.8, "sawtooth", 0.26, 130, lp=800)
        m.tone(49, 0.1, 1.0, "sine", 0.75, 40)
        m.noise(0.1, 0.25, 0.18, 600)
    elif name == "win":
        m = Mix(3.4)
        seq = [392, 392, 392, 523.25, 659.25, 523.25, 659.25, 783.99]
        for i, f in enumerate(seq):
            m.tone(f, i * 0.18, 0.7, "square", 0.14)
            m.tone(f / 2, i * 0.18, 0.7, "triangle", 0.32)
        m.tone(1046.5, 1.5, 1.8, "triangle", 0.35)
        m.noise(1.5, 1.4, 0.12, 4000)
    elif name == "next":
        m = Mix(0.35)
        m.tone(784, 0, 0.12, "triangle", 0.22)
        m.tone(1174.7, 0.08, 0.22, "triangle", 0.2)
        m.noise(0, 0.12, 0.08, 3000)
    elif name == "kalp":  # online: iki kalp atışı
        m = Mix(1.1)
        for i in range(2):
            m.tone(60, i * 0.5, 0.32, "sine", 0.85, 42, lp=220)
            m.noise(i * 0.5, 0.08, 0.2, 1200)
    elif name == "bekle":
        m = Mix(1.2)
        for t, f in ((0, 659.25), (0.22, 987.77)):
            m.tone(f, t, 0.55, "sine", 0.26)
            m.tone(f * 2, t, 0.55, "sine", 0.06)
    elif name == "bulundu":
        m = Mix(1.1)
        for i, f in enumerate([523.25, 659.25, 783.99, 1046.5]):
            m.tone(f, i * 0.08, 0.55, "triangle", 0.3)
    elif name == "ayril":
        m = Mix(0.9)
        m.tone(329.63, 0, 0.4, "sawtooth", 0.22, 196, lp=800)
        m.tone(261.63, 0.15, 0.55, "triangle", 0.18, 164.81)
    elif name == "mesaj_gonder":
        m = Mix(0.3)
        m.tone(880, 0, 0.12, "triangle", 0.22)
        m.tone(1318.5, 0.07, 0.18, "sine", 0.16)
    elif name == "mesaj_al":
        m = Mix(0.4)
        m.tone(659.25, 0, 0.12, "sine", 0.22)
        m.tone(987.77, 0.09, 0.2, "triangle", 0.18)
    elif name == "altin":
        m = Mix(0.9)
        for i, f in enumerate([659.25, 783.99, 987.77]):
            m.tone(f, i * 0.1, 0.55, "triangle", 0.3)
        m.noise(0.1, 0.35, 0.14, 3000)
    else:
        raise ValueError(name)
    return m


EFFECT_NAMES = ["tick", "start", "joker", "kilit", "ok", "no", "win", "next",
                "kalp", "bekle", "bulundu", "ayril", "mesaj_gonder", "mesaj_al", "altin"]


class Sounds:
    def __init__(self):
        self.dir = os.path.join(data_dir(), "sesler")
        self.enabled = True
        self._wx_sound = None

    def path(self, name):
        return os.path.join(self.dir, name + ".wav")

    def ensure(self):
        """Eksik sesleri üretir. Arka plan iş parçacığından çağrılabilir."""
        os.makedirs(self.dir, exist_ok=True)
        ver_file = os.path.join(self.dir, "surum.txt")
        try:
            with open(ver_file, "r", encoding="utf-8") as f:
                ok_ver = f.read().strip() == SOUND_VERSION
        except OSError:
            ok_ver = False
        for name in EFFECT_NAMES:
            if ok_ver and os.path.exists(self.path(name)):
                continue
            build_effect(name).save(self.path(name))
        with open(ver_file, "w", encoding="utf-8") as f:
            f.write(SOUND_VERSION)

    def play(self, name):
        if not self.enabled:
            return
        p = self.path(name)
        if not os.path.exists(p):
            return
        try:
            if winsound:
                winsound.PlaySound(p, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                import wx.adv
                self._wx_sound = wx.adv.Sound(p)
                if self._wx_sound.IsOk():
                    self._wx_sound.Play(wx.adv.SOUND_ASYNC)
        except Exception:
            pass

    def stop(self):
        try:
            if winsound:
                winsound.PlaySound(None, winsound.SND_PURGE)
            elif self._wx_sound:
                self._wx_sound.Stop()
        except Exception:
            pass


# =====================================================================
#  EKRAN OKUYUCU KONUŞMASI
# =====================================================================
class Speaker:
    """accessible_output2 (NVDA, JAWS, vb.) -> SAPI -> sessiz."""

    def __init__(self):
        self.enabled = True
        self.out = None
        self.sapi = None
        self.kind = "yok"
        try:
            from accessible_output2.outputs.auto import Auto
            self.out = Auto()
            self.kind = "ekran okuyucu"
        except Exception:
            self.out = None
        if self.out is None:
            try:
                import win32com.client
                self.sapi = win32com.client.Dispatch("SAPI.SpVoice")
                self.kind = "SAPI"
            except Exception:
                self.sapi = None

    @property
    def available(self):
        return self.out is not None or self.sapi is not None

    def speak(self, text, interrupt=True, force=False):
        if not text or not (self.enabled or force):
            return
        try:
            if self.out is not None:
                self.out.speak(text, interrupt=interrupt)
            elif self.sapi is not None:
                # 1 = eşzamansız, 2 = öncekini iptal et
                self.sapi.Speak(text, 1 | (2 if interrupt else 0))
        except Exception:
            pass


# =====================================================================
#  SORU HAVUZU
# =====================================================================
def clean_questions(data):
    lst = data.get("questions") if isinstance(data, dict) else data
    out = []
    for q in lst or []:
        try:
            opts = [str(o).strip() for o in q["options"]]
            ans = int(q["answer"])
            text = str(q["question"]).strip()
            if len(opts) == 4 and 0 <= ans < 4 and text and all(opts):
                out.append({
                    "cat": str(q.get("category", "")).strip(),
                    "q": text,
                    "opts": opts,
                    "ans": ans,
                    "exp": str(q.get("explanation", "")).strip(),
                })
        except Exception:
            continue
    return out


def _parse_raw(raw):
    data = json.loads(raw.decode("utf-8-sig"))
    pool = clean_questions(data)
    if len(pool) < 10:
        raise ValueError("En az 10 geçerli soru gerekli.")
    ver = data.get("version", "") if isinstance(data, dict) else ""
    return pool, ver


def fetch_online():
    url = "%s?t=%d" % (QUESTIONS_URL, int(time.time()))
    req = urllib.request.Request(url, headers={
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "User-Agent": "BilgiYarismasi-wx/1.0",
    })
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = r.read()
    pool, ver = _parse_raw(raw)
    try:  # sonraki çevrimdışı açılışlar için sakla
        with open(os.path.join(data_dir(), "questions_cache.json"), "wb") as f:
            f.write(raw)
    except OSError:
        pass
    return pool, ver


def load_questions():
    """(havuz, kaynak, sürüm) döndürür. kaynak: 'internet' | 'kayıtlı' | 'yerel'."""
    try:
        pool, ver = fetch_online()
        return {"pool": pool, "source": "internet", "version": ver}
    except Exception:
        pass
    candidates = [
        ("kayıtlı", os.path.join(data_dir(), "questions_cache.json")),
        ("yerel", os.path.join(base_dir(), "questions.json")),
    ]
    for source, path in candidates:
        try:
            with open(path, "rb") as f:
                pool, ver = _parse_raw(f.read())
            return {"pool": pool, "source": source, "version": ver}
        except Exception:
            continue
    raise RuntimeError("Sorular indirilemedi ve kayıtlı kopya bulunamadı.")


class Game:
    def __init__(self, pool, limit):
        picks = random.sample(pool, min(ROUND_COUNT, len(pool)))
        self.qs = []
        for q in picks:
            opts = [{"t": t, "c": i == q["ans"], "gone": False} for i, t in enumerate(q["opts"])]
            random.shuffle(opts)
            self.qs.append({"cat": q["cat"], "q": q["q"], "o": opts, "e": q["exp"]})
        self.n = len(self.qs)
        self.i = 0
        self.joker = True
        self.lock = False
        self.limit = limit
        self.deadline = 0.0
        self.warn10 = False
        self.last_tick = -1
        self.timing = False  # süre işliyor mu


# =====================================================================
#  AYARLAR
# =====================================================================
class Config:
    def __init__(self):
        self.path = os.path.join(data_dir(), "ayarlar.json")
        self.d = {"sure": 0, "ses": True, "konusma": True, "ad": "", "osure": 20}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.d.update(json.load(f))
        except Exception:
            pass
        if self.d.get("sure") not in TIME_CHOICES:
            self.d["sure"] = 0

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.d, f)
        except OSError:
            pass


HELP_TEXT = (
    "Nasıl oynanır\n"
    "10 soruluk bir yarışma. Her soruda dört şık var. Bir soruyu yanlış bilirsen oyun biter; "
    "hepsini bilirsen kazanırsın. Süreli oynamayı seçersen süre dolunca soru yanlış sayılır. "
    "Her oyunda bir kez Yarı yarıya jokeri kullanabilirsin: iki yanlış şık elenir.\n\n"
    "Oyun sırasındaki kısayollar\n"
    "1, 2, 3, 4: ilgili şıkkı seçer.\n"
    "C: soruyu ve şıkları ekran okuyucuya yeniden okutur.\n"
    "T: kalan süreyi söyler.\n"
    "P: puan durumunu söyler.\n"
    "J: Yarı yarıya jokerini kullanır.\n"
    "Yön tuşları: şıklar arasında gezer.\n"
    "Esc: oyundan çıkış için onay ister.\n\n"
    "Genel kısayollar\n"
    "Ctrl+M: sesleri açar ya da kapatır.\n"
    "Ctrl+K: ekran okuyucu konuşmasını açar ya da kapatır.\n"
    "F1: bu yardım ekranı.\n"
    "Ctrl+Q: programdan çıkar.\n\n"
    "Online düello\n"
    "Ana menüden Online Oyna'yı seç. Rastgele rakip bulabilir ya da özel oda kurup 6 haneli kodu arkadaşına verebilirsin. "
    "Odayı kuran kişi süreyi seçer. 10 soru sorulur, doğruyu hızlı bilen daha çok puan alır; skor eşitse eşitlik bozulana kadar altın soru gelir. "
    "Düello sırasında S: sohbet mesajı yazar, H: son mesajları okur. Web sitesindeki oyuncularla ve diğer masaüstü oyuncularla eşleşebilirsin. Sesli konuşma (mikrofon) yalnızca sitedeki oyuncular arasında vardır.\n\n"
    "Sorular her oyun başında internetten yenilenir. İnternet yoksa son kaydedilen sorular kullanılır."
)


# =====================================================================
#  ARAYÜZ
# =====================================================================
ID_GAME_TIMER = wx.NewIdRef()
ID_WAIT_TIMER = wx.NewIdRef()


class MainFrame(OnlineMixin, wx.Frame):
    def __init__(self):
        super().__init__(None, title=APP_TITLE, size=(1000, 760))
        self.cfg = Config()
        self.speaker = Speaker()
        self.speaker.enabled = bool(self.cfg.d["konusma"])
        self.sounds = Sounds()
        self.sounds.enabled = bool(self.cfg.d["ses"])
        self.pool = []
        self.source = ""
        self.game = None
        self.screen = "wait"
        self.closing = False
        self._calls = []
        self.opt_btns = []
        self.opt_labels = []
        self.joker_btn = None
        self.q_ctrl = None
        self.fb_col = None
        self.timer_lbl = None
        self.gauge = None
        self.wait_gauge = None
        self.paused_at = None
        self.o_note_tc = None
        self.load_questions_fn = load_questions
        self.online_init()
        ol.LOG_PATH = os.path.join(data_dir(), "online_log.txt")

        self.panel = wx.Panel(self)
        self.game_timer = wx.Timer(self, ID_GAME_TIMER)
        self.wait_timer = wx.Timer(self, ID_WAIT_TIMER)
        self.Bind(wx.EVT_TIMER, self.on_game_timer, id=ID_GAME_TIMER)
        self.Bind(wx.EVT_TIMER, self.on_wait_timer, id=ID_WAIT_TIMER)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self._build_menu()
        self.Centre()

        self.show_wait()
        self.run_bg(self._startup_job, self._startup_done)

    # ------------------------------------------------------------ menü
    def _build_menu(self):
        mb = wx.MenuBar()
        m = wx.Menu()
        self.mi_sound = m.AppendCheckItem(wx.ID_ANY, "Sesler\tCtrl+M")
        self.mi_sound.Check(self.sounds.enabled)
        self.mi_speech = m.AppendCheckItem(wx.ID_ANY, "Ekran okuyucu konuşması\tCtrl+K")
        self.mi_speech.Check(self.speaker.enabled)
        m.AppendSeparator()
        mi_quit = m.Append(wx.ID_EXIT, "Çıkış\tCtrl+Q")
        mb.Append(m, "&Oyun")
        h = wx.Menu()
        mi_help = h.Append(wx.ID_HELP, "Nasıl oynanır ve kısayollar\tF1")
        mb.Append(h, "&Yardım")
        self.SetMenuBar(mb)
        self.Bind(wx.EVT_MENU, self.on_toggle_sound, self.mi_sound)
        self.Bind(wx.EVT_MENU, self.on_toggle_speech, self.mi_speech)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(), mi_quit)
        self.Bind(wx.EVT_MENU, lambda e: self.open_help(), mi_help)

    def on_toggle_sound(self, _e):
        self.sounds.enabled = self.mi_sound.IsChecked()
        self.cfg.d["ses"] = self.sounds.enabled
        self.cfg.save()
        if not self.sounds.enabled:
            self.sounds.stop()
        self.say("Sesler açık." if self.sounds.enabled else "Sesler kapalı.", force=True)

    def on_toggle_speech(self, _e):
        on = self.mi_speech.IsChecked()
        self.cfg.d["konusma"] = on
        self.cfg.save()
        if on:
            self.speaker.enabled = True
            self.say("Ekran okuyucu konuşması açık.")
        else:
            self.say("Ekran okuyucu konuşması kapalı.", force=True)
            self.speaker.enabled = False

    # ------------------------------------------------------------ yardımcılar
    def say(self, text, interrupt=True, force=False):
        self.speaker.speak(text, interrupt=interrupt, force=force)

    def later(self, ms, fn, *args):
        c = wx.CallLater(ms, fn, *args)
        self._calls.append(c)
        return c

    def cancel_later(self):
        for c in self._calls:
            try:
                c.Stop()
            except Exception:
                pass
        self._calls = []

    def go(self, fn, *args):
        """Düğme işleyicisinden ekran değiştirirken güvenli geçiş."""
        wx.CallAfter(fn, *args)

    def run_bg(self, work, done):
        def runner():
            try:
                res, err = work(), None
            except Exception as e:  # noqa
                res, err = None, e
            wx.CallAfter(self._bg_done, done, res, err)
        threading.Thread(target=runner, daemon=True).start()

    def _bg_done(self, done, res, err):
        if not self.closing:
            done(res, err)

    def font(self, size=14, bold=False):
        return wx.Font(wx.FontInfo(size).Bold(bold))

    def new_screen(self, title):
        self.stop_game_timer()
        self.wait_timer.Stop()
        self.cancel_later()
        self.panel.DestroyChildren()
        self.opt_btns, self.opt_labels = [], []
        self.joker_btn = self.q_ctrl = self.fb_col = None
        self.timer_lbl = self.gauge = self.wait_gauge = None
        self.o_note_tc = self.o_status_tc = self.o_players = self.o_wait_tc = None
        self.o_count = self.o_timer_lbl = self.o_gauge = self.o_rm_tc = self.o_rm_btn = None
        outer = wx.BoxSizer(wx.HORIZONTAL)
        outer.AddStretchSpacer(1)
        self.col = wx.BoxSizer(wx.VERTICAL)
        outer.Add(self.col, 5, wx.EXPAND | wx.ALL, 20)
        outer.AddStretchSpacer(1)
        self.panel.SetSizer(outer)
        self.SetTitle("%s — %s" % (APP_TITLE, title))

    def add_heading(self, text):
        st = wx.StaticText(self.panel, label=text)
        st.SetFont(self.font(26, True))
        self.col.Add(st, 0, wx.BOTTOM, 10)
        return st

    def add_text(self, text, size=14):
        st = wx.StaticText(self.panel, label=text)
        st.SetFont(self.font(size))
        st.Wrap(760)
        self.col.Add(st, 0, wx.BOTTOM, 10)
        return st

    def add_readonly(self, label, text, height=120, size=16, bold=False):
        lab = wx.StaticText(self.panel, label=label)  # ekran okuyucu için etiket
        lab.SetFont(self.font(11))
        self.col.Add(lab, 0, wx.TOP, 6)
        tc = wx.TextCtrl(self.panel, value=text,
                         style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP)
        tc.SetFont(self.font(size, bold))
        tc.SetMinSize((-1, height))
        tc.SetName(label)
        self.col.Add(tc, 0, wx.EXPAND | wx.BOTTOM, 8)
        return tc

    def add_button(self, label, handler, primary=False, parent=None, sizer=None):
        b = wx.Button(parent or self.panel, label=label)
        b.SetFont(self.font(15, primary))
        b.SetMinSize((-1, 48))
        b.Bind(wx.EVT_BUTTON, handler)
        (sizer or self.col).Add(b, 0, wx.EXPAND | wx.BOTTOM, 8)
        if primary:
            b.SetDefault()
        return b

    def finish_layout(self):
        self.panel.Layout()
        self.Layout()

    # ------------------------------------------------------------ bekleme ekranı
    def show_wait(self, message=WAIT_MESSAGE):
        self.screen = "wait"
        self.new_screen("Bekleyin")
        self.add_heading(APP_TITLE)
        tc = self.add_readonly("Durum", message, height=70, size=18)
        self.wait_gauge = wx.Gauge(self.panel, range=100, style=wx.GA_HORIZONTAL)
        self.col.Add(self.wait_gauge, 0, wx.EXPAND | wx.TOP, 10)
        self.finish_layout()
        self.wait_timer.Start(80)
        tc.SetFocus()
        self.say(message)

    def on_wait_timer(self, _e):
        if self.wait_gauge:
            try:
                self.wait_gauge.Pulse()
            except RuntimeError:
                pass

    def _startup_job(self):
        self.sounds.ensure()
        try:
            return load_questions()
        except Exception as e:  # noqa
            return e

    def _startup_done(self, res, _err):
        if isinstance(res, Exception) or res is None:
            self.pool = []
            self.show_home(note="Sorular yüklenemedi. İnternet bağlantını kontrol edip tekrar dene.")
            return
        self.pool, self.source = res["pool"], res["source"]
        self.show_home()

    # ------------------------------------------------------------ ana menü
    def source_note(self):
        if not self.pool:
            return "Soru havuzu boş."
        names = {"internet": "internetten güncellendi",
                 "kayıtlı": "internet yok, kayıtlı sorular kullanılıyor",
                 "yerel": "internet yok, bilgisayardaki questions.json kullanılıyor"}
        return "Soru havuzu: %d soru, %s." % (len(self.pool), names.get(self.source, ""))

    def show_home(self, note=None):
        self.online_close()
        self.game = None
        self.screen = "home"
        self.new_screen("Ana menü")
        self.add_heading(APP_TITLE)
        info = note or self.source_note()
        self.add_text("Tek başına 10 soru çöz ya da online bir rakiple düello yap.", 15)
        self.add_text(info, 12)
        b = self.add_button("Tek Başına Oyna", lambda e: self.go(self.show_setup), primary=True)
        self.add_button("Online Oyna (rakiple düello)", lambda e: self.go(self.show_online_name))
        self.add_button("Nasıl oynanır ve kısayollar", lambda e: self.go(self.open_help))
        self.add_button("Hatalı soru bildir / İletişim (tarayıcıda açılır)",
                        lambda e: webbrowser.open(CONTACT_URL))
        self.add_button("Çıkış", lambda e: self.Close())
        self.finish_layout()
        b.SetFocus()
        speech = "%s. Ana menü. %s" % (APP_TITLE, info)
        if not self.speaker.available:
            speech = ""
        self.say(speech)

    # ------------------------------------------------------------ yardım
    def open_help(self):
        if self.screen == "game":
            return
        self.show_help()

    def show_help(self):
        self.screen = "help"
        self.new_screen("Yardım")
        self.add_heading("Nasıl oynanır")
        tc = self.add_readonly("Yardım metni", HELP_TEXT, height=420, size=14)
        b = self.add_button("Geri", lambda e: self.go(self.show_home), primary=True)
        self.finish_layout()
        tc.SetFocus()
        self.say("Yardım ekranı. Metni okumak için ok tuşlarını kullan. Geri dönmek için Esc tuşuna bas.")

    # ------------------------------------------------------------ ayar ekranı
    def show_setup(self):
        self.screen = "setup"
        self.new_screen("Oyun ayarı")
        self.add_heading("Tek Başına")
        choices = ["Süresiz" if v == 0 else "%d saniye" % v for v in TIME_CHOICES]
        self.radio = wx.RadioBox(self.panel, label="Süreli oynamak ister misin?",
                                 choices=choices, majorDimension=3, style=wx.RA_SPECIFY_COLS)
        self.radio.SetFont(self.font(14))
        self.radio.SetSelection(TIME_CHOICES.index(self.cfg.d["sure"]))
        self.col.Add(self.radio, 0, wx.EXPAND | wx.BOTTOM, 10)
        self.add_text("Her soru için süre verilir. Süre dolunca soru yanlış sayılır.", 12)
        self.add_button("Başla", lambda e: self.go(self.start_game), primary=True)
        self.add_button("Geri", lambda e: self.go(self.show_home))
        self.finish_layout()
        self.radio.SetFocus()
        self.say("Oyun ayarı. Süreli oynamak ister misin? Ok tuşlarıyla seç, Başla düğmesine bas.")

    # ------------------------------------------------------------ oyun başlat
    def start_game(self):
        sel = self.radio.GetSelection() if getattr(self, "radio", None) else 0
        self.cfg.d["sure"] = TIME_CHOICES[max(0, sel)]
        self.cfg.save()
        self.show_wait()
        self.run_bg(load_questions, self._questions_for_game)

    def _questions_for_game(self, res, err):
        if err or not res:
            if len(self.pool) >= 10:
                self.say("Sorular yenilenemedi, eldeki sorular kullanılıyor.", interrupt=False)
                self.begin_game()
            else:
                self.show_home(note="Sorular indirilemedi. İnternet bağlantını kontrol edip tekrar dene.")
            return
        self.pool, self.source = res["pool"], res["source"]
        if self.source != "internet":
            self.say("İnternete ulaşılamadı, kayıtlı sorular kullanılıyor.", interrupt=False)
        self.begin_game()

    def begin_game(self):
        self.game = g = Game(self.pool, self.cfg.d["sure"])
        self.screen = "ready"
        self.new_screen("Hazır mısın?")
        self.add_heading("Hazır mısın?")
        self.finish_layout()
        self.sounds.play("start")
        self.say("Başlıyor. Hazır mısın?")
        self.later(1900, self._first_question, g)

    def _first_question(self, g):
        if self.game is g:
            self.show_question()

    # ------------------------------------------------------------ soru ekranı
    def opt_text(self, j, suffix=""):
        q = self.game.qs[self.game.i]
        return "%s: %s%s" % (LETTERS[j], q["o"][j]["t"], suffix)

    def question_speech(self, with_time=False):
        g = self.game
        q = g.qs[g.i]
        opts = ", ".join("%s: %s" % (LETTERS[k], o["t"]) for k, o in enumerate(q["o"]) if not o["gone"])
        s = "Soru %d / %d. Kategori: %s. %s Seçenekler: %s." % (g.i + 1, g.n, q["cat"], q["q"], opts)
        if with_time:
            s += " " + self.time_text()
        return s

    def time_text(self):
        g = self.game
        if not g:
            return ""
        if not g.limit:
            return "Süre sınırı kapalı."
        if g.timing:
            return "Kalan süre: %d saniye." % self.remaining()
        return "Bu soru için süre durdu."

    def remaining(self):
        g = self.game
        return max(0, int(math.ceil(g.deadline - time.monotonic()))) if g and g.deadline else 0

    def show_question(self):
        g = self.game
        if not g:
            return
        q = g.qs[g.i]
        g.lock = False
        self.screen = "game"
        self.new_screen("Soru %d / %d" % (g.i + 1, g.n))
        if g.i > 0:
            self.sounds.play("next")
        head = self.add_text("Soru %d / %d — %s" % (g.i + 1, g.n, q["cat"]), 14)
        head.SetFont(self.font(14, True))
        if g.limit:
            self.timer_lbl = wx.StaticText(self.panel, label="Kalan süre: %d saniye" % g.limit)
            self.timer_lbl.SetFont(self.font(13))
            self.col.Add(self.timer_lbl, 0, wx.BOTTOM, 4)
            self.gauge = wx.Gauge(self.panel, range=1000, style=wx.GA_HORIZONTAL)
            self.gauge.SetValue(1000)
            self.col.Add(self.gauge, 0, wx.EXPAND | wx.BOTTOM, 8)
        qtext = "%s\n%s" % (q["cat"], q["q"])
        if not self.speaker.available:
            # Konuşma yoksa ekran okuyucu odak değişince tüm metni okusun
            qtext = self.question_speech()
        self.q_ctrl = self.add_readonly("Soru", qtext, height=110, size=18, bold=True)
        grp = wx.BoxSizer(wx.VERTICAL)
        for k in range(4):
            b = wx.Button(self.panel, label=self.opt_text(k))
            b.SetFont(self.font(15))
            b.SetMinSize((-1, 50))
            b.SetWindowStyleFlag(wx.BU_LEFT)
            b.Bind(wx.EVT_BUTTON, lambda e, kk=k: self.pick(kk))
            grp.Add(b, 0, wx.EXPAND | wx.BOTTOM, 6)
            self.opt_btns.append(b)
        self.col.Add(grp, 0, wx.EXPAND)
        self.joker_btn = wx.Button(self.panel, label="Yarı yarıya (J)" if g.joker else "Yarı yarıya (kullanıldı)")
        self.joker_btn.SetFont(self.font(13))
        self.joker_btn.Enable(g.joker)
        self.joker_btn.Bind(wx.EVT_BUTTON, lambda e: self.use_joker())
        self.col.Add(self.joker_btn, 0, wx.EXPAND | wx.TOP, 6)
        self.fb_col = wx.BoxSizer(wx.VERTICAL)
        self.col.Add(self.fb_col, 0, wx.EXPAND | wx.TOP, 8)
        self.finish_layout()

        self.q_ctrl.SetFocus()
        speech = self.question_speech(with_time=bool(g.limit))
        if g.i == 0:
            speech += " Şık seçmek için 1 ile 4 arası tuşlara bas. C soruyu tekrar okur."
        self.later(250, self._speak_if_current, g, g.i, speech)
        self.start_game_timer()

    def _speak_if_current(self, g, idx, text):
        if self.game is g and g.i == idx:
            self.say(text)

    # ------------------------------------------------------------ süre
    def start_game_timer(self):
        g = self.game
        if not g or not g.limit:
            return
        g.deadline = time.monotonic() + g.limit
        g.warn10 = False
        g.last_tick = -1
        g.timing = True
        self.game_timer.Start(200)

    def stop_game_timer(self):
        self.game_timer.Stop()
        if self.game:
            self.game.timing = False

    def on_game_timer(self, _e):
        if self.screen == "ogame":
            self.on_online_timer()
            return
        g = self.game
        if not g or not g.timing or g.lock or self.screen != "game":
            return
        left = max(0.0, g.deadline - time.monotonic())
        sec = int(math.ceil(left))
        if self.timer_lbl:
            self.timer_lbl.SetLabel("Kalan süre: %d saniye" % sec)
        if self.gauge:
            self.gauge.SetValue(int(left / g.limit * 1000))
        if 0 < sec <= 5 and sec != g.last_tick:
            g.last_tick = sec
            self.sounds.play("tick")
        if sec == 10 and not g.warn10 and g.limit > 10:
            g.warn10 = True
            self.say("10 saniye kaldı.", interrupt=False)
        if left <= 0:
            self.timeout()

    def timeout(self):
        g = self.game
        if not g or g.lock:
            return
        g.lock = True
        self.stop_game_timer()
        self.lock_ui()
        self.reveal(g, -1)

    def lock_ui(self):
        if self.joker_btn:
            self.joker_btn.Enable(False)

    # ------------------------------------------------------------ seçim
    def pick(self, k):
        g = self.game
        if not g or g.lock or self.screen != "game":
            return
        q = g.qs[g.i]
        if q["o"][k]["gone"]:
            self.say("Bu şık elendi.")
            return
        g.lock = True
        self.stop_game_timer()
        self.lock_ui()
        self.opt_btns[k].SetLabel(self.opt_text(k, " (seçildi)"))
        self.sounds.play("kilit")
        self.say("%s şıkkı kilitlendi: %s. Sonuç bekleniyor." % (LETTERS[k], q["o"][k]["t"]))
        self.later(2200, self.reveal, g, k)

    def use_joker(self):
        g = self.game
        if not g or not g.joker or g.lock or self.screen != "game":
            return
        g.joker = False
        self.sounds.play("joker")
        q = g.qs[g.i]
        wrong = [k for k, o in enumerate(q["o"]) if not o["c"] and not o["gone"]]
        for k in random.sample(wrong, min(2, len(wrong))):
            q["o"][k]["gone"] = True
            self.opt_btns[k].SetLabel(self.opt_text(k, " (elendi)"))
        self.joker_btn.Enable(False)
        self.joker_btn.SetLabel("Yarı yarıya (kullanıldı)")
        left = [k for k, o in enumerate(q["o"]) if not o["gone"]]
        self.say("Joker kullanıldı. İki yanlış şık elendi. Kalan şıklar: %s." %
                 ", ".join("%s: %s" % (LETTERS[k], q["o"][k]["t"]) for k in left))
        self.opt_btns[left[0]].SetFocus()

    # ------------------------------------------------------------ sonuç
    def reveal(self, g, k):
        if self.game is not g or self.screen != "game":
            return
        self.stop_game_timer()
        g.lock = True
        q = g.qs[g.i]
        right = next(j for j, o in enumerate(q["o"]) if o["c"])
        good = (k == right)
        for j, b in enumerate(self.opt_btns):
            if j == right:
                b.SetLabel(self.opt_text(j, " (doğru cevap)"))
            elif j == k:
                b.SetLabel(self.opt_text(j, " (yanlış seçimin)"))
        self.sounds.play("ok" if good else "no")
        if k < 0:
            msg = "Süre doldu. Doğru cevap %s: %s." % (LETTERS[right], q["o"][right]["t"])
        elif good:
            msg = "Doğru cevap!"
        else:
            msg = "Yanlış. Doğru cevap %s: %s." % (LETTERS[right], q["o"][right]["t"])
        full = ("%s %s" % (msg, q["e"])).strip()
        last = g.i == g.n - 1
        label = ("Sonucu gör" if last else "Sonraki soru") if good else "Sonucu gör"

        lab = wx.StaticText(self.panel, label="Sonuç")
        lab.SetFont(self.font(11))
        self.fb_col.Add(lab, 0)
        tc = wx.TextCtrl(self.panel, value=full,
                         style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP)
        tc.SetFont(self.font(15))
        tc.SetMinSize((-1, 90))
        tc.SetName("Sonuç")
        self.fb_col.Add(tc, 0, wx.EXPAND | wx.BOTTOM, 6)
        nb = wx.Button(self.panel, label=label)
        nb.SetFont(self.font(15, True))
        nb.SetMinSize((-1, 48))
        nb.SetDefault()
        nb.Bind(wx.EVT_BUTTON, lambda e: self.go(self.after_reveal, g, good, last))
        self.fb_col.Add(nb, 0, wx.EXPAND)
        self.finish_layout()
        tc.SetFocus()
        self.say(full)

    def after_reveal(self, g, good, last):
        if self.game is not g:
            return
        if good and not last:
            g.i += 1
            self.show_question()
        else:
            self.end_game(g.n if good else g.i)

    def end_game(self, n):
        g = self.game
        total = g.n if g else ROUND_COUNT
        self.screen = "result"
        self.new_screen("Sonuç")
        perfect = n == total
        title = ("Hepsini bildin!" if perfect else "Çok iyi!" if n >= 7
                 else "Fena değil." if n >= 4 else "Bir daha dene.")
        self.add_heading(title)
        tc = self.add_readonly("Skor", "%d / %d doğru" % (n, total), height=70, size=24, bold=True)
        b = self.add_button("Tekrar oyna", lambda e: self.go(self.show_setup), primary=True)
        self.add_button("Ana menü", lambda e: self.go(self.show_home))
        self.add_button("Hatalı soru bildir / İletişim (tarayıcıda açılır)",
                        lambda e: webbrowser.open(CONTACT_URL))
        self.finish_layout()
        if perfect:
            self.sounds.play("win")
        tc.SetFocus()
        self.say("%s %d sorudan %d doğru." % (title, total, n))

    # ------------------------------------------------------------ klavye
    def on_char_hook(self, e):
        code = e.GetKeyCode()
        if e.ControlDown() or e.AltDown() or e.MetaDown():
            e.Skip()
            return
        scr = self.screen
        if code == wx.WXK_ESCAPE:
            if scr == "game":
                self.confirm_exit_game()
            elif scr == "ogame":
                self.confirm_leave_online()
            elif scr in ("setup", "help", "oname"):
                self.go(self.show_home)
            elif scr in ("omenu", "owait", "odisc"):
                self.go(self.show_online_menu if scr != "omenu" else self.show_home)
            elif scr == "ojoin":
                self.go(self.show_online_menu)
            else:
                e.Skip()
            return
        focus = wx.Window.FindFocus()
        if isinstance(focus, wx.TextCtrl) and focus.IsEditable():
            e.Skip()
            return
        ch = chr(code).upper() if 32 <= code < 127 else ""
        if scr == "game" and self.game:
            digit = None
            if ord("1") <= code <= ord("4"):
                digit = code - ord("1")
            elif wx.WXK_NUMPAD1 <= code <= wx.WXK_NUMPAD4:
                digit = code - wx.WXK_NUMPAD1
            if digit is not None:
                self.pick(digit)
                return
            if ch == "C":
                self.read_question()
                return
            if ch == "T":
                self.say(self.time_text())
                return
            if ch == "P":
                g = self.game
                self.say("Soru %d / %d. Şu ana kadar %d doğru. Yarı yarıya jokeri %s." %
                         (g.i + 1, g.n, g.i, "duruyor" if g.joker else "kullanıldı"))
                return
            if ch == "J":
                self.use_joker()
                return
        elif scr in ONLINE_SCREENS_KEYS:
            if self.online_key(code, ch):
                return
        if scr in ("game", "ogame") and self.opt_btns and code in (
                wx.WXK_UP, wx.WXK_DOWN, wx.WXK_LEFT, wx.WXK_RIGHT, wx.WXK_HOME, wx.WXK_END):
            if self.move_option_focus(code):
                return
        e.Skip()

    def gone_flags(self):
        if self.screen == "game" and self.game:
            q = self.game.qs[self.game.i]
            return [o["gone"] for o in q["o"]]
        return [False] * len(self.opt_btns)

    def move_option_focus(self, code):
        focus = wx.Window.FindFocus()
        if focus not in self.opt_btns:
            return False
        gone = self.gone_flags()
        usable = [b for j, b in enumerate(self.opt_btns) if not gone[j]]
        if not usable:
            return False
        if code == wx.WXK_HOME:
            usable[0].SetFocus()
        elif code == wx.WXK_END:
            usable[-1].SetFocus()
        else:
            step = 1 if code in (wx.WXK_DOWN, wx.WXK_RIGHT) else -1
            i = usable.index(focus) if focus in usable else 0
            usable[(i + step) % len(usable)].SetFocus()
        return True

    def read_question(self):
        if self.q_ctrl:
            self.q_ctrl.SetFocus()
        self.say(self.question_speech(with_time=bool(self.game.limit and self.game.timing)))

    def confirm_exit_game(self):
        g = self.game
        paused = g.timing
        if paused:
            self.paused_at = time.monotonic()
            self.game_timer.Stop()
        dlg = wx.MessageDialog(self, "Oyundan çıkıp ana menüye dönmek istiyor musun?",
                               "Oyundan çık", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
        dlg.SetYesNoLabels("Evet, çık", "Hayır, devam et")
        self.say("Oyundan çıkılsın mı? Evet ya da hayır.")
        res = dlg.ShowModal()
        dlg.Destroy()
        if self.game is not g or self.screen != "game":
            return
        if res == wx.ID_YES:
            self.go(self.show_home)
            return
        if paused and g.timing and not g.lock:
            g.deadline += time.monotonic() - self.paused_at
            self.game_timer.Start(200)
        if self.q_ctrl:
            self.q_ctrl.SetFocus()
        self.say("Oyuna devam ediliyor.")

    # ------------------------------------------------------------ kapanış
    def on_close(self, e):
        self.closing = True
        self.online_close()
        self.game_timer.Stop()
        self.wait_timer.Stop()
        self.cancel_later()
        self.sounds.stop()
        self.Destroy()


def main():
    app = wx.App(False)
    frame = MainFrame()
    frame.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()
