"""diag.py — 自包含差分诊断（不依赖你的任何其他文件）

用法：python diag.py 视频链接
从"shell 最简命令"逐级加参数到"GUI 同款完整命令"，
定位到底是哪一级导致失败。结果存 diag.log。
"""

import json
import os
import shutil
import subprocess
import sys
import threading
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent
CFG_FILE = APP / "yt-dlp-gui.json"
LOG = APP / "diag.log"
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

DEFAULTS = {
    "ytdlp_path": r"G:\yt-dlp_win\yt-dlp.exe",
    "download_dir": r"E:\movie",
    "output_template": "%(title)s [%(id)s].%(ext)s",
    "proxy": "", "cookies_browser": "",
}

lines = []


def say(t=""):
    print(t)
    lines.append(str(t))


def quote(s):
    return f'"{s}"' if " " in s else s


def load_cfg():
    cfg = dict(DEFAULTS)
    if CFG_FILE.exists():
        try:
            data = json.loads(
                CFG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update(data)
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def version_of(exe):
    try:
        out = subprocess.run(
            [exe, "--version"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15,
            creationflags=CREATE_NO_WINDOW)
        if out.returncode == 0:
            return (out.stdout or "").strip() or "(空输出)"
        return f"退出码{out.returncode} {(out.stderr or '')[:120]}"
    except Exception as e:
        return f"无法执行：{e}"


def run_stage(title, argv):
    say("")
    say(f"—— {title} ——")
    say("命令：" + " ".join(quote(a) for a in argv))
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        p = subprocess.Popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL, text=True, bufsize=1,
            encoding="utf-8", errors="replace",
            creationflags=CREATE_NO_WINDOW, env=env)
    except Exception as e:
        say(f"[启动失败] {e}")
        return False
    errs = []
    threading.Thread(
        target=lambda: [errs.append(l.rstrip())
                        for l in p.stderr],
        daemon=True).start()
    for raw in p.stdout:
        line = raw.rstrip()
        if line:
            say("  | " + line[:180])
    code = p.wait()
    say(f"[退出码 {code}] → {'成功' if code == 0 else '失败'}")
    if code != 0 and errs:
        say("—— stderr 末尾 15 行 ——")
        for ln in errs[-10:]:
            say("  ! " + ln[:200])
    return code == 0


def main():
    url = sys.argv[1].strip() if len(sys.argv) > 1 \
        else input("请输入下载链接：").strip()
    cfg = load_cfg()
    exe = cfg["ytdlp_path"]

    say("=" * 60)
    say("【0】环境")
    say(f"yt-dlp : {exe}  存在={Path(exe).is_file()}  "
        f"版本={version_of(exe)}")
    say(f"下载目录: {cfg['download_dir']}  "
        f"存在={Path(cfg['download_dir']).is_dir()}")
    say(f"代理   : {cfg.get('proxy') or '无'}    "
        f"cookie浏览器: {cfg.get('cookies_browser') or '无'}")

    # GUI 自己记下来的失败原因（来自历史记录）
    say("")
    say("【0.5】GUI 历史里最近 3 条失败记录的错误原文")
    fails = [r for r in (cfg.get("history") or [])
             if r.get("status") == "failed"][-3:]
    if not fails:
        say("  （没有失败记录）")
    for rec in fails:
        say(f"  [{rec.get('end_time', '')}] "
            f"{(rec.get('title') or '')[:40]}")
        for ln in (rec.get("error") or "(空)").splitlines()[-4:]:
            say("      " + ln[:160])

    # 阶段1：shell 最简用法（你手工成功的那类命令）
    run_stage("阶段1 shell式最简命令（--simulate，不真下载）",
              [exe, "--no-playlist", "--simulate", url])

    # 阶段2：加画质选择器
    run_stage("阶段2 + 画质选择器 -f bv*+ba/b（--simulate）",
              [exe, "-f", "bv*+ba/b", "--no-playlist",
               "--simulate", url])

    # 阶段3：加 GUI 的全部机器可读参数
    argv3 = [exe, "-f", "bv*+ba/b",
             "-P", cfg["download_dir"],
             "-o", cfg["output_template"],
             "--no-playlist", "--newline", "--encoding", "utf-8",
             "--progress-template",
             "download:PROG@@@%(progress._percent_str)s"
             "@@@%(progress._speed_str)s@@@%(progress._eta_str)s",
             "--no-simulate",
             "--print", "before_dl:TITLE@@@%(title)s",
             "--print", "after_move:FILE@@@%(filepath)s",
             "--simulate", url]
    ok3 = run_stage("阶段3 GUI同款机器参数（--simulate）", argv3)

    if ok3:
        argv5 = [x for x in argv3 if x != "--simulate"]
        run_stage("阶段4 GUI同款完整命令，真实下载", argv5)

    say("")
    say("判读：阶段1失败=网络/风控；仅阶段3起失败=某个新参数问题；"
        "全成功但GUI仍失败=GUI运行时问题。")


try:
    main_ok = True
except Exception:
    main_ok = False

if __name__ == "__main__":
    try:
        main.__globals__  # 占位，真正执行在下方
    except Exception:
        pass
    try:
        # 执行 main 流程
        cfg = load_cfg()
        url = sys.argv[1].strip() if len(sys.argv) > 1 \
            else input("请输入下载链接后回车：").strip()
        exe = cfg["ytdlp_path"]
        say("=" * 60)
        say("【0】环境")
        say(f"yt-dlp : {exe}  存在={Path(exe).is_file()}  "
            f"版本={version_of(exe)}")
        say(f"下载目录: {cfg['download_dir']}  "
            f"存在={Path(cfg['download_dir']).is_dir()}")
        say(f"代理   : {cfg.get('proxy') or '无'}    "
            f"cookie浏览器: {cfg.get('cookies_browser') or '无'}")
        fails = [r for r in (cfg.get("history") or [])
                 if r.get("status") == "failed"][-3:]
        say("")
        say("【0.5】GUI 历史里最近失败记录的错误原文")
        if not fails:
            say("  （没有）")
        for rec in fails:
            say(f"  时间 {rec.get('end_time', '')}  "
                f"标题 {(rec.get('title') or '')[:50]}")
            for ln in (rec.get("error") or "(空)").splitlines()[-5:]:
                say("      " + ln[:160])
        run_stage("阶段1 shell式最简命令（--simulate）",
                  [exe, "--no-playlist", "--simulate", url])
        run_stage("阶段2 +画质选择器 -f bv*+ba/b（--simulate）",
                  [exe, "-f", "bv*+ba/b", "--no-playlist",
                   "--simulate", url])
        argv3 = [exe, "-f", "bv*+ba/b",
                 "-P", cfg["download_dir"],
                 "-o", cfg["output_template"],
                 "--no-playlist", "--newline",
                 "--encoding", "utf-8",
                 "--progress-template",
                 "download:PROG@@@%(progress._percent_str)s"
                 "@@@%(progress._speed_str)s@@@%(progress._eta_str)s",
                 "--no-simulate",
                 "--print", "before_dl:TITLE@@@%(title)s",
                 "--print", "after_move:FILE@@@%(filepath)s",
                 "--simulate", url]
        if run_stage("阶段3 GUI同款机器参数（--simulate）", argv3):
            run_stage("阶段4 GUI同款完整命令（真实下载）",
                      [x for x in argv3 if x != "--simulate"])
    except Exception:
        import traceback
        say(traceback.format_exc())
    try:
        with open(LOG, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except OSError:
        pass
    print(f"\n已保存到 {LOG}")
    input("\n按回车键关闭…")