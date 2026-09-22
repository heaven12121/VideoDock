"""ui_history.py — 下载历史页

数据源：信息文件 history 字段（新记录在上）。
本次修正 open_location：path 为空时绝不再回退到“当前目录”
（旧版 Path("") == Path(".") 会被 is_dir() 判真，导致打开
程序所在文件夹）；文件已不在但父文件夹存在 → 打开父文件夹；
否则回退默认下载目录。
"""

import csv
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFileDialog,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

import config
from builder import preview_command
from i18n import tr

STATUS_COLOR = {"queued": "#b8860b", "running": "#1565c0",
                "paused": "#6a4c93", "done": "#2e7d32",
                "failed": "#c62828", "canceled": "#757575"}


def status_text(status: str) -> str:
    s = tr("st." + str(status))
    return s if s != "st." + str(status) else str(status)


def open_location(path: str, fallback_dir: str = ""):
    """打开文件所在文件夹。任何情况下都不会打开“当前目录”。"""
    path = (path or "").strip()
    fallback = (fallback_dir or "").strip()
    try:
        if os.name == "nt":
            p = Path(path) if path else None
            if p is not None and p.is_file():
                os.startfile(str(p.parent))
                return
            if p is not None and p.is_dir():
                os.startfile(str(p))
                return
            if p is not None:
                parent = p.parent
                if parent.is_dir() and str(parent) not in (".", ""):
                    os.startfile(str(parent))
                    return
            if fallback:
                d = Path(fallback)
                d.mkdir(parents=True, exist_ok=True)
                os.startfile(str(d))
        else:
            if path:
                p = Path(path)
                target = p if p.is_dir() else p.parent
                if Path(target).exists():
                    subprocess.Popen(["xdg-open", str(target)])
                    return
            if fallback:
                subprocess.Popen(["xdg-open", fallback])
    except OSError:
        pass


def file_size_text(path: str) -> str:
    try:
        n = Path(path).stat().st_size
    except OSError:
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return ""


class HistoryPage(QWidget):
    """下载历史页。管理器可为 None（独立预览模式）。"""

    def __init__(self, manager, cfg: dict, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.cfg = cfg
        self._view = []

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 6)
        root.setSpacing(6)

        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(0, 0, 0, 0)
        self.cb_filter = QComboBox()
        for text, data in [(tr("hist.f_all"), ""),
                           (tr("hist.f_done"), "done"),
                           (tr("hist.f_failed"), "failed"),
                           (tr("hist.f_canceled"), "canceled")]:
            self.cb_filter.addItem(text, data)
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText(tr("hist.search_ph"))
        self.btn_clear = QPushButton(tr("btn.clear"))
        self.btn_export = QPushButton(tr("btn.export_csv"))
        bl.addWidget(self.cb_filter)
        bl.addWidget(self.ed_search, 1)
        bl.addWidget(self.btn_clear)
        bl.addWidget(self.btn_export)
        root.addWidget(bar)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            [tr("hist.h_time"), tr("hist.h_title"),
             tr("hist.h_status"), tr("hist.h_size"),
             tr("hist.h_path")])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        hd = self.table.horizontalHeader()
        hd.setSectionResizeMode(0, QHeaderView.Fixed)
        hd.setSectionResizeMode(1, QHeaderView.Stretch)
        hd.setSectionResizeMode(2, QHeaderView.Fixed)
        hd.setSectionResizeMode(3, QHeaderView.Fixed)
        hd.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 140)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 80)
        self.table.verticalHeader().setVisible(False)
        root.addWidget(self.table, 1)

        self.ed_search.textChanged.connect(self._refresh)
        self.cb_filter.currentIndexChanged.connect(self._refresh)
        self.btn_clear.clicked.connect(self._clear)
        self.btn_export.clicked.connect(self._export_csv)
        self.table.customContextMenuRequested.connect(self._menu)
        self.table.doubleClicked.connect(self._open_selected)

        # 任务完结（写入历史）→ 立即刷新表格
        if self.manager is not None:
            self.manager.sig_task_finished.connect(
                lambda _rec: self._refresh())

        self._refresh()

    # ---------------- 渲染 ----------------
    def _refresh(self):
        kw = self.ed_search.text().strip().lower()
        st = self.cb_filter.currentData()
        rows = [rec for rec in reversed(self.cfg.get("history", []))
                if (not st or rec.get("status") == st)
                and (not kw or kw in (rec.get("title", "")
                                      + rec.get("url", "")).lower())]
        self._view = rows
        self.table.setRowCount(max(len(rows), 1))
        if not rows:
            self.table.setItem(0, 0, QTableWidgetItem(tr("hist.empty")))
            return
        for r, rec in enumerate(rows):
            cells = [rec.get("start_time", ""), rec.get("title", ""),
                     status_text(rec.get("status", "")),
                     file_size_text(rec.get("file_path", "")),
                     rec.get("file_path", "")]
            for c, text in enumerate(cells):
                self.table.setItem(r, c, QTableWidgetItem(text))
            it = self.table.item(r, 2)
            if it:
                color = QColor(STATUS_COLOR.get(rec.get("status", ""),
                                                "#555555"))
                it.setForeground(QBrush(color))

    def refresh_from_cfg(self):
        self._refresh()

    # ---------------- 动作 ----------------
    def _sel_rec(self):
        r = self.table.currentRow()
        return self._view[r] if 0 <= r < len(self._view) else None

    def _open_selected(self, *_):
        rec = self._sel_rec()
        if rec:
            open_location(rec.get("file_path", ""),
                          self.cfg.get("download_dir", ""))

    def _del_record(self, rec):
        if rec in self.cfg.get("history", []):
            self.cfg["history"].remove(rec)
            config.save_config(self.cfg)
            self._refresh()

    def _clear(self):
        ans = QMessageBox.question(
            self, tr("msg.confirm"), tr("hist.confirm_clear"))
        if ans == QMessageBox.StandardButton.Yes:
            self.cfg["history"] = []
            config.save_config(self.cfg)
            self._refresh()

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dlg.export_hist"), "yt-dlp-history.csv",
            "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow([tr("hist.h_time"), "end_time",
                        tr("hist.h_title"), tr("hist.h_status"),
                        tr("hist.h_path"), "url", "command", "error"])
            for rec in self.cfg.get("history", []):
                w.writerow([rec.get("start_time", ""),
                            rec.get("end_time", ""),
                            rec.get("title", ""),
                            rec.get("status", ""),
                            rec.get("file_path", ""),
                            rec.get("url", ""),
                            preview_command(rec.get("command", [])),
                            rec.get("error", "")])

    def _menu(self, pos):
        rec = self._sel_rec()
        if rec is None:
            return
        menu = QMenu(self)
        if self.manager is not None and rec.get("command"):
            menu.addAction(
                tr("btn.retry"),
                lambda: self.manager.retry(rec.get("command", []),
                                           rec.get("url", ""),
                                           rec.get("title", "")))
        menu.addAction(tr("hist.open_menu"), self._open_selected)
        menu.addAction(
            tr("hist.copy_menu"),
            lambda: QApplication.clipboard().setText(
                rec.get("url", "")))
        menu.addSeparator()
        menu.addAction(tr("hist.del_menu"),
                       lambda: self._del_record(rec))
        menu.exec(self.table.viewport().mapToGlobal(pos))


if __name__ == "__main__":
    import i18n
    cfg = config.load_config()
    i18n.init(cfg.get("language", "auto"))
    app = QApplication(sys.argv)
    page = HistoryPage(None, cfg)
    page.resize(820, 520)
    page.show()
    sys.exit(app.exec())