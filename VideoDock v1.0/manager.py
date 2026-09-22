"""manager.py — 任务队列与调度中心（定稿版）

状态机：queued → running → done/failed/canceled
                    └→ paused →(恢复)→ queued

stop() 为"立即终结"：点取消当场置 canceled、当场写历史、
当场发完结信号，进程树并行杀死；worker 事后回报被终结守卫忽略。
新增 redownload / redownload_all_failed（详见各方法 docstring）。
"""

import dataclasses
import subprocess
import threading
import time
import uuid

from PySide6.QtCore import QObject, Signal

import config
from builder import CREATE_NO_WINDOW, build_argv
from worker import TaskWorker

FINAL_STATES = {"done", "failed", "canceled"}


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


_KEYS = ("id", "url", "title", "status", "percent", "speed", "eta",
         "file_path", "error", "start_time", "end_time", "proxy")


def _snapshot(task: dict) -> dict:
    return {k: task.get(k, "") for k in _KEYS}


class TaskManager(QObject):

    sig_task_added = Signal(dict)
    sig_task_updated = Signal(str, dict)
    sig_task_finished = Signal(dict)
    sig_queue_changed = Signal(int)

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self._lock = threading.RLock()
        self._tasks = {}
        self._workers = {}
        self._stopping = False
        self._global_paused = False
        self._counter = 0
        self._last_group = 0
        self._last_start = 0.0
        self._timer_pending = threading.Event()
        self._pending_records = []      # 待落盘的历史记录

    # ================= 提交 =================
    def submit(self, spec) -> str:
        proxy = self._next_proxy()
        if proxy:
            spec = dataclasses.replace(spec, proxy=proxy)
            self._maybe_hook()
        argv = build_argv(spec, self.cfg)
        return self._enqueue(argv, spec.url, proxy=proxy)

    def retry(self, old_argv: list, url: str = "",
              title: str = "") -> str:
        argv = list(old_argv)
        if argv:
            argv[0] = self.cfg["ytdlp_path"]
        url = url or (argv[-1] if argv else "")
        return self._enqueue(argv, url, title=title or "retry")

    def redownload(self, tid: str) -> str:
        """单任务重新下载：复用命令，追加 --force-overwrites。"""
        with self._lock:
            task = self._tasks.get(tid)
            if task is None:
                return ""
            argv = list(task["argv"])
            url = task["url"]
            title = task["title"]
        if argv:
            argv[0] = self.cfg["ytdlp_path"]
        if len(argv) >= 2 and "--force-overwrites" not in argv:
            argv.insert(len(argv) - 1, "--force-overwrites")
        return self._enqueue(argv, url, title=title)

    def redownload_all_failed(self) -> int:
        """重新下载全部失败任务，返回入队数量。"""
        with self._lock:
            failed = [t for t in self._tasks.values()
                      if t["status"] == "failed"]
        n = 0
        for t in failed:
            if self.redownload(t["id"]):
                n += 1
        return n

    def _enqueue(self, argv, url, title="", proxy="") -> str:
        tid = uuid.uuid4().hex[:8]
        task = {
            "id": tid, "url": url, "title": title or url,
            "status": "queued", "argv": list(argv), "proxy": proxy,
            "percent": 0.0, "speed": "", "eta": "",
            "file_path": "", "error": "", "last_log": "",
            "start_time": _now(), "end_time": "",
            "finalized": False,
        }
        with self._lock:
            self._tasks[tid] = task
        self.sig_task_added.emit(_snapshot(task))
        self._pump()
        return tid

    # ================= 轮换 =================
    def _next_proxy(self) -> str:
        pool = [p.strip()
                for p in (self.cfg.get("proxy_pool") or []) if p.strip()]
        if not self.cfg.get("rotate_enabled") or len(pool) < 2:
            return ""
        n = max(1, int(self.cfg.get("rotate_every_n", 1)))
        with self._lock:
            idx = (self._counter // n) % len(pool)
            self._counter += 1
        return pool[idx]

    def _maybe_hook(self):
        hook = (self.cfg.get("rotate_command") or "").strip()
        n = max(1, int(self.cfg.get("rotate_every_n", 1)))
        with self._lock:
            group = (self._counter - 1) // n
            changed = hook and group > 0 and group != self._last_group
            self._last_group = group
        if changed:
            threading.Thread(target=self._run_hook, args=(hook,),
                             daemon=True).start()

    @staticmethod
    def _run_hook(hook: str):
        try:
            subprocess.Popen(
                hook, shell=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW)
        except OSError:
            pass

    # ================= 调度 =================
    def _pump(self):
        if self._stopping or self._global_paused:
            return
        started = []
        interval = 0.0
        with self._lock:
            limit = max(1, int(self.cfg.get("max_concurrent", 1)))
            try:
                interval = max(
                    0.0, float(self.cfg.get("task_interval", 0) or 0))
            except (TypeError, ValueError):
                interval = 0.0
            running = sum(1 for t in self._tasks.values()
                          if t["status"] == "running")
            free = limit - running
            if interval > 0:
                free = min(free, 1)
                waited = time.monotonic() - self._last_start
                if self._last_start and waited < interval:
                    free = 0
                    self._schedule_pump(interval - waited)
            queued_left = 0
            for task in self._tasks.values():
                if task["status"] != "queued":
                    continue
                if free > 0:
                    task["status"] = "running"
                    started.append(task)
                    free -= 1
                else:
                    queued_left += 1
        for task in started:
            w = TaskWorker(task["id"], task["argv"], self._on_event)
            with self._lock:
                self._workers[task["id"]] = w
            w.start()
        if started:
            self._last_start = time.monotonic()
            if interval > 0:
                self._schedule_pump(interval)
        self.sig_queue_changed.emit(queued_left)

    def _schedule_pump(self, delay: float):
        if self._stopping or delay <= 0:
            return
        if self._timer_pending.is_set():
            return
        self._timer_pending.set()

        def fire():
            self._timer_pending.clear()
            self._pump()

        t = threading.Timer(delay, fire)
        t.daemon = True
        t.start()

    # ================= worker 回调（后台线程） =================
    def _on_event(self, tid, **kw):
        kind = kw.get("type", "")
        with self._lock:
            task = self._tasks.get(tid)
            if task is None:
                return
            if kind == "progress":
                task["percent"] = kw.get("percent", task["percent"])
                task["speed"] = kw.get("speed", task["speed"])
                task["eta"] = kw.get("eta", task["eta"])
            elif kind == "title":
                if kw.get("title"):
                    task["title"] = kw["title"]
            elif kind == "finished_file":
                task["file_path"] = kw.get("path", "")
            elif kind == "log":
                task["last_log"] = kw.get("text", "")
            elif kind in ("done", "canceled"):
                self._workers.pop(tid, None)
                if task["status"] in FINAL_STATES:
                    pass            # stop() 已即时终结：忽略迟到回报
                elif task["status"] == "paused":
                    pass            # 暂停态：保持，不写历史
                elif kind == "canceled" or self._stopping:
                    task["status"] = "canceled"
                    task["end_time"] = _now()
                    self._finalize_locked(task)
                elif kw.get("ok"):
                    task["status"] = "done"
                    task["percent"] = 100.0
                    task["end_time"] = _now()
                    self._finalize_locked(task)
                else:
                    task["status"] = "failed"
                    task["error"] = kw.get("error", "") or "failed"
                    task["end_time"] = _now()
                    self._finalize_locked(task)
            snap = _snapshot(task)
        self.sig_task_updated.emit(tid, snap)
        self._flush_records()

    def _finalize_locked(self, task):
        """终结并入待写队列（持锁调用；finalized 防重复）。"""
        if task.get("finalized"):
            return
        task["finalized"] = True
        self._pending_records.append({
            "id": task["id"], "url": task["url"],
            "title": task["title"], "status": task["status"],
            "file_path": task["file_path"],
            "command": list(task["argv"]),
            "start_time": task["start_time"],
            "end_time": task.get("end_time") or _now(),
            "error": task["error"],
        })

    def _flush_records(self):
        """待写历史落盘并广播（锁外执行）。"""
        with self._lock:
            records = self._pending_records
            self._pending_records = []
        for record in records:
            config.add_history(self.cfg, record)
            self.sig_task_finished.emit(dict(record))

    # ================= 控制 =================
    def pause(self, tid):
        with self._lock:
            task = self._tasks.get(tid)
            if not task or task["status"] != "running":
                return
            task["status"] = "paused"
            worker = self._workers.get(tid)
        if worker:
            worker.kill()

    def resume(self, tid):
        with self._lock:
            task = self._tasks.get(tid)
            if not task or task["status"] != "paused":
                return
            task["status"] = "queued"
        self.sig_task_updated.emit(tid, _snapshot(task))
        self._pump()

    def set_global_paused(self, on: bool) -> None:
        self._global_paused = bool(on)
        if not on:
            self._pump()

    def is_global_paused(self) -> bool:
        return self._global_paused

    def stop(self, tid):
        """取消（立即终结）：置 canceled → 写历史 → 发信号 →
        杀进程树。卡片立刻响应，不等 worker 回报。"""
        with self._lock:
            task = self._tasks.get(tid)
            if task is None or task["status"] in FINAL_STATES:
                return
            worker = self._workers.pop(tid, None)
            task["status"] = "canceled"
            task["end_time"] = _now()
            self._finalize_locked(task)
        if worker is not None:
            worker.kill()
        self.sig_task_updated.emit(tid, _snapshot(task))
        self._flush_records()
        self._pump()

    def all_tasks(self) -> list:
        with self._lock:
            return [_snapshot(t) for t in self._tasks.values()]

    def shutdown(self):
        self._stopping = True
        with self._lock:
            workers = list(self._workers.values())
            pending = [t for t in self._tasks.values()
                       if t["status"] in ("queued", "running", "paused")]
        for w in workers:
            w.kill()
        with self._lock:
            for t in pending:
                if t["status"] not in FINAL_STATES:
                    t["status"] = "canceled"
                    t["end_time"] = _now()
                self._finalize_locked(t)
        self._flush_records()
        config.save_config(self.cfg)