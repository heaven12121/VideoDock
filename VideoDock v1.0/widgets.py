"""widgets.py — 公共控件：？帮助图标 / 参数行 / 折叠分组 / 文件选择

HelpLabel 在构造时按 key 调 tr() 取译文（重启生效的语言策略下，
构造期取词即可）；悬停发出信号，由主窗口底部帮助栏显示。
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget,
)

from i18n import tr


class HelpLabel(QLabel):
    """固定显示 '?' 的小圆标。
    鼠标移入：emit helpRequested(说明文字)；移出：emit("")。"""

    helpRequested = Signal(str)

    def __init__(self, key, parent=None):
        super().__init__("?", parent)
        self._key = key
        self._text = tr(key)
        self.setToolTip(self._text)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(18, 18)
        self.setCursor(Qt.WhatsThisCursor)
        self.setStyleSheet(
            "QLabel { border:1px solid #9a9a9a; border-radius:9px;"
            " color:#666; font-size:11px; }"
            "QLabel:hover { border-color:#2d7dd2; color:#2d7dd2; }")

    def enterEvent(self, event):
        self.helpRequested.emit(self._text)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.helpRequested.emit("")
        super().leaveEvent(event)


class FieldRow(QWidget):
    """一行 = 名称 + 控件 + ？。中间的控件通过 .field 访问。
    名称应由调用方传入 tr() 之后的译文。"""

    def __init__(self, name, field, help_key, parent=None):
        super().__init__(parent)
        self.field = field
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(6)
        lbl = QLabel(name)
        lbl.setMinimumWidth(110)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(lbl)
        lay.addWidget(field, 1)
        lay.addWidget(HelpLabel(help_key))


class CollapsibleSection(QWidget):
    """可折叠分组：点击标题行展开/收起正文。"""

    def __init__(self, title, expanded=False, parent=None):
        super().__init__(parent)
        self._title = title
        self._toggle = QToolButton()
        self._toggle.setCheckable(True)
        self._toggle.setChecked(expanded)
        self._toggle.setStyleSheet(
            "QToolButton { border:none; font-weight:bold;"
            " text-align:left; padding:4px; }"
            "QToolButton:hover { color:#2d7dd2; }")
        self.body = QWidget()
        self.body.setVisible(expanded)
        self.lay = QVBoxLayout(self.body)
        self.lay.setContentsMargins(14, 2, 2, 6)
        self.lay.setSpacing(4)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._toggle)
        outer.addWidget(self.body)

        self._toggle.toggled.connect(self._on_toggle)
        self._sync_title()

    def _sync_title(self):
        arrow = "▾" if self._toggle.isChecked() else "▸"
        self._toggle.setText(f"{arrow} {self._title}")

    def _on_toggle(self, on):
        self.body.setVisible(on)
        self._sync_title()

    def add_row(self, name, field, help_key):
        row = FieldRow(name, field, help_key)
        self.lay.addWidget(row)
        return row

    def add_widget(self, widget):
        self.lay.addWidget(widget)
        return widget


def pick_file(parent, title, pattern=None):
    """选单个文件，返回完整路径；取消返回空串。
    pattern 传 None 时用当前语言的『所有文件』过滤器。"""
    if pattern is None:
        pattern = tr("dlg.all_files")
    path, _ = QFileDialog.getOpenFileName(parent, title, "", pattern)
    return path


def pick_dir(parent, title=None):
    """选目录，返回完整路径；取消返回空串。"""
    if title is None:
        title = tr("dlg.pick_dir")
    return QFileDialog.getExistingDirectory(parent, title, "")