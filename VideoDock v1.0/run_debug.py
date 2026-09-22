"""run_debug.py — 诊断启动器

用法：python run_debug.py（或直接双击，前提是 .py 关联了 Python）
程序正常时行为和 main.py 完全一样；
启动失败时：错误全文弹窗显示，并追加写入同目录的 error.log
"""

import sys
import traceback
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parent / "error.log"

err_text = ""
try:
    import main
    code = main.main()
    sys.exit(code)
except SystemExit:
    raise
except Exception:
    err_text = traceback.format_exc()
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 60 + "\n" + err_text)
    except OSError:
        pass

# 走到这里说明启动失败：用弹窗把错误亮出来
try:
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication(sys.argv)
    QMessageBox.critical(
        None, "启动失败",
        "程序启动出错，详情已写入 error.log\n\n"
        + err_text[-1500:])
except Exception:
    pass

print(err_text)
input("按回车键关闭…")