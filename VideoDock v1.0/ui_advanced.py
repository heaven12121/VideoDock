"""ui_advanced.py — 高级模式面板（tr 化定稿）

链接输入已上移到主窗口顶部共用，本面板只负责参数。
共有字段写入共享 TaskSpec；高级独有字段保留在控件中不丢失。
所有可见文字经 tr() 取词（键位见 lang/zh.json）。
"""

import shlex
import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
    QVBoxLayout, QWidget,
)

from builder import FORMAT_MAP, TaskSpec, build_argv, preview_command
from i18n import tr
from ui_settings import BROWSERS
from widgets import CollapsibleSection, FieldRow, pick_file


def split_args(text: str) -> list:
    """附加参数文本 → argv 片段。posix=False 保留反斜杠。"""
    text = text.strip()
    if not text:
        return []
    try:
        parts = shlex.split(text, posix=False)
    except ValueError:
        parts = text.split()
    return [p[1:-1] if len(p) > 1 and p[0] == p[-1]
            and p[0] in "\"'" else p for p in parts]


class AdvancedPanel(QWidget):

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._live = []
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 4)
        root.setSpacing(6)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(4)
        self._build_output(bl)
        self._build_network(bl)
        self._build_select(bl)
        self._build_subs(bl)
        self._build_post(bl)
        self._build_debug(bl)
        self._build_extra(bl)
        bl.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(scroll, 1)

        tip = QLabel(tr("adv.preview_tip"))
        tip.setStyleSheet("color:#777;")
        root.addWidget(tip)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(96)
        self.preview.setFont(QFont("Consolas", 9))
        self.preview.setLineWrapMode(QPlainTextEdit.NoWrap)
        root.addWidget(self.preview)

        self._wire_live()
        self._on_format_change()

    # ================= 取词辅助 =================
    @staticmethod
    def _containers():
        return [tr("merge.default"), "mp4", "mkv", "webm", "avi"]

    @staticmethod
    def _presets():
        return [(tr("quality.best"), "best"), ("1080P", "1080"),
                ("720P", "720"), ("480P", "480"),
                (tr("simple.audio"), "audio"),
                (tr("quality.custom"), "custom")]

    # ================= 分组构建 =================
    def _build_output(self, lay):
        sec = CollapsibleSection(tr("sec.output"), expanded=True)
        self.ed_dir = QLineEdit(self.cfg.get("download_dir", ""))
        self._live.append(self.ed_dir)
        sec.add_row(tr("row.dir"), self.ed_dir, "help.P")

        self.ed_tmpl = QLineEdit(self.cfg.get("output_template", ""))
        self._live.append(self.ed_tmpl)
        sec.add_row(tr("row.tmpl"), self.ed_tmpl, "help.o")

        self.cb_format = QComboBox()
        for text, data in self._presets():
            self.cb_format.addItem(text, data)
        self._live.append(self.cb_format)
        sec.add_row(tr("row.format"), self.cb_format, "help.f")

        self.ed_format = QLineEdit()
        self.ed_format.setPlaceholderText(tr("ph.fmt_sel"))
        self.ed_format.setFont(QFont("Consolas", 9))
        self.ed_format.setEnabled(False)
        self._live.append(self.ed_format)
        sec.add_row(tr("row.fmt_sel"), self.ed_format, "help.f")

        self.cb_merge = QComboBox()
        self.cb_merge.addItems(self._containers())
        self._live.append(self.cb_merge)
        sec.add_row(tr("row.merge"), self.cb_merge, "help.merge")
        self.cb_format.currentIndexChanged.connect(
            self._on_format_change)
        lay.addWidget(sec)

    def _build_network(self, lay):
        sec = CollapsibleSection(tr("sec.network"))
        self.ed_proxy = QLineEdit()
        self.ed_proxy.setPlaceholderText(tr("ph.proxy"))
        self._live.append(self.ed_proxy)
        sec.add_row(tr("row.proxy"), self.ed_proxy, "help.proxy")

        self.cb_cookies = QComboBox()
        self.cb_cookies.addItems(BROWSERS)
        self._live.append(self.cb_cookies)
        sec.add_row(tr("row.cookies"), self.cb_cookies, "help.cookies")

        self.ed_rate = QLineEdit()
        self.ed_rate.setPlaceholderText(tr("ph.rate"))
        self._live.append(self.ed_rate)
        sec.add_row(tr("row.rate"), self.ed_rate, "help.r")

        self.sp_retries = QSpinBox()
        self.sp_retries.setRange(0, 50)
        self.sp_retries.setValue(10)
        self._live.append(self.sp_retries)
        sec.add_row(tr("row.retries"), self.sp_retries, "help.retries")

        self.sp_timeout = QSpinBox()
        self.sp_timeout.setRange(0, 600)
        self.sp_timeout.setSuffix(" s")
        self.sp_timeout.setSpecialValueText("default")
        self._live.append(self.sp_timeout)
        sec.add_row(tr("row.timeout"), self.sp_timeout,
                    "help.socket_timeout")
        lay.addWidget(sec)

    def _build_select(self, lay):
        sec = CollapsibleSection(tr("sec.select"))
        self.chk_playlist = QCheckBox(tr("chk.playlist_dl"))
        self._live.append(self.chk_playlist)
        sec.add_row(tr("row.playlist"), self.chk_playlist,
                    "help.no_playlist")

        self.ed_pl_items = QLineEdit()
        self.ed_pl_items.setPlaceholderText(tr("ph.pl_items"))
        self._live.append(self.ed_pl_items)
        sec.add_row(tr("row.pl_items"), self.ed_pl_items,
                    "help.playlist_items")

        self.ed_filter = QLineEdit()
        self.ed_filter.setPlaceholderText(tr("ph.filter"))
        self._live.append(self.ed_filter)
        sec.add_row(tr("row.filter"), self.ed_filter,
                    "help.match_filter")

        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        self.ed_archive = QLineEdit()
        self.ed_archive.setPlaceholderText(tr("ph.archive"))
        btn = QPushButton(tr("btn.browse"))
        btn.clicked.connect(self._browse_archive)
        h.addWidget(self.ed_archive, 1)
        h.addWidget(btn)
        self._live.append(self.ed_archive)
        sec.add_row(tr("row.archive"), box, "help.download_archive")
        lay.addWidget(sec)

    def _build_subs(self, lay):
        sec = CollapsibleSection(tr("sec.subs"))
        self.ed_sublangs = QLineEdit("all")
        self._live.append(self.ed_sublangs)
        sec.add_row(tr("row.sublangs"), self.ed_sublangs,
                    "help.sub_langs")

        self.chk_subs = QCheckBox(tr("chk.subs_embed"))
        self.chk_srt = QCheckBox(tr("chk.srt"))
        self.chk_thumb = QCheckBox(tr("chk.thumb_embed"))
        self.chk_meta = QCheckBox(tr("chk.meta"))
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        for w in (self.chk_subs, self.chk_srt, self.chk_thumb,
                  self.chk_meta):
            h.addWidget(w)
            self._live.append(w)
        h.addStretch(1)
        sec.add_row(tr("row.embed"), row, "help.embed_subs")
        lay.addWidget(sec)

    def _build_post(self, lay):
        sec = CollapsibleSection(tr("sec.post"))
        self.cb_afmt = QComboBox()
        self.cb_afmt.addItems(["mp3", "m4a", "opus", "flac"])
        self.cb_afmt.setEnabled(False)
        self._live.append(self.cb_afmt)
        sec.add_row(tr("row.afmt"), self.cb_afmt, "help.audio_format")

        self.cb_recode = QComboBox()
        self.cb_recode.addItems(self._containers())
        self._live.append(self.cb_recode)
        sec.add_row(tr("row.recode"), self.cb_recode, "help.recode")

        self.chk_sponsor = QCheckBox(tr("chk.sponsor"))
        self._live.append(self.chk_sponsor)
        sec.add_row(tr("row.sponsor"), self.chk_sponsor,
                    "help.sponsorblock")
        lay.addWidget(sec)

    def _build_debug(self, lay):
        sec = CollapsibleSection(tr("sec.debug"))
        self.chk_verbose = QCheckBox(tr("chk.verbose"))
        self.chk_quiet = QCheckBox(tr("chk.quiet"))
        self.chk_nopart = QCheckBox(tr("chk.nopart"))
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        for w in (self.chk_verbose, self.chk_quiet, self.chk_nopart):
            h.addWidget(w)
            self._live.append(w)
        h.addStretch(1)
        sec.add_row(tr("row.debugout"), row, "help.v")
        lay.addWidget(sec)

    def _build_extra(self, lay):
        sec = CollapsibleSection(tr("sec.extra"), expanded=True)
        self.ed_extra = QPlainTextEdit()
        self.ed_extra.setMaximumHeight(64)
        self.ed_extra.setPlaceholderText(tr("ph.extra"))
        self._live.append(self.ed_extra)
        sec.add_row("", self.ed_extra, "help.extra")
        lay.addWidget(sec)

    # ================= 小工具 =================
    def _browse_archive(self):
        p = pick_file(self, tr("dlg.pick_archive"),
                      tr("dlg.archive_filter"))
        if p:
            self.ed_archive.setText(p)

    def _on_format_change(self, *_):
        custom = self.cb_format.currentData() == "custom"
        self.ed_format.setEnabled(custom)
        if not custom:
            self.ed_format.setText(
                FORMAT_MAP.get(self.cb_format.currentData(), ""))
        self.cb_afmt.setEnabled(self.cb_format.currentData() == "audio")

    def _wire_live(self):
        for w in self._live:
            if isinstance(w, QPlainTextEdit):
                w.textChanged.connect(self.refresh_preview)
            elif isinstance(w, QSpinBox):
                w.valueChanged.connect(self.refresh_preview)
            elif isinstance(w, QLineEdit):
                w.textChanged.connect(self.refresh_preview)
            elif isinstance(w, QComboBox):
                w.currentIndexChanged.connect(self.refresh_preview)
            elif isinstance(w, QCheckBox):
                w.toggled.connect(self.refresh_preview)

    # ================= 与共享 TaskSpec 的双向同步 =================
    def collect(self, spec: TaskSpec):
        """界面 → spec（不碰 url，链接由主窗口顶部共用框管理）。"""
        spec.download_dir = self.ed_dir.text().strip()
        spec.output_tmpl = self.ed_tmpl.text().strip()
        spec.proxy = self.ed_proxy.text().strip()
        spec.cookies_browser = self.cb_cookies.currentText()
        spec.playlist = self.chk_playlist.isChecked()

        data = self.cb_format.currentData()
        if data == "custom":
            text = self.ed_format.text().strip()
            if text:
                spec.quality = "custom"
                spec.custom_format = text
            else:
                spec.quality = "best"
                spec.custom_format = ""
        else:
            spec.quality = data
            spec.custom_format = ""
        spec.audio_format = self.cb_afmt.currentText()

        spec.write_subs = self.chk_subs.isChecked()
        spec.sub_langs = self.ed_sublangs.text().strip() or "all"
        spec.convert_subs = self.chk_srt.isChecked()
        spec.embed_thumb = self.chk_thumb.isChecked()

        extra = []
        if self.cb_merge.currentIndex() > 0:
            extra += ["--merge-output-format",
                      self.cb_merge.currentText()]
        if self.ed_archive.text().strip():
            extra += ["--download-archive",
                      self.ed_archive.text().strip()]
        if self.ed_pl_items.text().strip():
            extra += ["--playlist-items",
                      self.ed_pl_items.text().strip()]
        if self.ed_filter.text().strip():
            extra += ["--match-filter", self.ed_filter.text().strip()]
        if self.ed_rate.text().strip():
            extra += ["-r", self.ed_rate.text().strip()]
        if self.sp_retries.value() != 10:
            extra += ["--retries", str(self.sp_retries.value())]
        if self.sp_timeout.value() > 0:
            extra += ["--socket-timeout", str(self.sp_timeout.value())]
        if self.chk_meta.isChecked():
            extra.append("--embed-metadata")
        if self.cb_recode.currentIndex() > 0:
            extra += ["--recode-video", self.cb_recode.currentText()]
        if self.chk_sponsor.isChecked():
            extra += ["--sponsorblock-mark", "all"]
        if self.chk_verbose.isChecked():
            extra.append("-v")
        if self.chk_quiet.isChecked():
            extra.append("-q")
        if self.chk_nopart.isChecked():
            extra.append("--no-part")
        extra += split_args(self.ed_extra.toPlainText())
        spec.extra_args = extra

    def apply(self, spec: TaskSpec):
        """spec → 界面（只反显共有字段）。"""
        if spec.download_dir:
            self.ed_dir.setText(spec.download_dir)
        if spec.output_tmpl:
            self.ed_tmpl.setText(spec.output_tmpl)
        if spec.proxy:
            self.ed_proxy.setText(spec.proxy)
        if spec.cookies_browser:
            self.cb_cookies.setCurrentText(spec.cookies_browser)
        idx = self.cb_format.findData(spec.quality)
        self.cb_format.setCurrentIndex(idx if idx >= 0 else 0)
        if spec.quality == "custom":
            self.ed_format.setText(spec.custom_format)
        self.cb_afmt.setCurrentText(spec.audio_format)
        self.chk_subs.setChecked(spec.write_subs)
        self.chk_srt.setChecked(spec.convert_subs)
        self.chk_thumb.setChecked(spec.embed_thumb)
        if spec.sub_langs and spec.sub_langs != "all":
            self.ed_sublangs.setText(spec.sub_langs)
        self.refresh_preview()

    # ================= 实时预览 =================
    def refresh_preview(self, *args):
        scratch = TaskSpec(url="<URL>")
        self.collect(scratch)
        self.preview.setPlainText(
            preview_command(build_argv(scratch, self.cfg)))

    def showEvent(self, e):
        self.refresh_preview()
        super().showEvent(e)


if __name__ == "__main__":
    import i18n
    import config
    cfg = config.load_config()
    i18n.init(cfg.get("language", "auto"))
    app = QApplication(sys.argv)
    panel = AdvancedPanel(cfg)
    spec = TaskSpec(url="https://youtu.be/dQw4w9WgXcQ", quality="1080",
                    write_subs=True)
    panel.apply(spec)
    panel.resize(760, 640)
    panel.show()
    sys.exit(app.exec())