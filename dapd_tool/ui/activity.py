"""Track running operations so shutdown and update installation share one guard."""
from PySide6.QtCore import QObject, Signal


class ActivityState(QObject):
    changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = set()

    @property
    def busy(self):
        return bool(self._running)

    def set_busy(self, runner, busy):
        if busy:
            self._running.add(runner)
        else:
            self._running.discard(runner)
        self.changed.emit(self.busy)
