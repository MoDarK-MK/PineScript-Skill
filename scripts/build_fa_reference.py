#!/usr/bin/env python3
"""
build_fa_reference.py - Generate the Persian quick reference for the lint rules.

The linter speaks English and this repo's owner works in Persian. A one-line
Persian gloss per rule turns a code in the output into something readable
without a round trip through the English catalog.

GENERATED, not hand-written, from two sources: the rule catalog for codes and
severities, and TRANSLATIONS below for the prose. A rule with no translation is
rendered with its English summary and listed as untranslated, so the gap is
visible instead of silently missing.

Usage:
    python3 scripts/build_fa_reference.py
    python3 scripts/build_fa_reference.py --check     # exit 1 if stale
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pine_lint

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "references" / "lint-rules.fa.md"

SEVERITY_FA = {
    "error": "خطا",
    "warning": "هشدار",
    "info": "نکته",
}

TRANSLATIONS = {
    "PINE001": "دستور //@version= نیست یا خراب است — بدون آن Pine نسخه ۱ فرض می‌کند.",
    "PINE002": "هیچ indicator() / strategy() / library() اعلام نشده.",
    "PINE003": "پرانتز یا براکت باز مانده.",
    "PINE004": "نحو منسوخ study() یا security().",
    "PINE005": "انباشتگر بدون var — هر کندل صفر می‌شود.",
    "PINE006": "request.security() بدون lookahead صریح.",
    "PINE007": "ورودی بدون عنوان.",
    "PINE008": "خط بلندتر از حد مجاز.",
    "PINE009": "نزدیک یا فراتر از سقف ۶۴ plot.",
    "PINE010": "پارامتر when= در v6 حذف شده.",
    "PINE011": "پارامتر transp= در v6 حذف شده.",
    "PINE012": "linewidth کمتر از حداقل ۱ در v6.",
    "PINE013": "switch بدون شاخه‌ی پیش‌فرض «=>» (در v6 اجباری).",
    "PINE014": "عملگر تاریخچه [] روی مقدار ثابت — در v6 نامعتبر.",
    "PINE015": "یک پارامتر نام‌دار دوبار در یک فراخوانی.",
    "PINE016": "مقایسه‌ی timeframe.period با رشته‌ی بدون ضریب.",
    "PINE017": "تله‌ی ارزیابی تنبل and/or در v6.",
    "PINE018": "نام‌گذاری خارج از قرارداد camelCase / SNAKE_CASE.",
    "PINE019": "تب و فاصله با هم در تورفتگی یک خط.",
    "PINE020": "سرِ بلوک (if/for/while/…) بدون بدنه‌ی تورفته.",
    "PINE021": "strategy() بدون پارامترهای توصیه‌شده‌ی حجم و کارمزد.",
    "PINE022": "overlay= صریح تعیین نشده.",
    "PINE023": "تقسیم عدد صحیح بر صحیح — v6 کسر می‌دهد، v5 می‌بُرید.",
    "PINE025": "نزدیک یا فراتر از سقف خط/باکس/لیبل/جدول.",
    "PINE026": "بخشی از فایل با تب و بخشی با فاصله تورفته شده.",
    "PINE027": "اسکریپت هیچ خروجی یا سفارشی تولید نمی‌کند.",
    "PINE028": "کد واقعی پیش از //@version= آمده.",
    "PINE029": "strategy.exit() بدون هیچ سطح توقف یا حد — هیچ سفارشی ثبت نمی‌کند.",
    "PINE030": "strategy.exit() سطح نسبی و مطلق را با هم آورده.",
    "PINE031": "پارامتر تیک‌محور با عبارت قیمت‌محور پر شده.",
    "PINE032": "strategy.position_avg_price بدون گارد «پوزیشن باز است».",
    "PINE033": "qty= یا qty_percent= بیرون از بازه‌ی مجاز.",
    "PINE034": "from_entry= به شناسه‌ای اشاره می‌کند که هیچ ورودی‌ای نمی‌سازد.",
    "PINE035": "استراتژی ورود دارد ولی هیچ خروج یا گارد ریسکی ندارد.",
    "PINE036": "table.cell() بدون text_color — پیش‌فرض Pine سیاه است و روی تم تیره نامرئی.",
    "PINE037": "array.new داخل بلوکِ هر-کندل بدون var — هر بار از نو ساخته می‌شود.",
    "PINE038": "درایینگ‌ها حذف و دوباره ساخته می‌شوند به‌جای جابه‌جایی.",
    "PINE039": "request.security() تکراری با همان نماد، تایم‌فریم و lookahead.",
    "PINE040": "plot()/plotshape()/plotchar() بدون عنوان.",
    "PINE041": "size.large یا size.huge — راهنمای طراحی سقف را size.normal گذاشته.",
    "PINE042": "تابع متغیر سراسری را تغییر می‌دهد (خطای کامپایل CE10088).",
    "PINE043": "شاخه‌های پایانی if/else تابع نوع متفاوت برمی‌گردانند (CE10235).",
    "PINE044": "تایم‌فریم ثانیه‌ای — نیازمند پلن Premium، وگرنه کل اسکریپت بالا نمی‌آید.",
    "PINE045": "متغیرِ مقداردهی‌شده با na با ==/!= مقایسه شده به‌جای na() — گارد هرگز فعال نمی‌شود.",
    "PINE046": "input.*() بیرون از دامنه‌ی سراسری.",
    "PINE047": "plot()/bgcolor()/fill() بیرون از دامنه‌ی سراسری.",
    "PINE048": "نزدیک یا فراتر از سقف ۴۰ فراخوانی request.*().",
    "PINE049": "فراخوانی سفارش strategy.*() داخل تابع.",
    "PINE050": "انتساب با := به نامی که هیچ‌جا اعلام نشده.",
    "PINE051": "متغیر اعلام شده ولی هرگز خوانده نمی‌شود (مرده یا فقط-نوشتنی).",
    "PINE052": "درایینگ داخل حلقه ساخته می‌شود ولی max_*_count تعیین نشده — پیش‌فرض ۵۰ است.",
    "PINE053": "بدترین حالت تعداد تکرار حلقه‌های تودرتو از بودجه بیشتر است.",
    "PINE054": "مجموعه‌ی var داخل شاخه‌ی قیمت‌محور بدون گارد barstate.isconfirmed رشد می‌کند.",
    "PINE055": "تابع به متغیری ارجاع می‌دهد که پایین‌تر در فایل اعلام شده.",
    "PINE056": "تابع اعلام شده ولی هرگز فراخوانی نمی‌شود.",
    "PINE057": "شرط ثابت است — همیشه درست یا همیشه غلط.",
    "PINE058": "نامی که یک فضای‌نام داخلی را سایه می‌اندازد و بعد با نقطه صدا زده می‌شود — مقدار اشتباه خوانده می‌شود بدون هیچ خطایی.",
    "PINE059": "رشته‌ای که در همان خط بسته نمی‌شود — پاین رشتهٔ چندخطی ندارد و کامپایل رد می‌کند.",
    "PINE060": "تقسیم دو عدد صحیح جایی که کسر لازم بوده — پاین نتیجه را صحیح می‌دهد و کسر پیش از هر چیز حذف می‌شود.",
    "PINE061": "جدول با بیش از ۸ ردیف بدون خط جداکننده — خوانایی داشبورد کاهش می‌یابد.",
    "PINE062": "چندین label.new در barstate.islast بدون فاصله‌گذاری و ضد برخورد.",
    "PINE063": "کلمه‌ای که پاین رزرو کرده به‌عنوان نام متغیر یا تابع — مثل range و text؛ کامپایل رد می‌کند.",
}

HEADER = """# مرجع سریع قواعد لینت

> **این فایل تولید می‌شود.** ویرایش دستی نکنید — `scripts/build_fa_reference.py`
> آن را از خود کاتالوگ قواعد می‌سازد، پس شماره و شدت هرگز از کد جدا نمی‌افتد.
> برای توضیح کامل هر قاعده با مثال، به `references/lint-rules.md` مراجعه کنید.

معنی شدت‌ها: **خطا** یعنی به احتمال زیاد کامپایل نمی‌شود یا قطعاً غلط است.
**هشدار** یعنی کامپایل می‌شود ولی به احتمال زیاد باگ است. **نکته** یعنی تفاوتی
که دانستنش خوب است، نه مشکلی که باید رفع شود.

خاموش‌کردن یک قاعده: `// pine-lint-disable-next-line CODE` روی خط قبل،
`// pine-lint-disable-line CODE` روی همان خط، یا `// pine-lint-disable CODE`
برای کل فایل.

| کد | شدت | چه می‌گوید | خودترمیم |
|---|---|---|---|
"""


def render():
    rows = []
    untranslated = []
    for code in sorted(pine_lint.RULES):
        severity, summary = pine_lint.RULES[code]
        text = TRANSLATIONS.get(code)
        if text is None:
            untranslated.append(code)
            text = summary + "  ‹ترجمه‌نشده›"
        fixable = "✓" if code in pine_lint.FIXABLE else ""
        rows.append(f"| `{code}` | {SEVERITY_FA[severity]} | {text} | {fixable} |")

    body = HEADER + "\n".join(rows) + "\n"
    body += (f"\n\nمجموعاً {len(pine_lint.RULES)} قاعده. "
             f"{len(pine_lint.FIXABLE)} قاعده با `--fix` خودکار رفع می‌شود.\n")
    if untranslated:
        body += ("\n> **ترجمه‌نشده:** " + "، ".join(f"`{c}`" for c in untranslated) +
                 " — این‌ها با خلاصه‌ی انگلیسی نمایش داده می‌شوند تا کمبودشان دیده شود.\n")
    return body, untranslated


def main():
    parser = argparse.ArgumentParser(description="Generate the Persian rule reference.")
    parser.add_argument("--check", action="store_true", help="Exit 1 if stale")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

    body, untranslated = render()
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current == body:
            print(f"{OUT.relative_to(ROOT)}: up to date "
                  f"({len(pine_lint.RULES) - len(untranslated)}/{len(pine_lint.RULES)} translated)")
            return 0
        print(f"{OUT.relative_to(ROOT)}: OUT OF DATE")
        print("Run: python3 scripts/build_fa_reference.py")
        return 1

    OUT.write_text(body, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} "
          f"({len(pine_lint.RULES) - len(untranslated)}/{len(pine_lint.RULES)} translated)")
    if untranslated:
        print("untranslated: " + ", ".join(untranslated))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
