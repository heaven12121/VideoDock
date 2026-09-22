"""installer.py — VDSetup 安装向导（最终一致版）

要点：
  · 不使用 QWizard registerField/field（路径含空格时必填校验
    失效导致"下一步"灰死），一律直接读 mode_page.ed_app 控件；
  · 程序目录默认 D:\\Program Files\\VideoDock（无 D 盘回退），
    下载目录固定 = 程序目录\\downloads（不在向导中询问，
    用户安装后在主程序设置页自行修改）；
  · ModePage 页内校验：目录非空即可下一步；
  · 三件套 + 使用须知复制到程序目录，须知自动弹出一次；
  · 可选开始菜单/桌面快捷方式；写入 HKCU 卸载注册表与
    Uninstall.bat（Windows 设置-应用 可卸载）。
"""

import io
import json
import os
import shutil
import subprocess
import sys
import threading
import zipfile
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton,
    QRadioButton, QVBoxLayout, QWidget, QWizard, QWizardPage,
)

import i18n
from i18n import LANGS, tr

APP_VERSION = "1.0"
NOTICE_NAME = "使用须知.txt"
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
BROWSERS = ["firefox", "chrome", "edge", "brave", "opera",
            "vivaldi", "safari"]
FF_URL = ("https://github.com/BtbN/FFmpeg-Builds/releases/latest/"
          "download/ffmpeg-master-latest-win64-gpl.zip")
UNINST_KEY = (r"Software\Microsoft\Windows\CurrentVersion"
              r"\Uninstall\VideoDock")


# ================= 基础工具 =================
def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _meipass() -> Path:
    return Path(getattr(sys, "_MEIPASS", "") or ".")


def _icon_path() -> str:
    for c in (_base_dir() / "VDicon01.ICO",
              _meipass() / "VDicon01.ICO"):
        if c.is_file():
            return str(c)
    return ""


def bundled_videodock():
    for c in (_meipass() / "VideoDock.exe",
              _base_dir() / "VideoDock.exe"):
        if c.is_file():
            return c
    return None


def bundled_ytdlp():
    for c in (_meipass() / "yt-dlp.exe", _base_dir() / "yt-dlp.exe"):
        if c.is_file():
            return c
    return None


def bundled_ffmpeg():
    for c in (_meipass() / "ffmpeg.exe", _base_dir() / "ffmpeg.exe"):
        if c.is_file():
            return c
    return None


def bundled_notice():
    for c in (_meipass() / NOTICE_NAME, _base_dir() / NOTICE_NAME):
        if c.is_file():
            return c
    return None


def find_ffmpeg(app_dir: Path):
    for c in (app_dir / "ffmpeg.exe",
              app_dir / "yt-dlp_win" / "ffmpeg.exe",
              _base_dir() / "ffmpeg.exe"):
        if c.is_file():
            return c
    found = shutil.which("ffmpeg")
    return Path(found) if found else None


def ytdlp_version(exe: str) -> str:
    try:
        out = subprocess.run(
            [exe, "--version"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20,
            creationflags=CREATE_NO_WINDOW)
        if out.returncode == 0:
            return (out.stdout or "").strip()
    except Exception:
        pass
    return ""


def cookies_check(exe: str, browser: str, timeout=30):
    try:
        out = subprocess.run(
            [exe, "--cookies-from-browser", browser,
             "--simulate", "gui://cookie-check"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
            creationflags=CREATE_NO_WINDOW)
    except Exception:
        return False, ""
    text = ((out.stdout or "") + (out.stderr or "")).lower()
    if "unsupported url" in text:
        return True, tr("ready.cookie.ok")
    if "could not find" in text or "not found" in text:
        return False, tr("ready.cookie.nofind")
    if "decrypt" in text or "dpapi" in text:
        return False, tr("ready.cookie.decrypt")
    return False, tr("ready.cookie.fail", msg="error")


def default_app_dir() -> Path:
    if os.path.exists("D:\\"):
        return Path("D:\\Program Files\\VideoDock")
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "Programs" / "VideoDock"


def start_menu_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return (Path(base) / "Microsoft" / "Windows" / "Start Menu"
            / "Programs" / "VideoDock")


def desktop_dir() -> str:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "[Environment]::GetFolderPath('Desktop')"],
            capture_output=True, text=True, timeout=20,
            creationflags=CREATE_NO_WINDOW)
        d = (out.stdout or "").strip()
        if d:
            return d
    except Exception:
        pass
    return str(Path.home() / "Desktop")


def _ps_quote(s) -> str:
    return str(s).replace("'", "''")


def make_shortcut(lnk: Path, target: str, workdir: str,
                  icon: str) -> bool:
    if os.name != "nt":
        return False
    script = ("$s=(New-Object -COM WScript.Shell)"
              f".CreateShortcut('{_ps_quote(lnk)}'); "
              f"$s.TargetPath='{_ps_quote(target)}'; "
              f"$s.WorkingDirectory='{_ps_quote(workdir)}'; "
              f"$s.IconLocation='{_ps_quote(str(icon))},0'; "
              "$s.Save()")
    try:
        lnk.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", script],
            creationflags=CREATE_NO_WINDOW, capture_output=True,
            timeout=30)
        return Path(lnk).is_file()
    except Exception:
        return False


def dir_size_kb(p: Path) -> int:
    total = 0
    try:
        for f in p.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
            except OSError:
                pass
    except OSError:
        pass
    return max(1, total // 1024)


def register_uninstall(app_dir: Path) -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg
    except ImportError:
        return False
    exe = app_dir / "VideoDock.exe"
    uninst = app_dir / "Uninstall.bat"
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                              UNINST_KEY) as k:
            def setv(name, value, typ=winreg.REG_SZ):
                winreg.SetValueEx(k, name, 0, typ, value)
            setv("DisplayName", "VideoDock")
            setv("DisplayVersion", APP_VERSION)
            setv("Publisher", "VideoDock")
            if exe.is_file():
                setv("DisplayIcon", str(exe))
            setv("InstallLocation", str(app_dir))
            setv("UninstallString", f'"{uninst}"')
            setv("NoModify", 1, winreg.REG_DWORD)
            setv("NoRepair", 1, winreg.REG_DWORD)
            setv("EstimatedSize", dir_size_kb(app_dir),
                 winreg.REG_DWORD)
        return True
    except OSError:
        return False


def write_uninstall_bat(app_dir: Path, cfg_path: Path,
                        dl_dir: str) -> bool:
    desk = desktop_dir()
    sm_dir = start_menu_dir()
    sm_lnk = sm_dir / "VideoDock.lnk"
    dl = Path(dl_dir)
    dl_inside = str(dl).lower().startswith(str(app_dir).lower())
    lines = [
        "@echo off",
        "title Uninstall VideoDock",
        "taskkill /f /im VideoDock.exe >nul 2>&1",
        f'del /q "{sm_lnk}" >nul 2>&1',
        f'rmdir "{sm_dir}" 2>nul',
        f'del /q "{desk}\\VideoDock.lnk" >nul 2>&1',
        'reg delete "HKCU\\Software\\Microsoft\\Windows'
        '\\CurrentVersion\\Uninstall\\VideoDock" /f >nul 2>&1',
    ]
    if dl_inside:
        lines += [
            "echo.",
            'choice /c YN /t 8 /d N /m "Also delete downloaded '
            'videos (downloads folder)?"',
            "if errorlevel 2 goto keepdl",
            "goto delpass",
            ":keepdl",
            f'move /y "{dl}" "{desk}\\VideoDock_downloads" '
            ">nul 2>&1",
            ":delpass",
        ]
    lines += [
        f'del /q "{cfg_path}" >nul 2>&1',
        f'del /q "{app_dir}\\{NOTICE_NAME}" >nul 2>&1',
        "echo Uninstalling, please wait...",
        f'start "" cmd /c "timeout /t 2 /nobreak >NUL '
        f'& rd /s /q "{app_dir}""',
        "exit",
    ]
    text = "\r\n".join(lines) + "\r\n"
    bat = app_dir / "Uninstall.bat"
    try:
        try:
            bat.write_text(text, encoding="mbcs")
        except (LookupError, OSError):
            bat.write_text(text, encoding="utf-8")
        return True
    except OSError:
        return False


def relaunch(lang_code: str):
    QMessageBox.information(None, tr("inst.title"),
                            tr("msg.restart_needed",
                               lang=LANGS.get(lang_code, lang_code)))
    env = os.environ.copy()
    env["VD_LANG"] = lang_code
    subprocess.Popen([sys.executable] + sys.argv, env=env)
    QApplication.instance().quit()


def write_config(app_dir: Path, dl_dir: str, ffmpeg_path: str,
                 browser: str, language: str, portable: bool) -> Path:
    app_dir.mkdir(parents=True, exist_ok=True)
    if portable:
        (app_dir / "portable.flag").write_text("", encoding="utf-8")
        cfg_path = app_dir / "yt-dlp-gui.json"
    else:
        base = os.environ.get("APPDATA") or str(Path.home())
        d = Path(base) / "VideoDock"
        d.mkdir(parents=True, exist_ok=True)
        cfg_path = d / "yt-dlp-gui.json"
    ytdlp = app_dir / "yt-dlp.exe"
    cfg = {
        "ytdlp_path": str(ytdlp),
        "ffmpeg_path": ffmpeg_path or "",
        "download_dir": str(dl_dir),
        "output_template": "%(title)s [%(id)s].%(ext)s",
        "max_concurrent": 1, "history_max": 500,
        "proxy": "", "cookies_browser": browser or "",
        "language": language, "show_welcome": True,
        "sound_enabled": True, "popup_enabled": True,
        "rotate_enabled": False, "proxy_pool": [],
        "rotate_every_n": 5, "rotate_command": "",
        "task_interval": 0, "history": [],
    }
    cfg_path.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8")
    Path(cfg["download_dir"]).mkdir(parents=True, exist_ok=True)
    return cfg_path


# ================= 后台线程 =================
class FFmpegDownloader(QThread):
    progress = Signal(int, int)
    ok = Signal(str)
    fail = Signal(str)

    def __init__(self, dest: Path, parent=None):
        super().__init__(parent)
        self._dest = dest

    def run(self):
        import urllib.request
        buf = io.BytesIO()
        try:
            req = urllib.request.Request(
                FF_URL, headers={"User-Agent": "VDSetup"})
            with urllib.request.urlopen(req, timeout=60) as r:
                total = int(r.headers.get("Content-Length", 0) or 0)
                got = 0
                while True:
                    chunk = r.read(262144)
                    if not chunk:
                        break
                    buf.write(chunk)
                    got += len(chunk)
                    self.progress.emit(got, total)
        except Exception as e:
            self.fail.emit(str(e))
            return
        try:
            with zipfile.ZipFile(buf) as z:
                for name in z.namelist():
                    if name.endswith(("ffmpeg.exe", "/ffmpeg.exe")):
                        self._dest.parent.mkdir(parents=True,
                                                exist_ok=True)
                        self._dest.write_bytes(z.read(name))
                        self.ok.emit(str(self._dest))
                        return
            self.fail.emit("ffmpeg.exe not found in archive")
        except Exception as e:
            self.fail.emit(str(e))


class CookieBridge(QObject):
    result = Signal(int, str, bool, str)
    finished = Signal(int)


# ================= 向导页 =================
class WelcomePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle(tr("inst.welcome_t"))
        v = QVBoxLayout(self)
        lab = QLabel(tr("inst.welcome_b"))
        lab.setWordWrap(True)
        v.addWidget(lab)
        form = QFormLayout()
        self.cb_lang = QComboBox()
        self.cb_lang.addItem("Auto", "auto")
        for code, name in LANGS.items():
            self.cb_lang.addItem(name, code)
        forced = os.environ.get("VD_LANG", "")
        if forced in LANGS:
            idx = self.cb_lang.findData(forced)
            if idx >= 0:
                self.cb_lang.setCurrentIndex(idx)
        form.addRow(tr("set.language"), self.cb_lang)
        v.addLayout(form)
        v.addStretch(1)
        self.cb_lang.activated.connect(self._on_lang)

    def _on_lang(self):
        code = self.cb_lang.currentData()
        if code == "auto":
            if os.environ.get("VD_LANG"):
                env = os.environ.copy()
                env.pop("VD_LANG", None)
                subprocess.Popen([sys.executable] + sys.argv, env=env)
                QApplication.instance().quit()
        elif i18n.resolve(code) != i18n._current_code:
            relaunch(code)


class ModePage(QWizardPage):
    """只问程序目录 + 快捷方式；下载目录固定跟随程序目录。
    页内校验：目录非空即可下一步（路径含空格也正常）。"""

    def __init__(self):
        super().__init__()
        self.setTitle(tr("inst.mode_t"))
        v = QVBoxLayout(self)
        self.rb_portable = QRadioButton(tr("inst.mode_portable"))
        self.rb_installed = QRadioButton(tr("inst.mode_installed"))
        self.rb_portable.setChecked(True)
        v.addWidget(self.rb_portable)
        v.addWidget(self.rb_installed)
        form = QFormLayout()
        self.ed_app = QLineEdit(str(default_app_dir()))
        form.addRow(tr("inst.appdir"),
                    self._with_browse(self.ed_app, self._browse_app))
        v.addLayout(form)
        self.ed_app.textChanged.connect(
            lambda _t: self.completeChanged.emit())

        self.chk_startmenu = QCheckBox(tr("inst.sc_startmenu"))
        self.chk_startmenu.setChecked(True)
        self.chk_desktop = QCheckBox(tr("inst.sc_desktop"))
        self.chk_desktop.setChecked(True)
        v.addWidget(self.chk_startmenu)
        v.addWidget(self.chk_desktop)
        v.addStretch(1)

    @staticmethod
    def _with_browse(edit, slot) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(edit, 1)
        b = QPushButton(tr("btn.browse"))
        b.clicked.connect(slot)
        h.addWidget(b)
        return w

    def app_dir(self) -> str:
        return self.ed_app.text().strip() or str(default_app_dir())

    def isComplete(self):
        return bool(self.ed_app.text().strip())

    def validatePage(self):
        return self.isComplete()

    def _browse_app(self):
        d = QFileDialog.getExistingDirectory(
            self, tr("dlg.pick_savedir"), self.ed_app.text())
        if d:
            self.ed_app.setText(d)

    def is_portable(self) -> bool:
        return self.rb_portable.isChecked()


class YtdlpPage(QWizardPage):
    """释放三件套：yt-dlp.exe / ffmpeg.exe / VideoDock.exe。"""

    def __init__(self):
        super().__init__()
        self.setTitle(tr("inst.ytdlp_t"))
        self._ok = False
        self._done_for = None
        v = QVBoxLayout(self)
        self.lab = QLabel(tr("inst.ytdlp_b"))
        self.lab.setWordWrap(True)
        v.addWidget(self.lab)
        v.addStretch(1)

    def initializePage(self):
        wizard = self.wizard()
        app_dir = Path(wizard.mode_page.app_dir())
        key = str(app_dir)
        if self._ok and self._done_for == key:
            return
        self._done_for = key
        self._ok = False
        extra = []
        try:
            app_dir.mkdir(parents=True, exist_ok=True)
            exe = app_dir / "yt-dlp.exe"
            src = bundled_ytdlp()
            if src is not None:
                shutil.copyfile(src, exe)
            ff = bundled_ffmpeg()
            if ff is not None:
                shutil.copyfile(ff, app_dir / "ffmpeg.exe")
                extra.append("ffmpeg.exe ✓")
            vd = bundled_videodock()
            if vd is not None:
                shutil.copyfile(vd, app_dir / "VideoDock.exe")
                extra.append("VideoDock.exe ✓")
            if not exe.is_file():
                self.lab.setText(tr("dlg.pick_ytdlp") + " →")
                self.completeChanged.emit()
                return
            ver = ytdlp_version(str(exe))
            if ver:
                self._ok = True
                wizard._ytdlp_path = str(exe)
                text = tr("inst.ytdlp_ok", path=str(exe), ver=ver)
            else:
                text = "✗ yt-dlp --version failed"
        except OSError as e:
            text = "✗ " + str(e)
        if extra:
            text = text + "\n" + "   ".join(extra)
        self.lab.setText(text)
        self.completeChanged.emit()

    def isComplete(self):
        return self._ok


class FFmpegPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle(tr("inst.ffmpeg_t"))
        self._ok = False
        self._checked_dir = None
        self._thread = None
        v = QVBoxLayout(self)
        self.lab = QLabel()
        self.lab.setWordWrap(True)
        v.addWidget(self.lab)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.hide()
        v.addWidget(self.bar)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        self.btn_dl = QPushButton(tr("inst.ffmpeg_dl"))
        self.btn_dl.clicked.connect(self._download)
        self.btn_browse = QPushButton(tr("btn.browse"))
        self.btn_browse.clicked.connect(self._browse)
        h.addWidget(self.btn_dl)
        h.addWidget(self.btn_browse)
        h.addStretch(1)
        v.addWidget(row)
        v.addStretch(1)

    def initializePage(self):
        wizard = self.wizard()
        app_dir = Path(wizard.mode_page.app_dir())
        key = str(app_dir)
        if self._ok and self._checked_dir == key:
            return
        self._checked_dir = key
        self._set_found(find_ffmpeg(app_dir))

    def _set_found(self, path):
        if path:
            self._ok = True
            self.wizard()._ffmpeg_path = str(path)
            self.lab.setStyleSheet("color:#2e7d32;")
            self.lab.setText(tr("inst.ffmpeg_found", path=str(path)))
            self.bar.hide()
            self.btn_dl.setEnabled(False)
        else:
            self._ok = False
            self.wizard()._ffmpeg_path = ""
            self.lab.setStyleSheet("color:#c62828;")
            self.lab.setText(tr("inst.ffmpeg_missing"))
            self.btn_dl.setEnabled(True)
        self.completeChanged.emit()

    def _download(self):
        wizard = self.wizard()
        app_dir = Path(wizard.mode_page.app_dir())
        self.btn_dl.setEnabled(False)
        self.btn_browse.setEnabled(False)
        self.bar.show()
        self.bar.setValue(0)
        self._thread = FFmpegDownloader(
            app_dir / "ffmpeg.exe", self)
        self._thread.progress.connect(self._on_progress)
        self._thread.ok.connect(self._on_ok)
        self._thread.fail.connect(self._on_fail)
        self._thread.start()

    def _on_progress(self, got, total):
        pct = int(got * 100 / total) if total > 0 else 0
        self.bar.setValue(pct)
        self.lab.setStyleSheet("color:#555;")
        self.lab.setText(tr("inst.ffmpeg_downloading", pct=pct))

    def _on_ok(self, path):
        self.btn_browse.setEnabled(True)
        self._set_found(Path(path))

    def _on_fail(self, err):
        self.btn_dl.setEnabled(True)
        self.btn_browse.setEnabled(True)
        self.lab.setStyleSheet("color:#c62828;")
        self.lab.setText(tr("inst.ffmpeg_fail", err=err[:120]))

    def _browse(self):
        p, _ = QFileDialog.getOpenFileName(
            self, tr("dlg.pick_ffmpeg"), "", "ffmpeg (ffmpeg*.exe)")
        if p:
            self._set_found(Path(p))

    def isComplete(self):
        return self._ok


class CookiePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle(tr("inst.cookie_t"))
        self._gen = 0
        self._selected = ""
        self._radios = {}
        self._rb_off = None
        v = QVBoxLayout(self)
        lab = QLabel(tr("inst.cookie_b"))
        lab.setWordWrap(True)
        v.addWidget(lab)
        self._list_v = QVBoxLayout()
        self._list_v.setSpacing(4)
        v.addLayout(self._list_v)
        self.lab_state = QLabel("")
        v.addWidget(self.lab_state)
        v.addStretch(1)
        self._bridge = CookieBridge()
        self._bridge.result.connect(self._on_result)
        self._bridge.finished.connect(self._on_finished)

    def initializePage(self):
        self._gen += 1
        gen = self._gen
        while self._list_v.count():
            it = self._list_v.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._radios.clear()
        self._selected = ""
        self._rb_off = QRadioButton("—")
        self._rb_off.setChecked(True)
        self._rb_off.toggled.connect(
            lambda on: on and self._sync_sel())
        self._list_v.addWidget(self._rb_off)
        self.lab_state.setText(tr("inst.cookie_checking"))
        exe = self.wizard()._ytdlp_path
        threading.Thread(target=self._run, args=(exe, gen),
                         daemon=True).start()

    def _run(self, exe, gen):
        for b in BROWSERS:
            ok, msg = cookies_check(exe, b)
            self._bridge.result.emit(gen, b, ok, msg)
        self._bridge.finished.emit(gen)

    def _on_result(self, gen, browser, ok, msg):
        if gen != self._gen:
            return
        rb = QRadioButton(("✓ " if ok else "✗ ") + browser)
        rb.setToolTip(msg)
        rb.setEnabled(ok)
        rb.toggled.connect(self._sync_sel)
        self._list_v.addWidget(rb)
        self._radios[browser] = rb
        if ok and self._selected == "":
            rb.setChecked(True)

    def _on_finished(self, gen):
        if gen == self._gen:
            self.lab_state.setText("")

    def _sync_sel(self, *_):
        self._selected = ""
        for b, rb in self._radios.items():
            if rb.isChecked():
                self._selected = b
                return


class FinishPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle(tr("inst.finish_t"))
        v = QVBoxLayout(self)
        self.lab = QLabel(tr("inst.finish_b"))
        self.lab.setWordWrap(True)
        v.addWidget(self.lab)
        self.chk_launch = QCheckBox(tr("inst.launch"))
        self.chk_launch.setChecked(True)
        v.addWidget(self.chk_launch)
        v.addStretch(1)

    def initializePage(self):
        wizard = self.wizard()
        app_dir = Path(wizard.mode_page.app_dir())
        dl_dir = str(app_dir / "downloads")
        portable = wizard.mode_page.is_portable()
        language = os.environ.get("VD_LANG") or "auto"
        browser = ""
        for pid in wizard.pageIds():
            p = wizard.page(pid)
            if isinstance(p, CookiePage):
                browser = p._selected
        try:
            cfg_path = write_config(app_dir, dl_dir,
                                    wizard._ffmpeg_path, browser,
                                    language, portable)
            wizard._written_ok = True
            wizard._app_dir_final = app_dir
        except OSError as e:
            wizard._written_ok = False
            self.lab.setText("✗ " + str(e))
            return

        # ---- 使用须知：复制到程序目录，记录路径供弹出 ----
        wizard._notice_final = ""
        notice = bundled_notice()
        if notice is not None:
            try:
                dst = app_dir / NOTICE_NAME
                shutil.copyfile(notice, dst)
                wizard._notice_final = str(dst)
            except OSError:
                wizard._notice_final = ""

        # ---- 快捷方式 ----
        exe = app_dir / "VideoDock.exe"
        if exe.is_file():
            if wizard.mode_page.chk_startmenu.isChecked():
                make_shortcut(start_menu_dir() / "VideoDock.lnk",
                              str(exe), str(app_dir), str(exe))
            if wizard.mode_page.chk_desktop.isChecked():
                make_shortcut(
                    Path(desktop_dir()) / "VideoDock.lnk",
                    str(exe), str(app_dir), str(exe))

        # ---- 卸载程序 + 注册表 ----
        reg_ok = False
        try:
            write_uninstall_bat(app_dir, cfg_path, dl_dir)
            reg_ok = register_uninstall(app_dir)
        except Exception:
            reg_ok = False

        notes = [tr("inst.integrate.ok")] if reg_ok else \
            ["△ 未写入系统卸载列表（非 Windows 或权限受限）"]
        self.lab.setText(tr("inst.finish_b") + "\n\n"
                         + "\n".join(notes))


# ================= 组装 =================
class SetupWizard(QWizard):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr("inst.title"))
        self._ytdlp_path = ""
        self._ffmpeg_path = ""
        self._written_ok = False
        self._app_dir_final = None
        self._notice_final = ""
        ico = _icon_path()
        if ico:
            self.setWindowIcon(QIcon(ico))
        self.setButtonText(QWizard.NextButton, tr("inst.next"))
        self.setButtonText(QWizard.BackButton, tr("inst.back"))
        self.setButtonText(QWizard.FinishButton, tr("inst.finish_btn"))
        self.setButtonText(QWizard.CancelButton, tr("inst.cancel"))
        self.addPage(WelcomePage())
        self.mode_page = ModePage()
        self.addPage(self.mode_page)
        self.addPage(YtdlpPage())
        self.addPage(FFmpegPage())
        self.addPage(CookiePage())
        self.finish_page = FinishPage()
        self.addPage(self.finish_page)


def main() -> int:
    i18n.init(os.environ.get("VD_LANG") or "auto")
    app = QApplication(sys.argv)
    app.setApplicationName("VDSetup")
    ico = _icon_path()
    if ico:
        app.setWindowIcon(QIcon(ico))
    wiz = SetupWizard()
    wiz.show()
    app.exec()
    if wiz.result() == QDialog.Accepted and wiz._written_ok:
        notice = getattr(wiz, "_notice_final", "")
        if notice and Path(notice).is_file():
            try:
                os.startfile(notice)
            except OSError:
                pass
        if wiz.finish_page.chk_launch.isChecked():
            exe = wiz._app_dir_final / "VideoDock.exe"
            if exe.is_file():
                subprocess.Popen([str(exe)])
    return 0


if __name__ == "__main__":
    sys.exit(main())