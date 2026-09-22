"""ui_main.py — VideoDock 主窗口

本次改动：右侧按钮列中“开始下载”主按钮增强——
固定高度 42px（默认约 28px 的 1.5 倍）、字体 12pt、加粗。
其余与上一版一致（纵向按钮列、总速度显示、完成音效/弹窗接线）。
"""

import dataclasses
import os
import re
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QRadioButton, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

import config
from builder import TaskSpec, build_argv, preview_command
from i18n import tr
from manager import TaskManager
from ui_advanced import AdvancedPanel
from ui_history import HistoryPage
from ui_ip import IpPage
from ui_settings import SettingsPage
from ui_tasks import TasksPage
from widgets import HelpLabel, pick_dir

try:
    from ui_toast import show_done_toast
except ImportError:                                     # pragma: no cover
    def show_done_toast(*a, **k):
        pass


def play_sound(path: str):
    if os.name != "nt" or not path or not Path(path).is_file():
        return
    try:
        import winsound
        winsound.PlaySound(path,
                           winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception:
        pass


# ---------------- 总速度聚合 ----------------
_UNITS = {"B": 1, "KIB": 1024, "MIB": 1024 ** 2, "GIB": 1024 ** 3,
          "TIB": 1024 ** 4, "PIB": 1024 ** 4 * 1024}
_SPEED_RE = re.compile(r"([\d.]+)\s*([KMGTP]?I?B)/s", re.I)


def parse_speed(text: str) -> float:
    """" 5.00MiB/s" → 字节/秒；无法解析返回 0。"""
    m = _SPEED_RE.search(text or "")
    if not m:
        return 0.0
    unit = m.group(2).upper()
    unit = re.sub(r"([KMGTP])B$", r"\1IB", unit)
    try:
        return float(m.group(1)) * _UNITS.get(unit, 0)
    except ValueError:
        return 0.0


def fmt_speed(bps: float) -> str:
    if bps <= 0:
        return ""
    for name, factor in (("B/s", 1), ("KiB/s", 1024),
                         ("MiB/s", 1024 ** 2), ("GiB/s", 1024 ** 3)):
        if bps < 1024 * factor or name == "GiB/s":
            return f"{bps / factor:.1f} {name}"
    return ""


class UrlEdit(QPlainTextEdit):
    """多行链接框：每行一个链接；回车提交，Shift+回车换行。"""

    submitted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setPlaceholderText(tr("url.placeholder"))
        self.setFixedHeight(96)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            if e.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(e)
            else:
                self.submitted.emit()
            return
        super().keyPressEvent(e)

    def dragEnterEvent(self, e):
        md = e.mimeData()
        if md.hasUrls() or md.hasText():
            e.acceptProposedAction()

    def dropEvent(self, e):
        md = e.mimeData()
        if md.hasUrls():
            urls = [u.toString() for u in md.urls()]
        else:
            urls = [ln.strip() for ln in md.text().splitlines()
                    if ln.strip()]
        if urls:
            cur = self.toPlainText().strip()
            self.setPlainText(
                (cur + "\n" if cur else "") + "\n".join(urls))
        e.acceptProposedAction()


class SimplePanel(QWidget):
    """简易模式：类型/画质/可选项/输出目录（链接框在主窗口顶部）。"""

    sig_preview = Signal()

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        grid = QGridLayout(self)
        grid.setContentsMargins(24, 16, 24, 8)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(10)
        grid.setColumnMinimumWidth(1, 320)
        grid.setColumnStretch(1, 1)

        def row(idx, name, widget, help_key):
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(lbl, idx, 0)
            grid.addWidget(widget, idx, 1)
            grid.addWidget(HelpLabel(help_key), idx, 2)

        type_box = QWidget()
        tl = QHBoxLayout(type_box)
        tl.setContentsMargins(0, 0, 0, 0)
        self.rb_video = QRadioButton(tr("simple.video"))
        self.rb_audio = QRadioButton(tr("simple.audio"))
        self.rb_video.setChecked(True)
        tl.addWidget(self.rb_video)
        tl.addWidget(self.rb_audio)
        tl.addStretch(1)
        row(0, tr("simple.type"), type_box, "help.quality")

        self.cb_quality = QComboBox()
        for text, data in [(tr("quality.best"), "best"), ("1080P", "1080"),
                           ("720P", "720"), ("480P", "480"),
                           (tr("quality.custom_hint"), "custom")]:
            self.cb_quality.addItem(text, data)
        row(1, tr("simple.quality"), self.cb_quality, "help.quality")

        self.cb_audio_fmt = QComboBox()
        self.cb_audio_fmt.addItems(["mp3", "m4a", "opus", "flac"])
        self.cb_audio_fmt.setEnabled(False)
        row(2, tr("simple.audio_format"), self.cb_audio_fmt,
            "help.audio_fmt")

        opt_box = QWidget()
        ol = QHBoxLayout(opt_box)
        ol.setContentsMargins(0, 0, 0, 0)
        self.chk_subs = QCheckBox(tr("simple.chk_subs"))
        self.chk_thumb = QCheckBox(tr("simple.chk_thumb"))
        ol.addWidget(self.chk_subs)
        ol.addWidget(HelpLabel("help.subs"))
        ol.addSpacing(18)
        ol.addWidget(self.chk_thumb)
        ol.addWidget(HelpLabel("help.thumb"))
        ol.addStretch(1)
        row(3, tr("simple.options"), opt_box, "help.subs")

        dir_box = QWidget()
        dl = QHBoxLayout(dir_box)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(6)
        self.ed_dir = QLineEdit(self.cfg.get("download_dir", ""))
        btn = QPushButton(tr("btn.browse"))
        btn.clicked.connect(self._browse_dir)
        dl.addWidget(self.ed_dir, 1)
        dl.addWidget(btn)
        row(4, tr("simple.outdir"), dir_box, "help.outdir")

        btn_row = QWidget()
        bl = QHBoxLayout(btn_row)
        bl.setContentsMargins(0, 6, 0, 0)
        bl.addStretch(1)
        self.btn_preview = QPushButton(tr("simple.preview"))
        bl.addWidget(self.btn_preview)
        grid.addWidget(btn_row, 5, 1)

        self.rb_video.toggled.connect(self._on_video_audio)
        self.btn_preview.clicked.connect(self.sig_preview.emit)

    def _on_video_audio(self, on):
        self.cb_quality.setEnabled(on)
        self.cb_audio_fmt.setEnabled(not on)

    def _browse_dir(self):
        p = pick_dir(self, tr("dlg.pick_savedir"))
        if p:
            self.ed_dir.setText(p)

    def collect(self, spec: TaskSpec):
        spec.quality = ("audio" if self.rb_audio.isChecked()
                        else self.cb_quality.currentData())
        spec.audio_format = self.cb_audio_fmt.currentText()
        spec.write_subs = self.chk_subs.isChecked()
        spec.embed_thumb = self.chk_thumb.isChecked()
        spec.download_dir = self.ed_dir.text().strip()

    def apply(self, spec: TaskSpec):
        if spec.quality == "audio":
            self.rb_audio.setChecked(True)
        else:
            self.rb_video.setChecked(True)
            idx = self.cb_quality.findData(spec.quality)
            if idx >= 0:
                self.cb_quality.setCurrentIndex(idx)
        self.cb_audio_fmt.setCurrentText(spec.audio_format)
        self.chk_subs.setChecked(spec.write_subs)
        self.chk_thumb.setChecked(spec.embed_thumb)
        if spec.download_dir:
            self.ed_dir.setText(spec.download_dir)


class MainWindow(QWidget):

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.spec = TaskSpec(url="")
        self._last_dir = cfg.get("download_dir", "")
        self._done_buffer = 0
        self._done_paths = []
        self.setWindowTitle(tr("app.title"))
        self.resize(900, 700)
        self.setMinimumSize(780, 620)

        self.manager = TaskManager(self.cfg)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 6)
        root.setSpacing(6)

        # ========== 链接框 + 右侧纵向按钮列 ==========
        top = QWidget()
        tl = QHBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(6)
        self.url_edit = UrlEdit()
        tl.addWidget(self.url_edit, 1)

        # ---- 开始下载：主按钮（1.5 倍高、12pt、加粗） ----
        self.btn_start = QPushButton(tr("btn.start"))
        bf = QFont()
        bf.setPointSize(12)
        bf.setBold(True)
        self.btn_start.setFont(bf)
        self.btn_start.setFixedHeight(42)
        self.btn_start.setFixedWidth(110)
        self.btn_start.setStyleSheet(
            "QPushButton { background:#2e7d32; color:white;"
            " padding:4px 10px; border-radius:4px; }"
            "QPushButton:hover { background:#1b5e20; }")

        self.btn_pause_all = QPushButton(tr("btn.pause_all"))
        self.btn_pause_all.setFixedWidth(110)
        self.btn_copy = QPushButton(tr("btn.copy"))
        self.btn_copy.setFixedWidth(110)
        self.btn_copy.setToolTip(tr("help.copy_cmd"))

        btn_col = QWidget()
        bv = QVBoxLayout(btn_col)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.setSpacing(4)
        bv.addWidget(self.btn_start)
        bv.addWidget(self.btn_pause_all)
        bv.addWidget(self.btn_copy)
        bv.addStretch(1)
        tl.addWidget(btn_col)
        root.addWidget(top)

        # ========== 五个标签页 ==========
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self.page_new = QWidget()
        pl = QVBoxLayout(self.page_new)
        pl.setContentsMargins(0, 4, 0, 0)
        mode_row = QWidget()
        ml = QHBoxLayout(mode_row)
        ml.setContentsMargins(8, 0, 8, 0)
        self.btn_simple = QPushButton(tr("mode.simple"))
        self.btn_advanced = QPushButton(tr("mode.advanced"))
        for b in (self.btn_simple, self.btn_advanced):
            b.setCheckable(True)
            b.setFixedWidth(88)
        self.btn_simple.setChecked(True)
        ml.addWidget(self.btn_simple)
        ml.addWidget(self.btn_advanced)
        ml.addStretch(1)
        ml.addWidget(HelpLabel("help.url"))
        pl.addWidget(mode_row)

        self.stack = QStackedWidget()
        self.simple_panel = SimplePanel(self.cfg)
        self.advanced_panel = AdvancedPanel(self.cfg)
        self.stack.addWidget(self.simple_panel)
        self.stack.addWidget(self.advanced_panel)
        pl.addWidget(self.stack, 1)
        self.tabs.addTab(self.page_new, tr("tab.new"))

        self.tasks_page = TasksPage(self.manager, self.cfg)
        self.tabs.addTab(self.tasks_page, tr("tab.tasks"))
        self.history_page = HistoryPage(self.manager, self.cfg)
        self.tabs.addTab(self.history_page, tr("tab.history"))
        self.settings_page = SettingsPage(self.cfg)
        self.tabs.addTab(self.settings_page, tr("tab.settings"))
        self.ip_page = IpPage(self.cfg)
        self.tabs.addTab(self.ip_page, tr("tab.ip"))

        # ========== 底栏：帮助 + 总速度 + 就绪徽标 + 排队数 ==========
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        root.addWidget(line)

        bottom = QWidget()
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(4, 2, 4, 2)
        self.help_bar = QLabel(tr("helpbar.default"))
        self.help_bar.setWordWrap(True)
        self.help_bar.setMinimumHeight(36)
        self.help_bar.setStyleSheet("color:#555;")
        bl.addWidget(self.help_bar, 1)
        self.lab_speed = QLabel("")
        self.lab_speed.setStyleSheet(
            "color:#1565c0; font-weight:bold;")
        bl.addWidget(self.lab_speed)
        self.lab_badge = QLabel()
        self.lab_badge.setCursor(Qt.PointingHandCursor)
        self.lab_badge.setToolTip(tr("ready.title"))
        bl.addWidget(self.lab_badge)
        self.lab_queue = QLabel("")
        self.lab_queue.setStyleSheet("color:#777;")
        bl.addWidget(self.lab_queue)
        root.addWidget(bottom)

        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.setInterval(1200)
        self._toast_timer.timeout.connect(self._flush_toast)

        # ========== 信号连接 ==========
        self.btn_simple.clicked.connect(lambda: self._switch_mode(0))
        self.btn_advanced.clicked.connect(lambda: self._switch_mode(1))
        self.btn_start.clicked.connect(self._start_download)
        self.btn_copy.clicked.connect(self._copy_command)
        self.btn_pause_all.clicked.connect(self._toggle_pause_all)
        self.simple_panel.sig_preview.connect(
            lambda: self._switch_mode(1))
        self.url_edit.submitted.connect(self._start_download)
        self.manager.sig_queue_changed.connect(self._on_queue_changed)
        self.manager.sig_task_finished.connect(self._on_task_finished)
        self.manager.sig_task_finished.connect(self._update_speed)
        self.manager.sig_task_updated.connect(self._update_speed)
        self.settings_page.sig_readiness.connect(self._on_readiness)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        for hl in self.findChildren(HelpLabel):
            hl.helpRequested.connect(self.help_bar.setText)

        sc = QShortcut(QKeySequence("Ctrl+Return"), self)
        sc.activated.connect(self._start_download)
        sc2 = QShortcut(QKeySequence("Ctrl+,"), self)
        sc2.activated.connect(
            lambda: self.tabs.setCurrentWidget(self.settings_page))

        flags = getattr(self.settings_page, "_flags", {})
        self._on_readiness(sum(1 for v in flags.values() if v))
        self._switch_mode(0)

    # ---------------- 模式切换 ----------------
    def _switch_mode(self, index: int):
        cur = self.stack.currentWidget()
        if cur is self.advanced_panel:
            self.advanced_panel.collect(self.spec)
        elif cur is self.simple_panel:
            self.simple_panel.collect(self.spec)

        if index == 1:
            self.advanced_panel.apply(self.spec)
        else:
            self.simple_panel.apply(self.spec)

        self.stack.setCurrentIndex(index)
        self.btn_simple.setChecked(index == 0)
        self.btn_advanced.setChecked(index == 1)

    # ---------------- 链接与提交 ----------------
    def _urls(self):
        return [ln.strip() for ln in
                self.url_edit.toPlainText().splitlines()
                if ln.strip()]

    def _collect_spec(self) -> TaskSpec:
        cur = self.stack.currentWidget()
        if cur is self.advanced_panel:
            self.advanced_panel.collect(self.spec)
        else:
            self.simple_panel.collect(self.spec)
        urls = self._urls()
        self.spec.url = urls[0] if urls else ""
        return self.spec

    def _not_ready_items(self):
        flags = getattr(self.settings_page, "_flags", {})
        items = []
        if not flags.get("ytdlp", config.ytdlp_ok(self.cfg)):
            items.append(tr("ready.ytdlp") + " — "
                         + tr("ready.ytdlp.nofile"))
        if not flags.get("ffmpeg", config.ffmpeg_ok(self.cfg)):
            items.append(tr("ready.ffmpeg") + " — "
                         + tr("ready.ffmpeg.bad"))
        if not flags.get("dir", True):
            items.append(tr("ready.dir"))
        if not flags.get("cookie", True):
            items.append(tr("ready.cookie"))
        return items

    def _start_download(self, checked=False):
        urls = self._urls()
        if not urls:
            QMessageBox.warning(self, tr("msg.confirm"),
                                tr("msg.no_url"))
            return
        for u in urls:
            if "://" not in u:
                QMessageBox.warning(self, tr("msg.confirm"),
                                    tr("msg.bad_url") + "\n" + u[:80])
                return
        not_ready = self._not_ready_items()
        if not_ready:
            box = QMessageBox(self)
            box.setWindowTitle(tr("msg.not_ready_title"))
            box.setText(tr("msg.not_ready_body",
                           items="\n".join("· " + i
                                           for i in not_ready)))
            go = box.addButton(tr("btn.goto_settings"),
                               QMessageBox.ActionRole)
            still = box.addButton(tr("btn.still_download"),
                                  QMessageBox.ActionRole)
            box.addButton(QMessageBox.Cancel)
            box.exec()
            clicked = box.clickedButton()
            if clicked is go:
                self.tabs.setCurrentWidget(self.settings_page)
                return
            if clicked is not still:
                return
        spec = self._collect_spec()
        if spec.quality != "audio" and not config.ffmpeg_ok(self.cfg):
            self.help_bar.setText(tr("msg.warn_no_ffmpeg"))
        for u in urls:
            self.manager.submit(dataclasses.replace(spec, url=u))
        self.help_bar.setText(tr("msg.queued", n=len(urls)))
        self.url_edit.clear()
        self.tabs.setCurrentWidget(self.tasks_page)

    def _copy_command(self):
        self._collect_spec()
        if not self.spec.url:
            QMessageBox.warning(self, tr("msg.confirm"),
                                tr("msg.no_url"))
            return
        argv = build_argv(self.spec, self.cfg)
        QApplication.clipboard().setText(preview_command(argv))
        self.help_bar.setText(tr("msg.copied"))

    def _toggle_pause_all(self):
        on = not self.manager.is_global_paused()
        self.manager.set_global_paused(on)
        self.btn_pause_all.setText(
            tr("btn.resume_all" if on else "btn.pause_all"))

    # ---------------- 总速度 ----------------
    def _update_speed(self, *args):
        total = 0.0
        try:
            for t in self.manager.all_tasks():
                if t.get("status") == "running":
                    total += parse_speed(t.get("speed", ""))
        except Exception:
            total = 0.0
        self.lab_speed.setText(
            ("⇣ " + fmt_speed(total)) if total > 0 else "")

    # ---------------- 完成反馈 ----------------
    def _on_task_finished(self, record: dict):
        if record.get("status") != "done":
            return
        if self.cfg.get("sound_enabled"):
            play_sound(self._sound_path())
        if self.cfg.get("popup_enabled"):
            self._done_buffer += 1
            if record.get("file_path"):
                self._done_paths.append(record["file_path"])
            self._toast_timer.start()

    def _flush_toast(self):
        n, paths = self._done_buffer, self._done_paths
        self._done_buffer, self._done_paths = 0, []
        if n <= 0:
            return
        show_done_toast(self, n, paths,
                        self.cfg.get("download_dir", ""))

    @staticmethod
    def _sound_path() -> str:
        base = Path(sys.executable).resolve().parent \
            if getattr(sys, "frozen", False) \
            else Path(__file__).resolve().parent
        return str(base / "VDsound.wav")

    # ---------------- 徽标 / 状态 / 同步 ----------------
    def _on_readiness(self, n: int):
        n = max(0, min(4, int(n)))
        ok = n == 4
        self.lab_badge.setText(
            tr("badge.ok" if ok else "badge.bad", n=n))
        self.lab_badge.setStyleSheet(
            "color:#2e7d32; font-weight:bold;"
            if ok else "color:#b8860b; font-weight:bold;")
        self.lab_badge.mousePressEvent = lambda e: \
            self.tabs.setCurrentWidget(self.settings_page)

    def _on_queue_changed(self, n: int):
        self.lab_queue.setText(tr("queue.left", n=n) if n else "")

    def _on_tab_changed(self, idx: int):
        if self.tabs.widget(idx) is self.page_new:
            d = self.cfg.get("download_dir", "")
            if self.simple_panel.ed_dir.text().strip() in (
                    "", self._last_dir):
                self.simple_panel.ed_dir.setText(d)
            ap = getattr(self.advanced_panel, "ed_dir", None)
            if ap is not None and ap.text().strip() in (
                    "", self._last_dir):
                ap.setText(d)
            self._last_dir = d

    def closeEvent(self, e):
        active = sum(1 for t in self.manager.all_tasks()
                     if t["status"] in ("queued", "running", "paused"))
        if active:
            ret = QMessageBox.question(
                self, tr("msg.exit_title"),
                tr("msg.exit_body", n=active),
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if ret != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
        self.manager.shutdown()
        config.save_config(self.cfg)
        super().closeEvent(e)


if __name__ == "__main__":
    import i18n
    cfg = config.load_config()
    i18n.init(cfg.get("language", "auto"))
    app = QApplication(sys.argv)
    win = MainWindow(cfg)
    win.show()
    sys.exit(app.exec())