"""main.py — VideoDock 程序入口

本次修正：欢迎窗关闭后立即让设置页从 cfg 刷新显示。
此前设置页在欢迎窗之前就用旧值渲染了“启动时显示帮助”复选框，
欢迎窗写入“不再提醒”后界面仍显示打钩——这正是
“设置里明明打钩了却不弹窗”的根源（文件里实际已是关）。
"""

import ctypes
import os
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

import config
import i18n
from ui_main import MainWindow

try:
    from ui_welcome import WelcomeDialog
except ImportError:                                     # pragma: no cover
    WelcomeDialog = None


def resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def main() -> int:
    cfg = config.load_config()
    i18n.init(cfg.get("language", "auto"))

    if os.name == "nt":
        try:
            ctypes.windll.shell32. \
                SetCurrentProcessExplicitAppUserModelID("VideoDock.1")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("VideoDock")

    icon_path = resource_dir() / "VDicon01.ICO"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))

    win = MainWindow(cfg)
    if icon_path.is_file():
        win.setWindowIcon(QIcon(str(icon_path)))
    win.show()

    # 启动帮助：显示与否只看文件里的真实值
    if WelcomeDialog is not None and cfg.get("show_welcome", True):
        dlg = WelcomeDialog(cfg, win)
        dlg.exec()
        config.save_config(cfg)
        # 关键修正：欢迎窗可能刚把“不再提醒”写入 cfg，
        # 立即刷新设置页，让复选框与文件保持一致，
        # 杜绝“界面打钩、文件已关”的错位。
        try:
            win.settings_page.refresh_from_cfg()
        except Exception:
            pass

    rc = app.exec()
    config.save_config(cfg)     # 退出兜底落盘
    return rc


if __name__ == "__main__":
    sys.exit(main())