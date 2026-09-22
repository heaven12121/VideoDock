"""ui_ip.py — IP 轮换设置页

保存即生效：manager 每次提交任务时实时读取 cfg 中的轮换配置，
无需重启。保存前校验代理池格式。
"""

import sys

from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

import config
from i18n import tr

PROXY_PREFIXES = ("http://", "https://", "socks4://", "socks5://")


class IpPage(QWidget):

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 8)
        root.setSpacing(10)

        hint = QLabel(tr("ip.hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet(
            "color:#555; background:#f4f6f8; border:1px solid #dde3e8;"
            " border-radius:4px; padding:8px;")
        root.addWidget(hint)

        form = QFormLayout()
        form.setLabelAlignment(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.AlignRight)
        root.addLayout(form)

        self.chk_enable = QCheckBox(tr("ip.enable"))
        form.addRow("", self.chk_enable)

        self.ed_pool = QPlainTextEdit()
        self.ed_pool.setPlaceholderText(tr("ip.pool_ph"))
        self.ed_pool.setFixedHeight(96)
        form.addRow(tr("ip.pool"), self.ed_pool)

        self.sp_n = QSpinBox()
        self.sp_n.setRange(1, 100)
        self.sp_n.setValue(5)
        form.addRow(tr("ip.every_n"), self.sp_n)

        self.sp_interval = QSpinBox()
        self.sp_interval.setRange(0, 3600)
        form.addRow(tr("ip.interval"), self.sp_interval)

        self.ed_hook = QLineEdit()
        self.ed_hook.setPlaceholderText(tr("ip.hook_ph"))
        form.addRow(tr("ip.hook"), self.ed_hook)

        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        btn = QPushButton(tr("btn.save"))
        btn.clicked.connect(self._save)
        h.addWidget(btn)
        h.addStretch(1)
        root.addWidget(row)

        self.lab_status = QLabel()
        root.addWidget(self.lab_status)
        root.addStretch(1)

        self.refresh_from_cfg()

    def refresh_from_cfg(self):
        self.chk_enable.setChecked(bool(self.cfg.get("rotate_enabled")))
        pool = self.cfg.get("proxy_pool") or []
        self.ed_pool.setPlainText("\n".join(pool))
        self.sp_n.setValue(int(self.cfg.get("rotate_every_n", 5)))
        self.sp_interval.setValue(int(self.cfg.get("task_interval", 0)))
        self.ed_hook.setText(self.cfg.get("rotate_command", ""))

    def _save(self):
        lines = [ln.strip() for ln
                 in self.ed_pool.toPlainText().splitlines()
                 if ln.strip()]
        for ln in lines:
            if not ln.lower().startswith(PROXY_PREFIXES):
                QMessageBox.warning(
                    self, tr("msg.confirm"),
                    tr("ip.bad_pool", line=ln))
                return
        self.cfg["rotate_enabled"] = self.chk_enable.isChecked()
        self.cfg["proxy_pool"] = lines
        self.cfg["rotate_every_n"] = self.sp_n.value()
        self.cfg["task_interval"] = self.sp_interval.value()
        self.cfg["rotate_command"] = self.ed_hook.text().strip()
        config.save_config(self.cfg)
        self.lab_status.setStyleSheet("color:#2e7d32;")
        self.lab_status.setText(tr("ip.saved"))


if __name__ == "__main__":
    cfg = config.load_config()
    app = QApplication(sys.argv)
    page = IpPage(cfg)
    page.resize(560, 460)
    page.show()
    sys.exit(app.exec())