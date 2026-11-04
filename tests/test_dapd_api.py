import json
import threading
import httpx
from dapd_api import DapdClient
from dapd_tool.engine import run_job
from creation_fixture import CreationCase, DEST

class DapdApiTests(CreationCase):
    def test_actual_http_adapter_end_to_end(self):
        def handler(request):
            name = request.url.path.split("/")[-1]
            data = json.loads(request.content) if request.method == "POST" else json.loads(request.url.params["input"])
            if name == "project.getProjects":
                value = [{"id": "p", "name": "项目"}]
            elif name == "taskGroup.getTaskGroups":
                value = [{"id": "g", "name": "任务组", "status": "in_progress"}]
            elif name == "task.getTaskById":
                value = dict(DEST, id="container", title="总单") if data["id"] == "container" else self.tasks[data["id"]]
            elif name == "task.createTask":
                value = self.create(data)
            else:
                self.fail(name)
            return httpx.Response(200, json={"result": {"data": value}})
        api = DapdClient("test", transport=httpx.MockTransport(handler))
        self.addCleanup(api.close)
        job = run_job(self.store, api, self.add(), threading.Event())
        self.assertEqual(job["status"], "completed")
        self.assertEqual(len(self.tasks), 10)
