"""i18n.py — VideoDock 多语言机制（唯一入口 tr()）

_EXTRA_ZH 内置兜底词：语言文件尚未收录的新界面词先由这里
提供中文；以后补录进 zh.json 后以文件为准。其他语言自动回退中文。
自测：python i18n.py
"""

import json
import locale
from pathlib import Path

LANG_DIR = Path(__file__).resolve().parent / "lang"

LANGS = {
    "zh": "中文",
    "en": "English",
    "fr": "Français",
    "es": "Español",
    "ru": "Русский",
    "ja": "日本語",
    "ko": "한국어",
}

_EXTRA_ZH = {
    "btn.redownload": "重新下载",
    "btn.redownload_all": "全部重新下载",
    "btn.dl_latest": "下载最新版",
    "inst.sc_startmenu": "创建开始菜单快捷方式",
    "inst.sc_desktop": "创建桌面快捷方式",
    "inst.integrate.ok": "已写入 Windows「应用和功能」卸载列表。",
}

_fallback = {}
_current = {}
_current_code = "zh"


def detect_system_lang() -> str:
    try:
        code = (locale.getdefaultlocale()[0] or "zh")[:2].lower()
    except (ValueError, AttributeError):
        code = "zh"
    return code if code in LANGS else "zh"


def resolve(language: str) -> str:
    if not language or language == "auto":
        return detect_system_lang()
    return language if language in LANGS else "zh"


def init(language: str) -> str:
    global _current, _current_code
    _fallback.clear()
    try:
        _fallback.update(json.loads(
            (LANG_DIR / "zh.json").read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        pass
    for k, v in _EXTRA_ZH.items():
        _fallback.setdefault(k, v)
    _current_code = resolve(language)
    _current = {}
    if _current_code != "zh":
        try:
            _current.update(json.loads(
                (LANG_DIR / f"{_current_code}.json")
                .read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            _current = {}
    return _current_code


def tr(key: str, **kw) -> str:
    s = _current.get(key) or _fallback.get(key) or key
    return s.format(**kw) if kw else s


def coverage(language: str):
    n_zh = len(_fallback)
    if language == "zh":
        return n_zh, n_zh, 0
    try:
        cur = json.loads(
            (LANG_DIR / f"{language}.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0, n_zh, n_zh
    missing = [k for k in _fallback if k not in cur]
    return len(cur), n_zh, len(missing)


if __name__ == "__main__":
    import sys
    want = sys.argv[1] if len(sys.argv) > 1 else "zh"
    code = init(want)
    print("lang =", code, "| title =", tr("app.title"))
    print(tr("inst.sc_startmenu"), "|", tr("inst.sc_desktop"))
    n_cur, n_all, miss = coverage(code)
    print(f"coverage: {n_cur}/{n_all}, missing {miss} (fallback=zh)")