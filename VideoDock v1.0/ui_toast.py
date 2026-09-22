"""ui_toast.py — 完成通知条（桌面右下角）

本次修正：导入列表补上 QWidget（按钮行容器用到它）。
其余不变：无父级顶层窗、屏幕右下角定位、文件名可点击链接、
5 秒自动关闭、多弹向上堆叠。
"""

import html
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
    QWidget,
)

from i18n import tr
from ui_history import open_location

_ACTIVE = []
STYLE = """
QFrame { background:#2f3542; border-radius:8px; }
QLabel { color:#ffffff; background:transparent; border:none; }
QLabel[data-role="link"] { color:#a8c7fa; }
QLabel[data-role="more"] { color:#9aa4b0; }
QPushButton { color:#ffffff; background:#4a69bd; border:none;
              border-radius:4px; padding:4px 10px; }
QPushButton#closeBtn { background:#57606f; }
QPushButton:hover { background:#6a89cc; }
"""


class DoneToast(QFrame):

    def __init__(self, count, paths, fallback_dir, duration_ms=5000):
        super().__init__(None)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint
                            | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setStyleSheet(STYLE)
        self._paths = list(paths or [])
        self._fallback = fallback_dir or ""

        title = (tr("toast.batch", n=count) if count > 1
                 else tr("toast.done"))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 10, 10)
        lay.setSpacing(4)

        lab_title = QLabel(title)
        f = lab_title.font()
        f.setBold(True)
        lab_title.setFont(f)
        lay.addWidget(lab_title)

        # ---- 文件名链接：点击打开所在文件夹 ----
        for p in self._paths[:3]:
            lab = QLabel(
                f'<a href="#open">{html.escape(Path(p).name)}</a>')
            lab.setProperty("data-role", "link")
            lab.setToolTip(p)
            lab.linkActivated.connect(
                lambda _k, path=p: self._open_path(path))
            lay.addWidget(lab)
        if len(self._paths) > 3:
            more = QLabel(f"+{len(self._paths) - 3} …")
            more.setProperty("data-role", "more")
            lay.addWidget(more)

        row = QWidget()
        rh = QHBoxLayout(row)
        rh.setContentsMargins(0, 2, 0, 0)
        rh.setSpacing(6)
        btn_open = QPushButton(tr("toast.open"))
        btn_open.clicked.connect(self._open_first)
        btn_close = QPushButton("×")
        btn_close.setObjectName("closeBtn")
        btn_close.setFixedWidth(28)
        btn_close.clicked.connect(self.dismiss)
        rh.addWidget(btn_open)
        rh.addWidget(btn_close)
        rh.addStretch(1)
        lay.addWidget(row)

        # ---- 尺寸：最小宽度 + 布局激活后取尺寸 ----
        self.setMinimumWidth(300)
        lay.activate()
        self.adjustSize()

        QTimer.singleShot(duration_ms, self.dismiss)

    def _open_path(self, path: str):
        open_location(path, self._fallback)
        self.dismiss()

    def _open_first(self):
        path = self._paths[0] if self._paths else ""
        open_location(path, self._fallback)
        self.dismiss()

    def dismiss(self):
        if self in _ACTIVE:
            _ACTIVE.remove(self)
            self._relayout()
        self.close()
        self.deleteLater()

    def _position(self, offset_above=0):
        scr = QApplication.primaryScreen().availableGeometry()
        x = scr.right() - self.width() - 16
        y = scr.bottom() - self.height() - 16 - offset_above
        self.move(x, y)

    def _relayout(self):
        y = 0
        for t in reversed(_ACTIVE):
            t._position(y)
            y += t.height() + 8

    def show_toast(self):
        _ACTIVE.append(self)
        self._relayout()
        self.show()
        self.raise_()
        self.repaint()


def show_done_toast(parent, count, paths, fallback_dir="",
                    duration_ms=5000):
    try:
        DoneToast(count, paths, fallback_dir,
                  duration_ms).show_toast()
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    import i18n
    import config
    cfg = config.load_config()
    i18n.init(cfg.get("language", "auto"))
    app = QApplication(sys.argv)
    show_done_toast(None, 1, [r"E:\movie\示例视频 [abc].mp4"],
                    r"E:\movie")
    show_done_toast(None, 4, [r"E:\movie\a.mp4", r"E:\movie\b.mp4",
                              r"E:\movie\c.mp4", r"E:\movie\d.mp4"],
                    r"E:\movie")
    sys.exit(app.exec())