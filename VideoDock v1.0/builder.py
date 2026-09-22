"""builder.py — 统一参数模型与命令构建器

本次修正（关键）：
  · 移除 --encoding utf-8 —— 该选项在新版 yt-dlp 中已被移除，
    传入会导致 yt-dlp 立即报错退出（表现为任务瞬间失败、
    没有任何进度/速度显示）。
  · 进度解析加固：worker 对 "Unknown" 等非数值百分比按 0 处理，
    不再让文本混入进度条。
"""

import os
from dataclasses import dataclass, field

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


@dataclass
class TaskSpec:
    url: str
    quality: str = "best"
    custom_format: str = ""
    audio_format: str = "mp3"
    write_subs: bool = False
    sub_langs: str = "all"
    convert_subs: bool = True
    embed_thumb: bool = False
    download_dir: str = ""
    output_tmpl: str = ""
    playlist: bool = False
    proxy: str = ""
    cookies_browser: str = ""
    extra_args: list = field(default_factory=list)


FORMAT_MAP = {
    "best": "bv*+ba/b",
    "1080": "bv*[height<=1080]+ba/b[height<=1080]/b",
    "720": "bv*[height<=720]+ba/b[height<=720]/b",
    "480": "bv*[height<=480]+ba/b[height<=480]/b",
    "audio": "ba/b",
}

MARK_PROG = "PROG@@@"
MARK_FILE = "FILE@@@"
MARK_TITLE = "TITLE@@@"


def build_argv(spec: TaskSpec, cfg: dict) -> list:
    has_ff = _ffmpeg_ok(cfg)
    q = spec.quality
    a = [cfg["ytdlp_path"]]

    # ---- 格式选择 ----
    if q == "custom" and spec.custom_format:
        a += ["-f", spec.custom_format]
    elif q == "audio":
        a += ["-f", FORMAT_MAP["audio"]]
        if has_ff:
            a += ["-x", "--audio-format", spec.audio_format,
                  "--audio-quality", "0"]
    elif q in FORMAT_MAP:
        if has_ff:
            a += ["-f", FORMAT_MAP[q]]
        else:
            if q == "best":
                a += ["-f", "b"]
            else:
                a += ["-f", "b[height<=%s]/b" % q]

    # ---- 输出位置 ----
    a += ["-P", spec.download_dir or cfg["download_dir"]]
    a += ["-o", spec.output_tmpl or cfg["output_template"]]

    # ---- 字幕 / 封面 ----
    if has_ff:
        if spec.write_subs:
            a += ["--sub-langs", spec.sub_langs or "all"]
            if spec.convert_subs:
                a += ["--convert-subs", "srt"]
            a += ["--embed-subs"]
        if spec.embed_thumb:
            a += ["--embed-thumbnail"]

    # ---- 网络 ----
    proxy = spec.proxy or cfg.get("proxy", "")
    if proxy:
        a += ["--proxy", proxy]
    cookies = spec.cookies_browser or cfg.get("cookies_browser", "")
    if cookies:
        a += ["--cookies-from-browser", cookies]

    # ---- 播放列表 ----
    if not spec.playlist:
        a.append("--no-playlist")

    # ---- 机器可读输出 ----
    # 注意：不要再加 --encoding（新版 yt-dlp 已移除该选项）。
    # 中文输出乱码由 worker 启动子进程时的
    # PYTHONIOENCODING=utf-8 环境变量兜底。
    a += ["--newline"]
    a += ["--progress-template",
          "download:" + MARK_PROG + "%(progress._percent_str)s"
          "@@@%(progress._speed_str)s@@@%(progress._eta_str)s"]
    a += ["--no-simulate",
          "--print", "before_dl:" + MARK_TITLE + "%(title)s",
          "--print", "after_move:" + MARK_FILE + "%(filepath)s"]

    # ---- 附加参数 ----
    a += list(spec.extra_args)
    a.append(spec.url)
    return a


def _ffmpeg_ok(cfg: dict) -> bool:
    import shutil
    from pathlib import Path
    p = cfg.get("ffmpeg_path", "")
    if p and Path(p).is_file():
        return True
    exe_dir = Path(cfg.get("ytdlp_path", "")).parent
    name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    if (exe_dir / name).is_file():
        return True
    return shutil.which("ffmpeg") is not None


def _quote_win(s: str) -> str:
    return f'"{s}"' if (" " in s or "\t" in s) else s


def preview_command(argv: list) -> str:
    return " ".join(_quote_win(x) for x in argv)


if __name__ == "__main__":
    cfg = {"ytdlp_path": r"G:\yt-dlp_win\yt-dlp.exe",
           "download_dir": r"E:\movie",
           "output_template": "%(title)s [%(id)s].%(ext)s",
           "ffmpeg_path": "", "proxy": "", "cookies_browser": ""}
    spec = TaskSpec(url="https://youtu.be/dQw4w9WgXcQ",
                    quality="1080", write_subs=True)
    print(preview_command(build_argv(spec, cfg)))