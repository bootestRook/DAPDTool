from PySide6.QtCore import QObject, QThread, Signal, Slot
from ..engine import safe_error


class Worker(QThread):
    result = Signal(object)
    failure = Signal(str)
    update = Signal(object)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            self.result.emit(self.function(self.update.emit))
        except Exception as exc:
            self.failure.emit(safe_error(exc))


class Runner(QObject):
    busyChanged = Signal(bool)

    def __init__(self, parent, activity):
        super().__init__(parent)
        self.activity = activity
        self.worker = None
        self.on_result = self.on_error = self.on_update = None

    @property
    def busy(self):
        return self.worker is not None

    def start(self, function, result, error, update=lambda _: None):
        if self.busy:
            return False
        self.on_result, self.on_error, self.on_update = result, error, update
        self.worker = Worker(function, self)
        self.worker.result.connect(self.received)
        self.worker.failure.connect(self.failed)
        self.worker.update.connect(self.updated)
        self.worker.finished.connect(self.finished)
        self.activity.set_busy(self, True)
        self.busyChanged.emit(True)
        self.worker.start()
        return True

    @Slot(object)
    def received(self, value):
        self.on_result(value)

    @Slot(str)
    def failed(self, value):
        self.on_error(value)

    @Slot(object)
    def updated(self, value):
        self.on_update(value)

    @Slot()
    def finished(self):
        old, self.worker = self.worker, None
        old.deleteLater()
        self.activity.set_busy(self, False)
        self.busyChanged.emit(False)
