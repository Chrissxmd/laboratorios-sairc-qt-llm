from PySide6.QtCore import QObject, Signal, Slot


class TaskWorker(QObject):
    progress = Signal(dict)
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, operation):
        super().__init__()
        self.operation = operation

    @Slot()
    def run(self):
        try:
            self.result.emit(self.operation(self.progress.emit))
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()
