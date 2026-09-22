"""config.py — 信息文件（yt-dlp-gui.json）读写 + 路径规则

存放规则：
  源码运行       → 与代码同目录
  打包 + 便携版  → exe 旁存在 portable.flag 时，与 exe 同目录
  打包 + 安装版  → %APPDATA%\\VideoDock\\

自愈逻辑：配置的 yt-dlp 路径失效时，按顺序自动改用
  ① 程序旁的 yt-dlp.exe（单文件版分发布局）
  ② 程序旁的 yt-dlp_win\\yt-dlp.exe（旧目录版布局，向后兼容）
  ③ PATH 中的 yt-dlp
ffmpeg：只要 ffmpeg.exe 与 yt-dlp.exe 同目录（默认布局即如此），
ffmpeg 路径留空也会自动就绪。
"""

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / "portable.flag").is_file():
            return exe_dir
        base = os.environ.get("APPDATA") or str(Path.home())
        d = Path(base) / "VideoDock"
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            return exe_dir
        return d
    return Path(__file__).resolve().parent


APP_DIR = _app_dir()
CONFIG_FILE = APP_DIR / "yt-dlp-gui.json"

DEFAULTS = {
    "ytdlp_path": r"G:\yt-dlp_win\yt-dlp.exe",
    "ffmpeg_path": "",
    "download_dir": r"E:\movie",
    "output_template": "%(title)s [%(id)s].%(ext)s",
    "max_concurrent": 1,
    "history_max": 500,
    "proxy": "",
    "cookies_browser": "",
    "language": "auto",
    "show_welcome": True,
    "sound_enabled": True,
    "popup_enabled": True,
    "rotate_enabled": False,
    "proxy_pool": [],
    "rotate_every_n": 5,
    "rotate_command": "",
    "task_interval": 0,
    "history": [],
}

_save_lock = threading.Lock()
_version_cache = {}


def _heal_ytdlp_path(cfg: dict) -> None:
    """配置路径失效时：① 程序旁单文件 exe → ② 旧目录版布局 →
    ③ PATH。"""
    p = str(cfg.get("ytdlp_path", "") or "")
    if p and Path(p).is_file():
        return
    for cand in (APP_DIR / "yt-dlp.exe",
                 APP_DIR / "yt-dlp_win" / "yt-dlp.exe"):
        if cand.is_file():
            cfg["ytdlp_path"] = str(cand)
            return
    found = shutil.which("yt-dlp")
    if found:
        cfg["ytdlp_path"] = found


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            data = json.loads(
                CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update(data)
        except (json.JSONDecodeError, OSError):
            pass
    _heal_ytdlp_path(cfg)
    try:
        Path(cfg["download_dir"]).mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return cfg


def save_config(cfg: dict) -> None:
    tmp = CONFIG_FILE.parent / (CONFIG_FILE.name + ".tmp")
    with _save_lock:
        try:
            tmp.write_text(
                json.dumps(cfg, ensure_ascii=False, indent=2),
                encoding="utf-8")
            tmp.replace(CONFIG_FILE)
        except OSError:
            pass


def add_history(cfg: dict, record: dict) -> None:
    history = cfg.setdefault("history", [])
    history.append(record)
    limit = int(cfg.get("history_max", 500))
    if len(history) > limit:
        del history[: len(history) - limit]
    save_config(cfg)


def ytdlp_ok(cfg: dict) -> bool:
    return Path(cfg["ytdlp_path"]).is_file()


def ytdlp_version(cfg: dict) -> str:
    exe = cfg.get("ytdlp_path", "")
    if exe in _version_cache:
        return _version_cache[exe]
    ver = ""
    try:
        out = subprocess.run(
            [exe, "--version"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15,
            creationflags=CREATE_NO_WINDOW)
        if out.returncode == 0:
            ver = (out.stdout or "").strip()
    except Exception:
        ver = ""
    _version_cache[exe] = ver
    return ver


def ffmpeg_ok(cfg: dict) -> bool:
    """显式路径 → yt-dlp 同目录 → PATH。"""
    p = cfg.get("ffmpeg_path", "")
    if p and Path(p).is_file():
        return True
    exe_dir = Path(cfg["ytdlp_path"]).parent
    name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    if (exe_dir / name).is_file():
        return True
    return shutil.which("ffmpeg") is not None