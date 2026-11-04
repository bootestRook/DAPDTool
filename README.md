# DAPD 任务工具

Windows 桌面工具，用于选择 DAPD 项目、任务组与父任务，创建空任务或按自建模板批量创建多层任务。

在 [Releases](https://github.com/bootestRook/DAPDTool/releases/latest) 下载 `DAPD任务工具-版本号-Windows-x64.zip`，完整解压后双击根目录的 `DAPD任务工具.exe`。无需安装程序或 Python，不调用 AI。

打开“更新与共享”可在软件内下载程序更新，或单独同步共享模板和素材。首次启动无默认模板；每位用户填写自己的 DAPD API Key。

详细使用与发布说明见 [README-DAPD.md](README-DAPD.md)。

## 代码组织

开发规则见 [AGENTS.md](AGENTS.md)。`dapd_desktop.py` 只负责启动；`dapd_tool/ui/main_window.py` 组装窗口并连接信号。
`ui/pages/`、`ui/dialogs/`、`ui/widgets/` 分别放功能页面、弹窗和可复用控件。账号与项目选择由 `Session` 管理，批次执行由 `JobController` 管理，后台操作由 `ActivityState` 统一登记。
业务、API 和存储模块放在 UI 之外，不依赖 Qt。页面通过信号协作，不读取其他页面或主窗口的内部状态。

```powershell
.\.venv-desktop\Scripts\python.exe -X utf8 scripts/check_structure.py
.\.venv-desktop\Scripts\python.exe -X utf8 -m unittest discover -s tests
```

结构检查会阻止超过 500 行的手写源文件、导入循环和跨层反向依赖，并提示超过 300 行的文件、60 行的函数及 300 行的类进行职责审查。
现有较长的任务浏览/编辑构造函数负责连续的控件布局；负责人选择模块包含同一控件的绘制、弹层和按钮。业务中的较长函数负责一个完整的创建、保存或包校验流程，构建入口负责连续打包流程；这些审查提示不作为自动豁免，后续修改仍需复核。
提交和 PR 会运行结构检查，本地构建及发布流水线也执行同一检查。打包源码递归包含 UI 子包、测试夹具与检查脚本。

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
