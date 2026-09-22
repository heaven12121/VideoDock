"""check_files.py — VideoDock 完整性检查（导入 + 离屏实例化冒烟测试）"""
import importlib
import os
import traceback
from pathlib import Path

MODULES = ["config", "i18n", "builder", "worker", "manager",
           "widgets", "ui_advanced", "ui_settings", "ui_ip",
           "ui_tasks", "ui_history", "ui_main", "main",
           "ui_welcome", "ui_toast"]

bad = []
for m in MODULES:
    try:
        importlib.import_module(m)
        print("OK  ", m)
    except Exception as e:
        print("ERR ", m, "→", type(e).__name__, str(e)[:100])
        bad.append(m)

langs = sorted(p.name for p in Path("lang").glob("*.json")) \
    if Path("lang").is_dir() else []
print("\nlang/", langs or "（缺少 lang 文件夹！）")

# ---- 冒烟测试：离屏真实实例化主窗口 ----
if not bad:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        import i18n
        import config
        i18n.init(config.load_config().get("language", "auto"))
        from PySide6.QtWidgets import QApplication
        app = QApplication([])
        from ui_main import MainWindow
        win = MainWindow(config.load_config())
        print("\nSMOKE  MainWindow 实例化 OK")
    except Exception:
        print("\nSMOKE  MainWindow 实例化失败：")
        traceback.print_exc()
        bad.append("MainWindow(smoke)")

print("\n结果：", "全部通过 ✓" if not bad else f"有问题：{bad}")