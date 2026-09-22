"""ui_welcome.py — 启动帮助窗口

契约：WelcomeDialog(cfg, parent)；勾选“不再提醒”时
写 cfg["show_welcome"] = False（落盘由调用方负责）。
配色规则（本次调整）：四项必要功能中，凡未达成的行一律橙色；
达成 → 绿色。Cookie 未启用也按“未达成”显示橙色提醒。
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

import config
from i18n import tr

OK_G = "#2e7d32"      # 达成
ORANGE = "#ef6c00"    # 未达成（用户指定）
GRAY = "#666666"      # 中性说明


def _ess_line(cfg: dict):
    """四项必要功能行：[(名称, 状态文字, 颜色), …]"""
    rows = []

    # ---- Cookie 浏览器 ----
    browser = cfg.get("cookies_browser", "")
    if browser:
        rows.append((tr("ready.cookie"),
                     tr("ready.cookie.ok") + f"（{browser}）", OK_G))
    else:
        rows.append((tr("ready.cookie"), tr("ready.cookie.off"),
                     ORANGE))

    # ---- yt-dlp ----
    if config.ytdlp_ok(cfg):
        ver = config.ytdlp_version(cfg) or "?"
        rows.append((tr("ready.ytdlp"),
                     tr("ready.ytdlp.ok", ver=ver), OK_G))
    else:
        rows.append((tr("ready.ytdlp"), tr("ready.ytdlp.nofile"),
                     ORANGE))

    # ---- ffmpeg ----
    if config.ffmpeg_ok(cfg):
        rows.append((tr("ready.ffmpeg"), tr("ready.ffmpeg.ok"), OK_G))
    else:
        rows.append((tr("ready.ffmpeg"), tr("ready.ffmpeg.bad"),
                     ORANGE))

    # ---- 下载目录 ----
    try:
        exists = Path(cfg.get("download_dir", "")).is_dir()
    except OSError:
        exists = False
    rows.append((tr("ready.dir"),
                 tr("ready.dir.ok" if exists else "ready.dir.create"),
                 OK_G if exists else ORANGE))
    return rows


class WelcomeDialog(QDialog):

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle(tr("welcome.title"))
        self.setMinimumSize(580, 500)

        outer = QVBoxLayout(self)
        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(18, 14, 18, 10)
        bv.setSpacing(10)

        # ---------- 首行：四项必要功能 + 实况 ----------
        ess = QLabel(tr("welcome.essentials"))
        ess.setWordWrap(True)
        ess.setStyleSheet("font-weight:bold;")
        bv.addWidget(ess)
        for name, status, color in _ess_line(cfg):
            lab = QLabel(f"{name} — {status}")
            lab.setWordWrap(True)
            lab.setStyleSheet(f"color:{color}; padding-left:12px;")
            bv.addWidget(lab)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        bv.addWidget(sep)

        # ---------- 简介 / 功能 / 站点 ----------
        intro = QLabel(tr("welcome.intro"))
        intro.setWordWrap(True)
        bv.addWidget(intro)

        feat = QLabel(tr("welcome.features"))
        feat.setWordWrap(True)
        bv.addWidget(feat)

        head = QLabel(tr("welcome.sites_head"))
        head.setStyleSheet("font-weight:bold;")
        bv.addWidget(head)
        sites = QLabel(tr("welcome.sites"))
        sites.setWordWrap(True)
        bv.addWidget(sites)
        all_head = QLabel(tr("welcome.sites_all"))
        all_head.setWordWrap(True)
        bv.addWidget(all_head)
        link = QLabel(
            f'<a href="{tr("welcome.url")}">{tr("welcome.url")}</a>')
        link.setOpenExternalLinks(True)
        link.setWordWrap(True)
        bv.addWidget(link)
        bv.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        # ---------- 底部：不再提醒 + 关闭 ----------
        foot = QWidget()
        fh = QHBoxLayout(foot)
        fh.setContentsMargins(18, 0, 18, 10)
        self.chk = QCheckBox(tr("welcome.dontshow"))
        fh.addWidget(self.chk)
        fh.addStretch(1)
        btn = QPushButton(tr("btn.close"))
        btn.clicked.connect(self.accept)
        fh.addWidget(btn)
        outer.addWidget(foot)

    def done(self, result):
        """无论怎么关（按钮/右上角×/Esc），勾选即写入配置。"""
        if self.chk.isChecked():
            self.cfg["show_welcome"] = False
        super().done(result)


if __name__ == "__main__":
    cfg = config.load_config()
    import i18n
    i18n.init(cfg.get("language", "auto"))
    app = QApplication(sys.argv)
    dlg = WelcomeDialog(cfg)
    dlg.exec()
    print("show_welcome =", cfg.get("show_welcome"))