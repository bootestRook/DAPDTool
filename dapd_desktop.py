"""Standalone executable entry point. Only DAPD and desktop modules are imported."""
import sys

if __name__ == "__main__":
    import velopack
    velopack.App().set_auto_apply_on_startup(False).run()

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from dapd_tool import VERSION
from dapd_tool.storage import Store
from dapd_tool.instance import acquire_instance_lock
from dapd_tool.ui.main_window import MainWindow
from dapd_tool.ui.theme import configure_app
from dapd_tool.ui.controls import message


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DAPDTaskTool")
    app.setApplicationVersion(VERSION)
    configure_app(app)
    try:
        lock = acquire_instance_lock()
    except Exception:
        message(None, "无法建立程序实例锁，请检查当前 Windows 用户的运行权限。")
        return 1
    if lock is None:
        message(None, "DAPD 任务工具已在运行，请使用已经打开的窗口。")
        return 0
    try:
        store = Store()
        store.recover_interrupted()
        window = MainWindow(store)
    except Exception:
        lock.Close()
        message(None, "无法打开本地数据目录。请检查用户目录是否可写，以及是否有其他程序占用数据文件。")
        return 1

    def report_exception(kind, value, traceback):
        # Do not write credentials, HTTP objects, or arbitrary exception strings to logs.
        message(window, "操作未完成。请查看创建记录后再继续；如果正在创建，请先停止并核对进度。")

    sys.excepthook = report_exception
    window.show()
    QTimer.singleShot(0, window.start)
    try:
        result = app.exec()
    finally:
        lock.Close()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
