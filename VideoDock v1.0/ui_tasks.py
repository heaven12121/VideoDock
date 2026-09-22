"""ui_tasks.py — 下载任务页

本次改动：
  · 卡片新增"重新下载"按钮（失败/已取消后可用，全新下载）；
  · 页头新增"全部重新下载"按钮（重下全部失败任务）；
  · 失败/已取消的卡片不再消失，停留在列表中等待重下；
    只有成功（done）的卡片自动移除。
"""

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from i18n import tr
from ui_history import open_location
from manager import TaskManager

FINAL = {"done", "failed", "canceled"}
REDL_OK = {"failed", "canceled"}     # 允许"重新下载"的状态

STATUS_COLOR = {"queued": "#b8860b", "running": "#1565c0",
                "paused": "#6a4c93", "done": "#2e7d32",
                "failed": "#c62828", "canceled": "#757575"}


def status_text(status: str) -> str:
    s = tr("st." + str(status))
    return s if s != "st." + str(status) else str(status)


def proxy_tag(info: dict, cfg: dict) -> str:
    proxy = info.get("proxy") or ""
    if not proxy:
        return ""
    pool = list(cfg.get("proxy_pool") or [])
    try:
        return f" [P{pool.index(proxy) + 1}]"
    except ValueError:
        return " [P?]"


class TaskCard(QFrame):

    def __init__(self, info: dict, cfg: dict, manager: TaskManager,
                 parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.tid = info["id"]
        self._cfg = cfg
        self._manager = manager
        self._info = info

        lay = QGridLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setHorizontalSpacing(8)

        self.lab_title = QLabel(info.get("title", ""))
        f = self.lab_title.font()
        f.setBold(True)
        self.lab_title.setFont(f)
        self.lab_title.setToolTip(info.get("url", ""))
        lay.addWidget(self.lab_title, 0, 0)

        btns = QWidget()
        h = QHBoxLayout(btns)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        self.btn_pause = QPushButton()
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_redl = QPushButton(tr("btn.redownload"))
        self.btn_redl.clicked.connect(
            lambda: self._manager.redownload(self.tid))
        self.btn_cancel = QPushButton(tr("btn.cancel"))
        self.btn_cancel.clicked.connect(
            lambda: self._manager.stop(self.tid))
        self.btn_open = QPushButton(tr("btn.open_folder"))
        self.btn_open.clicked.connect(self._open)
        for b in (self.btn_pause, self.btn_redl, self.btn_cancel,
                  self.btn_open):
            h.addWidget(b)
        h.addStretch(1)
        lay.addWidget(btns, 0, 1)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        lay.addWidget(self.bar, 1, 0, 1, 2)

        self.lab_info = QLabel()
        self.lab_info.setStyleSheet("color:#444;")
        lay.addWidget(self.lab_info, 2, 0, 1, 2)

        self.lab_err = QLabel("")
        self.lab_err.setStyleSheet("color:#c62828;")
        self.lab_err.setWordWrap(True)
        lay.addWidget(self.lab_err, 3, 0, 1, 2)

        self.update_state(info)

    def _toggle_pause(self):
        if self._info.get("status") == "paused":
            self._manager.resume(self.tid)
        else:
            self._manager.pause(self.tid)

    def _open(self):
        open_location(self._info.get("file_path", ""),
                      self._cfg.get("download_dir", ""))

    def update_state(self, info: dict):
        self._info = info
        status = info.get("status", "")
        self.lab_title.setText(info.get("title", ""))
        self.bar.setValue(int(info.get("percent", 0) or 0))

        parts = [status_text(status),
                 f"{info.get('percent', 0) or 0:.1f}%"]
        if info.get("speed"):
            parts.append(info["speed"])
        if info.get("eta"):
            parts.append(tr("task.remain", eta=info["eta"]))
        parts.append(proxy_tag(info, self._cfg))
        self.lab_info.setText("  ·  ".join(parts))
        self.lab_info.setStyleSheet(
            f"color:{STATUS_COLOR.get(status, '#555555')};")

        err = info.get("error") or ""
        if status == "failed" and err:
            self.lab_err.setText(err.splitlines()[-1][:160])
            self.lab_err.setToolTip(err)
        else:
            self.lab_err.setText("")
            self.lab_err.setToolTip("")

        # ---- 按钮状态 ----
        if status == "paused":
            self.btn_pause.setText(tr("btn.resume"))
            self.btn_pause.setEnabled(True)
        elif status == "running":
            self.btn_pause.setText(tr("btn.pause"))
            self.btn_pause.setEnabled(True)
        else:
            self.btn_pause.setEnabled(False)
        self.btn_redl.setEnabled(status in REDL_OK)
        self.btn_cancel.setEnabled(status not in FINAL)


class TasksPage(QWidget):

    def __init__(self, manager: TaskManager, cfg: dict, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.cfg = cfg
        self._cards = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 6)
        root.setSpacing(6)

        # ---- 页头：标题 + 全部重新下载 ----
        head = QWidget()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(0, 0, 0, 0)
        cap = QLabel(tr("tasks.title"))
        cap.setStyleSheet("font-weight:bold;")
        hl.addWidget(cap)
        hl.addStretch(1)
        self.btn_redl_all = QPushButton(tr("btn.redownload_all"))
        self.btn_redl_all.clicked.connect(self._redownload_all)
        hl.addWidget(self.btn_redl_all)
        root.addWidget(head)

        self.cards_host = QWidget()
        self.cards_lay = QVBoxLayout(self.cards_host)
        self.cards_lay.setContentsMargins(0, 0, 0, 0)
        self.cards_lay.setSpacing(6)
        self.lab_empty = QLabel(tr("tasks.empty"))
        self.lab_empty.setAlignment(Qt.AlignCenter)
        self.lab_empty.setStyleSheet("color:#999;")
        self.cards_lay.addWidget(self.lab_empty)
        self.cards_lay.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.cards_host)
        scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(scroll, 1)

        self.manager.sig_task_added.connect(self._on_added)
        self.manager.sig_task_updated.connect(self._on_updated)
        self.manager.sig_task_finished.connect(self._on_finished)

    def _redownload_all(self):
        self.manager.redownload_all_failed()

    def _on_added(self, info: dict):
        card = TaskCard(info, self.cfg, self.manager)
        self._cards[info["id"]] = card
        self.cards_lay.insertWidget(self.cards_lay.count() - 1, card)
        self.lab_empty.hide()

    def _on_updated(self, tid: str, snap: dict):
        card = self._cards.get(tid)
        if card:
            card.update_state(snap)

    def _on_finished(self, record: dict):
        # 只有成功（done）的卡片移除；
        # 失败/已取消的卡片保留，供"重新下载"。
        if record.get("status") == "done":
            card = self._cards.pop(record.get("id"), None)
            if card:
                card.setParent(None)
                card.deleteLater()
            if not self._cards:
                self.lab_empty.show()


if __name__ == "__main__":
    import i18n
    import config
    cfg = config.load_config()
    i18n.init(cfg.get("language", "auto"))
    app = QApplication(sys.argv)
    mgr = TaskManager(cfg)
    page = TasksPage(mgr, cfg)
    page.resize(680, 480)
    page.show()
    sys.exit(app.exec())