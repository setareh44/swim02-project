# -*- coding: utf-8 -*-
"""Motivational AI engine (Qt-free).

On every successful athlete login the engine shows (and can speak) one
high-impact quote, personalised with the swimmer's recent trend:

  * improving -> celebrate the progress with real numbers,
  * declining  -> empathy + one concrete next step,
  * stable     -> challenge to break the plateau,
  * no history -> warm welcome + first-session goal.

Every quote ships in two forms: Persian for the UI (``fa``) and plain ASCII
Finglish (``finglish``) for the terminal / speech synthesis.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Sequence, Tuple

from .history import AnalysisSummary, ProgressTracker


@dataclass(frozen=True)
class MotivationalQuote:
    fa: str
    finglish: str
    author: str = ""
    tags: Tuple[str, ...] = ()


QUOTE_BANK: List[MotivationalQuote] = [
    MotivationalQuote(
        "آب به کسی رحم نمی‌کند که بجنگد؛ به کسی جایزه می‌دهد که جاری شود.",
        "Ab be kasi rahm nemikonad ke bejangad; be kasi jayeze midahad ke jari shavad.",
        tags=("stable", "general")),
    MotivationalQuote(
        "قهرمان‌ها در استخر ساخته نمی‌شوند؛ در ذهن ساخته می‌شوند و در استخر ثابت می‌شوند.",
        "Ghahraman-ha dar estakhr sakhte nemishavand; dar zehn sakhte mishavand va dar estakhr sabet mishavand.",
        tags=("general", "race")),
    MotivationalQuote(
        "هر طولی که امروز می‌روی، فردا یک ثانیه از حریفت جلوتری.",
        "Har tooli ke emrooz miravi, farda yek saniye az harifet jelotari.",
        tags=("improving", "general")),
    MotivationalQuote(
        "پیشرفتت را دیدیم؛ SWOLF پایین‌تر یعنی شنای هوشمندتر. ادامه بده!",
        "Pishraftat ra didim; SWOLF-e payin-tar yani shenaye hooshmand-tar. Edame bede!",
        tags=("improving",)),
    MotivationalQuote(
        "نمودارت سبز است؛ بدنت دارد به تمرین جواب می‌دهد. امروز هم یک قدم.",
        "Nemudarat sabz ast; badanat darad be tamrin javab midahad. Emrooz ham yek ghadam.",
        tags=("improving",)),
    MotivationalQuote(
        "رکوردها مال کسانی است که وقتی خسته‌اند، یک طول بیشتر می‌روند.",
        "Record-ha mal-e kasani ast ke vaghti khaste-and, yek tool bishtar miravand.",
        tags=("improving", "race")),
    MotivationalQuote(
        "افت موقتی، بخشی از مسیر قهرمانی است؛ مهم برگشتن است، نه نیفتادن.",
        "Oft-e movaghati, bakhshi az masir-e ghahramani ast; mohem bargashtan ast, na niyoftadan.",
        tags=("declining",)),
    MotivationalQuote(
        "امروز روز بازسازی است: آرام شنا کن، تکنیک را تمیز کن، فردا حمله کن.",
        "Emrooz rooz-e bazsazi ast: aram shena kon, teknik ra tamiz kon, farda hamle kon.",
        tags=("declining",)),
    MotivationalQuote(
        "حتی قهرمانان المپیک هفته‌های بد دارند؛ فرقشان این است که برمی‌گردند.",
        "Hata ghahramanan-e Olympic hafte-haye bad darand; fargheshan in ast ke barmigardand.",
        tags=("declining",)),
    MotivationalQuote(
        "یک جلسه بد، تو را شناگر بدی نمی‌کند؛ جا زدن چرا.",
        "Yek jalase-ye bad, to ra shenagar-e badi nemikonad; ja zadan chera.",
        tags=("declining",)),
    MotivationalQuote(
        "پلاتو یعنی بدنت آماده جهش بعدی است؛ فقط باید محرک جدید بدهی.",
        "Plateau yani badanat amade-ye jahesh-e badi ast; faghat bayad moharrek-e jadid bedahi.",
        tags=("stable",)),
    MotivationalQuote(
        "ثبات، خودش یک پیروزی است؛ حالا وقتش است یک ریسک کوچک بکنی.",
        "Sabat, khodash yek piroozi ast; hala vaghtash ast yek risk-e koochak bokoni.",
        tags=("stable",)),
    MotivationalQuote(
        "به استخر خوش آمدی! اولین قدم قهرمانی همین امروز است: فقط شروع کن.",
        "Be estakhr khosh amadi! Avvalin ghadam-e ghahramani hamin emrooz ast: faghat shoroo kon.",
        tags=("welcome",)),
    MotivationalQuote(
        "هر تحلیلی که می‌گیری، یک نقشه گنج است؛ گنجش تکنیک بهتر توست.",
        "Har tahlili ke migiri, yek naghshe-ye ganj ast; ganjesh teknik-e behtar-e tost.",
        tags=("welcome", "general")),
    MotivationalQuote(
        "آرنج بالا، سر پایین، ذهن آرام؛ بقیه‌اش خودش می‌آید.",
        "Aranj bala, sar payin, zehn aram; baghiye-ash khodash miayad.",
        tags=("general", "stable")),
    MotivationalQuote(
        "تو با ساعت مسابقه نمی‌دهی؛ با نسخه دیروز خودت مسابقه می‌دهی.",
        "To ba saat mosabeghe nemidahi; ba noskhe-ye dirooz-e khodat mosabeghe midahi.",
        tags=("general", "improving")),
    MotivationalQuote(
        "تنفس درست، نصف شناست؛ آرام بگیر، کامل خالی کن.",
        "Tanaffos-e dorost, nesf-e shenast; aram begir, kamel khali kon.",
        tags=("general",)),
    MotivationalQuote(
        "دیوار برگشت، سکوی پرتاب است نه محل استراحت!",
        "Divar-e bargasht, sakkoo-ye partab ast na mahal-e esterahat!",
        tags=("race", "general")),
    MotivationalQuote(
        "پنجاه متر آخر را با قلبت شنا کن؛ پاهایت خودشان می‌آیند.",
        "Panjah metr-e akhar ra ba ghalbat shena kon; pahayat khodeshan miayand.",
        tags=("race",)),
    MotivationalQuote(
        "تمرین امروزت را جدی بگیر؛ حریفت الان دارد تمرین می‌کند.",
        "Tamrin-e emroozet ra jeddi begir; harifet alan darad tamrin mikonad.",
        tags=("race", "stable")),
]


class MotivationEngine:
    """Selects and personalises quotes from trends + history."""

    def __init__(self, bank: Optional[Sequence[MotivationalQuote]] = None):
        self.bank = list(bank) if bank else list(QUOTE_BANK)

    # -- selection --------------------------------------------------------
    @staticmethod
    def _day_seed(user_id: str, verdict: str) -> int:
        raw = "%s|%s|%s" % (date.today().isoformat(), user_id, verdict)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return int(digest[:8], 16)

    def _candidates(self, verdict: str) -> List[MotivationalQuote]:
        tagged = [q for q in self.bank if verdict in q.tags]
        if tagged:
            return tagged
        general = [q for q in self.bank if "general" in q.tags]
        return general or self.bank

    def select(self, verdict: str, user_id: str = "") -> MotivationalQuote:
        pool = self._candidates(verdict)
        if not pool:
            raise ValueError("Quote bank is empty.")
        idx = self._day_seed(user_id, verdict) % len(pool)
        return pool[idx]

    # -- personalisation --------------------------------------------------
    def personalise(self, summaries: Sequence[AnalysisSummary],
                    athlete_name: str = "",
                    user_id: str = "") -> Tuple[MotivationalQuote, str, str,
                                                str]:
        """Return (quote, personal_line_fa, personal_line_finglish, verdict).

        The personal line always references real numbers when history exists.
        """
        tracker = ProgressTracker(summaries)
        name = (athlete_name or "").strip()
        greeting = ("%s عزیز، " % name) if name else ""
        greeting_fn = ("%s, " % name) if name else ""

        if not tracker.items:
            quote = self.select("welcome", user_id)
            return (quote,
                    "%sبه ستارگان دریا خوش آمدی! اولین تحلیلت را بگیر تا روندت را دنبال کنیم." % greeting,
                    "%sBe Setargan-Darya khosh amadi! Avvalin tahlilat ra begir ta ravandat ra donbal konim." % greeting_fn,
                    "welcome")

        verdict = tracker.overall()
        style = tracker.items[-1].style or ""
        if verdict == ProgressTracker.IMPROVING:
            quote = self.select("improving", user_id)
            detail_fa, detail_fn = self._improving_line(tracker)
        elif verdict == ProgressTracker.DECLINING:
            quote = self.select("declining", user_id)
            detail_fa, detail_fn = self._declining_line(tracker)
        else:
            quote = self.select("stable", user_id)
            detail_fa, detail_fn = self._stable_line(tracker)
        style_fa = " (سبک: %s)" % style if style else ""
        line_fa = "%s%s%s" % (greeting, detail_fa, style_fa)
        line_fn = "%s%s" % (greeting_fn, detail_fn)
        return quote, line_fa, line_fn, verdict

    # -- detail builders --------------------------------------------------
    @staticmethod
    def _improving_line(t: ProgressTracker) -> Tuple[str, str]:
        d = t.delta_pct("swolf")
        if d is not None and d < -0.5:
            return ("روندت عالی است؛ SWOLF تو %.1f%% بهتر شده. همین مسیر را ادامه بده!" % abs(d),
                    "Ravandat ali ast; SWOLF-e to %.1f%% behtar shode. Hamin masir ra edame bede!" % abs(d))
        d = t.delta_pct("mean_speed")
        if d is not None and d > 0.5:
            return ("سرعت میانگینت %.1f%% بالا رفته؛ تمرین‌ها دارند جواب می‌دهند!" % d,
                    "Sorat-e miyanginat %.1f%% bala rafte; tamrin-ha darand javab midahand!" % d)
        d = t.delta_pct("symmetry")
        if d is not None and d > 0.5:
            return ("تقارن کششت %.1f%% بهتر شده؛ بدنت متعادل‌تر کار می‌کند." % d,
                    "Tagharon-e kesheshat %.1f%% behtar shode; badanat moteadel-tar kar mikonad." % d)
        return ("روند کلی‌ات رو به بهبود است؛ امروز هم با تمرکز شنا کن!",
                "Ravand-e kolliat ro be behbood ast; emrooz ham ba tamarkoz shena kon!")

    @staticmethod
    def _declining_line(t: ProgressTracker) -> Tuple[str, str]:
        d = t.delta_pct("swolf")
        if d is not None and d > 0.5:
            return ("SWOLF تو %.1f%% بالا رفته؛ امروز روی طول ضربه و سرش تمرکز کن، نه سرعت." % d,
                    "SWOLF-e to %.1f%% bala rafte; emrooz rooye tool-e zarbe va seresh tamarkoz kon, na sorat." % d)
        d = t.delta_pct("symmetry")
        if d is not None and d < -0.5:
            return ("تقارن کششت %.1f%% افت کرده؛ دریل تک‌دست امروز بهترین نسخه برای توست." % abs(d),
                    "Tagharon-e kesheshat %.1f%% oft karde; drill-e tak-dast-e emrooz behtarin noskhe baraye tost." % abs(d))
        return ("روندت کمی افت کرده؛ اشکالی ندارد، امروز سبک و تمیز شنا کن و برگرد!",
                "Ravandat kami oft karde; eshkali nadarad, emrooz sabok va tamiz shena kon va bargard!")

    @staticmethod
    def _stable_line(t: ProgressTracker) -> Tuple[str, str]:
        nxt = t.predict_next("swolf")
        if nxt is not None:
            return ("روندت پایدار است؛ پیش‌بینی جلسه بعد SWOLF حدود %.1f است. یک محرک جدید لازم داری!" % nxt,
                    "Ravandat paydar ast; pishbini-ye jalase-ye bad SWOLF hodood %.1f ast. Yek moharrek-e jadid lazem dari!" % nxt)
        return ("روندت پایدار است؛ برای شکستن پلاتو شدت یا حجم تمرین را کمی بالا ببر!",
                "Ravandat paydar ast; baraye shekastan-e plateau sheddat ya hajm-e tamrin ra kami bala bebar!")
