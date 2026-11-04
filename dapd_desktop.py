"""Standalone executable entry point. Only DAPD and desktop modules are imported."""
import sys

if __name__ == "__main__":
    import velopack
    velopack.App().set_auto_apply_on_startup(False).run()

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtWidgets import QApplication

from dapd_tool import VERSION
from dapd_tool.storage import Store
from dapd_tool.ui import MainWindow, configure_app, message


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DAPDTaskTool")
    app.setApplicationVersion(VERSION)
    configure_app(app)
    try:
        store = Store()
        lock = QLockFile(str(store.directory / "app.lock"))
        lock.setStaleLockTime(0)
        if not lock.tryLock(0):
            if lock.error() == QLockFile.LockError.LockFailedError:
                message(None, "DAPD 任务工具已在运行，请使用已经打开的窗口。")
                return 0
            message(None, "无法在本地数据目录创建锁文件。请检查当前程序的文件访问权限，或联系电脑管理员。")
            return 1
        store.recover_interrupted()
        window = MainWindow(store)
    except Exception:
        message(None, "无法打开本地数据目录。请检查用户目录是否可写，以及是否有其他程序占用数据文件。")
        return 1

    def report_exception(kind, value, traceback):
        # Do not write credentials, HTTP objects, or arbitrary exception strings to logs.
        message(window, "操作未完成。请查看创建记录后再继续；如果正在创建，请先停止并核对进度。")

    sys.excepthook = report_exception
    window.show()
    QTimer.singleShot(0, window.start)
    result = app.exec()
    lock.unlock()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
