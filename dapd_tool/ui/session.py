"""Account and project selection shared by the desktop pages."""
from PySide6.QtCore import QObject, Signal


class Session(QObject):
    accountChanged = Signal(str)
    projectsChanged = Signal(list)
    projectChanged = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.key = ""
        self.projects = []
        self.project = None

    def set_key(self, key):
        if key != self.key:
            self.key = key
            self.set_project(None)
            self.accountChanged.emit(key)
            self.set_projects([])

    def set_projects(self, projects):
        self.projects = list(projects)
        self.projectsChanged.emit(self.projects)

    def set_project(self, project):
        self.project = project
        self.projectChanged.emit(project)
