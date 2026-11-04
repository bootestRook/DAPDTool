# DAPD 任务工具

Windows 桌面工具，用于选择 DAPD 项目、任务组与父任务，创建空任务或按自建模板批量创建多层任务。

在 [Releases](https://github.com/bootestRook/DAPDTool/releases/latest) 下载 `DAPDTool.Desktop-win-Setup.exe` 后运行。无需安装 Python，不调用 AI。

打开“更新与共享”可在软件内下载程序更新，或单独同步共享模板和素材。首次启动无默认模板；每位用户填写自己的 DAPD API Key。

详细使用与发布说明见 [README-DAPD.md](README-DAPD.md)。

## 构建

需要 Windows x64、Python 3.13、.NET SDK 10。

```powershell
python -m venv .venv-desktop
.\.venv-desktop\Scripts\python.exe -m pip install -r requirements-desktop.txt
dotnet tool install vpk --version 1.2.161 --tool-path .tools
.\.venv-desktop\Scripts\python.exe -m unittest discover -s tests
.\.venv-desktop\Scripts\python.exe build_desktop.py
```

发布者递增 `dapd_tool/__init__.py` 的 VERSION、填写 RELEASE-NOTES.md 并推送代码，然后在 GitHub **Actions → Build and publish Windows → Run workflow** 完成测试、构建和发布。也可本机构建后运行 `publish_release.py app`。
内容包由软件导出，运行 `publish_release.py content 内容包路径` 发布。发布工具自动更新仓库的 `updates.json`，客户端读取此静态索引，无需 GitHub API 配额或登录。发布后运行 `git pull --ff-only` 取回索引提交。发布工具只使用发布者机器或 CI 的凭据，客户端不包含 GitHub Token。
