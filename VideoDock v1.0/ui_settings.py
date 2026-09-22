"""ui_settings.py — 设置页

修正：QUrl 属于 QtCore（PySide6 中 QtGui 没有 QUrl）。
yt-dlp 与 ffmpeg 路径行各有“下载最新版”按钮，分别打开
GitHub Releases 与 ffmpeg 官网下载页（系统默认浏览器）。
其余不变：语言置顶、四项就绪检查、sig_readiness。
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

import config
from i18n import LANGS, tr
from widgets import pick_dir, pick_file

BROWSERS = ["", "firefox", "chrome", "edge", "brave", "opera",
            "vivaldi", "safari"]

YTDLP_RELEASES = "https://github.com/yt-dlp/yt-dlp/releases/latest"
FFMPEG_SITE = "https://ffmpeg.org/download.html"

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def ffmpeg_available(ytdlp_path: str, explicit: str) -> bool:
    """ffmpeg 是否可用：显式路径 → yt-dlp 同目录 → PATH。"""
    if explicit and Path(explicit).is_file():
        return True
    exe_dir = Path(ytdlp_path).parent
    name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    if (exe_dir / name).is_file():
        return True
    return shutil.which("ffmpeg") is not None


def cookies_check(exe: str, browser: str, timeout=30):
    """真实检测：让 yt-dlp 读一次浏览器 Cookie（不联网下载）。"""
    try:
        out = subprocess.run(
            [exe, "--cookies-from-browser", browser,
             "--simulate", "gui://cookie-check"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
            creationflags=CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return False, tr("ready.cookie.fail", msg="timeout")
    except Exception:
        return False, tr("ready.cookie.nofind")
    text = ((out.stdout or "") + (out.stderr or "")).lower()
    if "unsupported url" in text:
        return True, tr("ready.cookie.ok")
    if ("could not find" in text or "not found" in text
            or "no such" in text):
        return False, tr("ready.cookie.nofind")
    if "decrypt" in text or "dpapi" in text:
        return False, tr("ready.cookie.decrypt")
    last = ((out.stderr or "").strip().splitlines() or ["?"])[-1]
    return False, tr("ready.cookie.fail", msg=last[:100])


class SettingsPage(QWidget):

    sig_readiness = Signal(int)      # 就绪项数量 0-4

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._orig_lang = cfg.get("language", "auto")
        self._flags = {"ytdlp": False, "ffmpeg": False,
                       "dir": False, "cookie": False}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(16, 12, 16, 12)
        bv.setSpacing(10)

        # ================= 语言（置顶） =================
        lang_form = QFormLayout()
        lang_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bv.addLayout(lang_form)
        self.cb_lang = QComboBox()
        self.cb_lang.addItem("Auto", "auto")
        for code, name in LANGS.items():
            self.cb_lang.addItem(name, code)
        idx = self.cb_lang.findData(self._orig_lang)
        self.cb_lang.setCurrentIndex(idx if idx >= 0 else 0)
        lang_form.addRow(tr("set.language"), self.cb_lang)
        lab_hint = QLabel(tr("set.lang_hint"))
        lab_hint.setStyleSheet("color:#777;")
        lang_form.addRow("", lab_hint)

        # ================= 就绪检查 =================
        grp = QGroupBox(tr("ready.title"))
        gv = QVBoxLayout(grp)
        self.lab_count = QLabel()
        self.lab_count.setAlignment(Qt.AlignRight)
        gv.addWidget(self.lab_count)
        gf = QFormLayout()
        gf.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        gv.addLayout(gf)

        # ---- Cookie 浏览器 ----
        cookie_row = QWidget()
        ch = QHBoxLayout(cookie_row)
        ch.setContentsMargins(0, 0, 0, 0)
        ch.setSpacing(6)
        self.cb_cookies = QComboBox()
        self.cb_cookies.addItems(BROWSERS)
        cur = cfg.get("cookies_browser", "")
        if cur in BROWSERS:
            self.cb_cookies.setCurrentText(cur)
        self.btn_cookie = QPushButton(tr("btn.check"))
        self.btn_cookie.clicked.connect(self._check_cookie)
        ch.addWidget(self.cb_cookies, 1)
        ch.addWidget(self.btn_cookie)
        gf.addRow(tr("ready.cookie"), cookie_row)
        self.lab_cookie = QLabel()
        self.lab_cookie.setWordWrap(True)
        gf.addRow("", self.lab_cookie)

        # ---- yt-dlp 路径（含版本号 + 下载最新版） ----
        self.ed_ytdlp = QLineEdit(cfg.get("ytdlp_path", ""))
        gf.addRow(tr("ready.ytdlp"),
                  self._with_browse(self.ed_ytdlp, self._browse_ytdlp,
                                    YTDLP_RELEASES))
        self.lab_ytdlp = QLabel()
        self.lab_ytdlp.setWordWrap(True)
        gf.addRow("", self.lab_ytdlp)

        # ---- ffmpeg 路径（含下载最新版） ----
        self.ed_ffmpeg = QLineEdit(cfg.get("ffmpeg_path", ""))
        self.ed_ffmpeg.setPlaceholderText(
            "ffmpeg.exe path / ffmpeg.exe 路径")
        gf.addRow(tr("ready.ffmpeg"),
                  self._with_browse(self.ed_ffmpeg, self._browse_ffmpeg,
                                    FFMPEG_SITE))
        self.lab_ffmpeg = QLabel()
        self.lab_ffmpeg.setWordWrap(True)
        gf.addRow("", self.lab_ffmpeg)

        # ---- 下载目录 ----
        self.ed_dir = QLineEdit(cfg.get("download_dir", ""))
        gf.addRow(tr("ready.dir"),
                  self._with_browse(self.ed_dir, self._browse_dir))
        self.lab_dir = QLabel()
        self.lab_dir.setWordWrap(True)
        gf.addRow("", self.lab_dir)
        bv.addWidget(grp)

        # ================= 通用选项 =================
        gen = QFormLayout()
        gen.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bv.addLayout(gen)
        self.sp_conc = QSpinBox()
        self.sp_conc.setRange(1, 4)
        self.sp_conc.setValue(int(cfg.get("max_concurrent", 1)))
        gen.addRow(tr("set.concurrent"), self.sp_conc)
        self.sp_hist = QSpinBox()
        self.sp_hist.setRange(50, 5000)
        self.sp_hist.setSingleStep(50)
        self.sp_hist.setValue(int(cfg.get("history_max", 500)))
        gen.addRow(tr("set.histmax"), self.sp_hist)
        self.ed_proxy = QLineEdit(cfg.get("proxy", ""))
        self.ed_proxy.setPlaceholderText(tr("set.proxy_ph"))
        gen.addRow(tr("set.proxy_global"), self.ed_proxy)

        # ================= 完成反馈 =================
        fb = QFormLayout()
        bv.addLayout(fb)
        self.chk_sound = QCheckBox(tr("set.sound"))
        self.chk_sound.setChecked(bool(cfg.get("sound_enabled", True)))
        fb.addRow("", self.chk_sound)
        self.chk_popup = QCheckBox(tr("set.popup"))
        self.chk_popup.setChecked(bool(cfg.get("popup_enabled", True)))
        fb.addRow("", self.chk_popup)
        self.chk_welcome = QCheckBox(tr("set.welcome"))
        self.chk_welcome.setChecked(bool(cfg.get("show_welcome", True)))
        fb.addRow("", self.chk_welcome)

        # ================= 保存 =================
        save_row = QWidget()
        sh = QHBoxLayout(save_row)
        sh.setContentsMargins(0, 0, 0, 0)
        self.btn_save = QPushButton(tr("btn.save"))
        self.btn_save.clicked.connect(self._save)
        sh.addWidget(self.btn_save)
        sh.addStretch(1)
        self.lab_status = QLabel()
        sh.addWidget(self.lab_status, 1)
        bv.addWidget(save_row)
        bv.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(body)
        outer.addWidget(scroll)

        # ---- 信号 ----
        self.ed_ytdlp.textChanged.connect(self._refresh_status)
        self.ed_ffmpeg.textChanged.connect(self._refresh_status)
        self.ed_dir.textChanged.connect(self._refresh_status)
        self.cb_cookies.currentIndexChanged.connect(
            lambda _: self._check_cookie())

        self._refresh_status()
        self._check_cookie()

    # ---------------- 拼装小工具 ----------------
    def _with_browse(self, edit: QLineEdit, slot,
                     latest_url: str = "") -> QWidget:
        """输入框 + 浏览按钮（+ 可选“下载最新版”按钮）。"""
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(edit, 1)
        btn = QPushButton(tr("btn.browse"))
        btn.clicked.connect(slot)
        lay.addWidget(btn)
        if latest_url:
            b2 = QPushButton(tr("btn.dl_latest"))
            b2.setToolTip(latest_url)
            b2.clicked.connect(
                lambda: QDesktopServices.openUrl(QUrl(latest_url)))
            lay.addWidget(b2)
        return w

    def _browse_ytdlp(self):
        p = pick_file(self, tr("dlg.pick_ytdlp"), "yt-dlp (yt-dlp*.exe)")
        if p:
            self.ed_ytdlp.setText(p)

    def _browse_ffmpeg(self):
        p = pick_file(self, tr("dlg.pick_ffmpeg"),
                      "ffmpeg (ffmpeg*.exe)")
        if p:
            self.ed_ffmpeg.setText(p)

    def _browse_dir(self):
        p = pick_dir(self, tr("dlg.pick_savedir"))
        if p:
            self.ed_dir.setText(p)

    # ---------------- 就绪检查 ----------------
    def _emit_ready(self):
        n = sum(1 for v in self._flags.values() if v)
        ok = n == 4
        self.lab_count.setText(
            tr("badge.ok" if ok else "badge.bad", n=n))
        self.lab_count.setStyleSheet(
            "color:#2e7d32; font-weight:bold;"
            if ok else "color:#b8860b; font-weight:bold;")
        self.sig_readiness.emit(n)

    def _refresh_status(self):
        ytdlp = self.ed_ytdlp.text().strip()
        if Path(ytdlp).is_file():
            ver = config.ytdlp_version({"ytdlp_path": ytdlp})
            self._ok(self.lab_ytdlp,
                     tr("ready.ytdlp.ok", ver=ver or "?"))
            self._flags["ytdlp"] = True
        else:
            self._bad(self.lab_ytdlp, tr("ready.ytdlp.nofile"))
            self._flags["ytdlp"] = False

        if ffmpeg_available(ytdlp, self.ed_ffmpeg.text().strip()):
            self._ok(self.lab_ffmpeg, tr("ready.ffmpeg.ok"))
            self._flags["ffmpeg"] = True
        else:
            self._bad(self.lab_ffmpeg, tr("ready.ffmpeg.bad"))
            self._flags["ffmpeg"] = False

        d_text = self.ed_dir.text().strip() or \
            config.DEFAULTS["download_dir"]
        try:
            Path(d_text).mkdir(parents=True, exist_ok=True)
            self._ok(self.lab_dir, tr("ready.dir.ok"))
            self._flags["dir"] = True
        except OSError as e:
            self._bad(self.lab_dir, "✗ " + str(e)[:80])
            self._flags["dir"] = False
        self._emit_ready()

    def _check_cookie(self):
        browser = self.cb_cookies.currentText()
        if not browser:
            self.lab_cookie.setStyleSheet("color:#777;")
            self.lab_cookie.setText(tr("ready.cookie.off"))
            self._flags["cookie"] = True      # 关闭=合法状态
            self._emit_ready()
            return
        exe = self.ed_ytdlp.text().strip() or \
            self.cfg.get("ytdlp_path", "")
        self.btn_cookie.setEnabled(False)
        self.lab_cookie.setStyleSheet("color:#777;")
        self.lab_cookie.setText(tr("ready.cookie.checking"))
        QApplication.processEvents()
        ok, msg = cookies_check(exe, browser)
        self.lab_cookie.setStyleSheet(
            "color:#2e7d32;" if ok else "color:#c62828;")
        self.lab_cookie.setText(msg)
        self._flags["cookie"] = ok
        self.btn_cookie.setEnabled(True)
        self._emit_ready()

    @staticmethod
    def _ok(label: QLabel, text: str):
        label.setStyleSheet("color:#2e7d32;")
        label.setText(text)

    @staticmethod
    def _bad(label: QLabel, text: str):
        label.setStyleSheet("color:#c62828;")
        label.setText(text)

    # ---------------- 保存 ----------------
    def _save(self):
        self.cfg["language"] = self.cb_lang.currentData()
        self.cfg["ytdlp_path"] = (self.ed_ytdlp.text().strip()
                                  or config.DEFAULTS["ytdlp_path"])
        self.cfg["ffmpeg_path"] = self.ed_ffmpeg.text().strip()
        self.cfg["download_dir"] = (self.ed_dir.text().strip()
                                    or config.DEFAULTS["download_dir"])
        try:
            Path(self.cfg["download_dir"]).mkdir(
                parents=True, exist_ok=True)
        except OSError as e:
            QMessageBox.warning(self, tr("msg.confirm"),
                                "✗ " + str(e))
            return
        self.cfg["max_concurrent"] = self.sp_conc.value()
        self.cfg["history_max"] = self.sp_hist.value()
        self.cfg["proxy"] = self.ed_proxy.text().strip()
        self.cfg["cookies_browser"] = self.cb_cookies.currentText()
        self.cfg["sound_enabled"] = self.chk_sound.isChecked()
        self.cfg["popup_enabled"] = self.chk_popup.isChecked()
        self.cfg["show_welcome"] = self.chk_welcome.isChecked()
        config.save_config(self.cfg)
        self._refresh_status()
        if self.cb_lang.currentData() != self._orig_lang:
            code = self.cb_lang.currentData()
            name = "Auto" if code == "auto" else LANGS.get(code, code)
            self.lab_status.setStyleSheet("color:#b8860b;")
            self.lab_status.setText(
                tr("msg.restart_needed", lang=name))
            self._orig_lang = code
        else:
            self.lab_status.setStyleSheet("color:#2e7d32;")
            self.lab_status.setText(tr("msg.saved"))

    def refresh_from_cfg(self):
        """配置被其他窗口（欢迎弹窗等）修改后由主窗口调用。"""
        self.ed_ytdlp.setText(self.cfg.get("ytdlp_path", ""))
        self.ed_ffmpeg.setText(self.cfg.get("ffmpeg_path", ""))
        self.ed_dir.setText(self.cfg.get("download_dir", ""))
        self.ed_proxy.setText(self.cfg.get("proxy", ""))
        self.sp_conc.setValue(int(self.cfg.get("max_concurrent", 1)))
        self.sp_hist.setValue(int(self.cfg.get("history_max", 500)))
        c = self.cfg.get("cookies_browser", "")
        if c in BROWSERS:
            self.cb_cookies.setCurrentText(c)
        self.chk_sound.setChecked(
            bool(self.cfg.get("sound_enabled", True)))
        self.chk_popup.setChecked(
            bool(self.cfg.get("popup_enabled", True)))
        self.chk_welcome.setChecked(
            bool(self.cfg.get("show_welcome", True)))
        code = self.cfg.get("language", "auto")
        idx = self.cb_lang.findData(code)
        self.cb_lang.setCurrentIndex(idx if idx >= 0 else 0)
        self._orig_lang = code
        self._refresh_status()
        self._check_cookie()


if __name__ == "__main__":
    cfg = config.load_config()
    import i18n
    i18n.init(cfg.get("language", "auto"))
    app = QApplication(sys.argv)
    page = SettingsPage(cfg)
    page.sig_readiness.connect(lambda n: print("ready:", n, "/4"))
    page.resize(640, 660)
    page.show()
    sys.exit(app.exec())