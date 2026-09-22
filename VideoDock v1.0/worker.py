"""worker.py — 单个下载任务的子进程托管线程

本次修正（中文标题乱码）：
  yt-dlp 子进程往管道写 stdout 的编码由其运行环境决定
  （Windows 上通常=本地 ANSI 代码页 GBK，而不是 UTF-8）。
  旧版固定用 utf-8 解码 → 中文标题乱码。
  现改为：优先按本地代码页（locale.getpreferredencoding）
  解码；由于仍可能存在个别字节无法映射，用 errors=replace
  兜底，保证永不崩。env 仍设 PYTHONUTF8=1 供支持该变量的
  版本使用（两路保险）。
"""

import collections
import locale
import os
import re
import subprocess
import sys
import threading

from builder import CREATE_NO_WINDOW, MARK_FILE, MARK_PROG, MARK_TITLE
from i18n import tr

PROG_RE = re.compile(
    r"^" + re.escape(MARK_PROG) + r"(.+?)@@@(.+?)@@@(.+?)")
FILE_RE = re.compile(r"^" + re.escape(MARK_FILE) + r"(.*)$")
TITLE_RE = re.compile(r"^" + re.escape(MARK_TITLE) + r"(.*)$")

PCT_RE = re.compile(r"^\[download\]\s+([\d.]+)%")
SPEED_RE = re.compile(r"\bat\s+(.+?)\s+ETA\s")
ETA_RE = re.compile(r"\bETA\s+(\S+)")
DEST_RE = re.compile(r"^\[download\] Destination: (.+)")
POST_DEST_RE = re.compile(
    r"^\[(?:Merger|ExtractAudio|VideoConvertor|FixupM3u8)\]"
    r"\s+Destination: (.+)")
ALREADY_RE = re.compile(
    r"^\[download\] (.+) has already been downloaded")


def _to_float(s, default=0.0):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


class TaskWorker(threading.Thread):

    def __init__(self, task_id, argv, on_event):
        super().__init__(daemon=True)
        self.task_id = task_id
        self.argv = argv
        self.on_event = on_event
        self.proc = None
        self._stop = False
        self._err_tail = collections.deque(maxlen=15)

    def kill(self):
        self._stop = True
        p = self.proc
        if p is None or p.poll() is not None:
            return
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(p.pid)],
                    creationflags=CREATE_NO_WINDOW,
                    capture_output=True)
            else:
                p.terminate()
        except OSError:
            pass

    def _drain_stderr(self):
        try:
            for raw in self.proc.stderr:
                line = raw.strip()
                if line:
                    self._err_tail.append(line)
        except (OSError, ValueError):
            pass

    def _emit(self, **kw):
        try:
            self.on_event(self.task_id, **kw)
        except Exception:
            pass

    def run(self):
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"       # 对支持该变量的版本生效
        enc = (locale.getpreferredencoding(False) or "utf-8")
        try:
            self.proc = subprocess.Popen(
                self.argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True, bufsize=1,
                encoding=enc,               # 按本地代码页解码（GBK）
                errors="replace",           # 个别字节解不了→替换符
                creationflags=CREATE_NO_WINDOW,
                env=env,
            )
        except FileNotFoundError:
            self._emit(type="done", ok=False, error=tr("worker.no_exe"))
            return
        except OSError as e:
            self._emit(type="done", ok=False, error=str(e))
            return

        threading.Thread(target=self._drain_stderr,
                         daemon=True).start()

        for raw in self.proc.stdout:
            line = raw.strip()
            if not line:
                continue
            m = PROG_RE.match(line)          # 完整模式：进度行
            if m:
                pct = m.group(1).strip().rstrip("%")
                self._emit(type="progress",
                           percent=_to_float(pct),
                           speed=m.group(2).strip(),
                           eta=m.group(3).strip())
            elif (m := TITLE_RE.match(line)):
                t = m.group(1).strip()
                if t:
                    self._emit(type="title", title=t)
            elif (m := FILE_RE.match(line)):
                path = m.group(1).strip()
                if path:
                    self._emit(type="finished_file", path=path)
            else:
                m = PCT_RE.match(line)       # 兼容模式：进度行
                if m:
                    sp = SPEED_RE.search(line)
                    et = ETA_RE.search(line)
                    eta = et.group(1) if et else ""
                    if eta.lower() == "unknown":
                        eta = ""
                    self._emit(type="progress",
                               percent=_to_float(m.group(1)),
                               speed=(sp.group(1).strip()
                                      if sp else ""),
                               eta=eta)
                else:
                    m = POST_DEST_RE.match(line)  # 合并后文件
                    if m:
                        self._emit(type="finished_file",
                                   path=m.group(1))
                    else:
                        m = DEST_RE.match(line)   # 下载目标名
                        if m:
                            path = m.group(1)
                            base = os.path.splitext(
                                os.path.basename(path))[0]
                            title = re.sub(r"\s*\[[^\]]+\]\s*$",
                                           "", base)
                            if title:
                                self._emit(type="title", title=title)
                            self._emit(type="finished_file",
                                       path=path)
                        else:
                            m = ALREADY_RE.match(line)
                            if m:
                                self._emit(type="finished_file",
                                           path=m.group(1))
                            else:
                                self._emit(type="log", text=line)
            if self._stop:
                break

        code = self.proc.wait()
        if self._stop:
            self._emit(type="canceled")
        elif code == 0:
            self._emit(type="done", ok=True)
        else:
            err = "\n".join(self._err_tail).strip()
            self._emit(type="done", ok=False,
                       error=err or f"yt-dlp exit {code}")


if __name__ == "__main__":
    # 自测：GBK 环境模拟。注意 fake 输出行在源码里是 UTF-8 字面量，
    # 子进程打印时会按其 stdout 编码转出——这正是我们要测的链路。
    import i18n
    i18n.init("zh")
    fake = [sys.executable, "-X", "utf8", "-c", (
        "print('[download]   20.0% of  5MiB at  1MiB/s ETA 00:01',"
        " flush=True)\n"
        "print('TITLE@@@演示标题', flush=True)\n"
        "print('FILE@@@E:/movie/demo.mp4', flush=True)\n")]
    w = TaskWorker("demo", fake, lambda tid, **kw: print(kw))
    w.start()
    w.join()