---
name: DAPD 桌面工具
description: 面向任务层级编辑与批量创建的原生 Windows 工具
colors:
  primary: "#146979"
  primary-hover: "#0f5866"
  background: "#f4f6f8"
  surface: "#ffffff"
  text: "#253440"
  muted: "#566875"
  heading: "#183c4a"
  focus: "#147788"
  selection: "#d8edef"
  input-border: "#bdcad1"
  button-border: "#b9c6cd"
  button-hover: "#edf3f5"
  button-pressed: "#dce9ed"
  notice-background: "#e9f2f3"
  notice-text: "#244e58"
  disabled-background: "#edf0f2"
  disabled-text: "#78868e"
typography:
  headline:
    fontFamily: "Microsoft YaHei UI"
    fontSize: "20pt"
    fontWeight: 600
  title:
    fontFamily: "Microsoft YaHei UI"
    fontSize: "12pt"
    fontWeight: 600
  body:
    fontFamily: "Microsoft YaHei UI"
    fontSize: "10pt"
rounded:
  field: "4px"
  button: "5px"
  notice: "6px"
spacing:
  compact: "12px"
  regular: "18px"
  page-top: "20px"
  dialog: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.button}"
    padding: "7px 14px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.button}"
    padding: "7px 14px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    rounded: "{rounded.field}"
    padding: "7px 9px"
  notice:
    backgroundColor: "{colors.notice-background}"
    textColor: "{colors.notice-text}"
    rounded: "{rounded.notice}"
    padding: "12px"
  navigation:
    textColor: "{colors.muted}"
    padding: "12px 25px"
  list-selection:
    backgroundColor: "{colors.selection}"
    textColor: "{colors.heading}"
    padding: "7px 4px"
---

# DAPD 桌面工具界面

## Overview

**Creative North Star: "浅色原生任务工作台"**

范围仅为独立 DAPD 工具，依据 `dapd_tool/ui.py`、`updates_ui.py`、`content_editor.py` 与 `media.py` 的当前实现记录。用户已确认 Python + PySide6 的原生 Windows Qt Widgets 方案；以浅色、系统中文字体和直接操作支撑办公屏幕中的高频任务管理。模板主任务与各级子任务均支持固定描述、内嵌图片和附件。

采用 Operate 模式，标准 Qt 控件与 Fusion 样式。DESIGN_VARIANCE=3，MOTION_INTENSITY=1，VISUAL_DENSITY=5。无装饰图片、无自定义动画。方向脚本已运行（91dbc398）；视觉方向由已确认的原生工具方案与既有桌面风格约束。网页检测器不适用于此界面。

**Key Characteristics:**

- 浅灰背景、白色操作区与单一青绿主色。
- 标准原生控件、清楚的文字状态和可见键盘焦点。
- 中等信息密度、可调分栏和可伸展内容区。
- 必要说明常显，所有悬停文字说明均禁用。

## Colors

青绿色用于主要操作、选中标签下划线与进度；浅灰底色承托白色输入和树形列表。正文、次要正文、标题分层清晰；选中行使用淡青底与深色文字。键盘焦点有独立边框颜色。

输入占位文字显式使用不透明的 `muted` 色，在白色输入背景上的对比度为 5.78:1。必要说明使用常显正文，不能依赖占位文字或悬停。

**The Visible Status Rule.** 状态必须使用具体文字说明；颜色、进度条和标签下划线只提供辅助识别。

## Typography

统一使用 Microsoft YaHei UI（10pt）；页面主标题（20pt、600 字重），区域标题（12pt、600 字重）。普通说明及内容编辑区的长节点标题按可用宽度换行，保留中文操作名称与完整状态文本。

## Layout

主窗口默认 1120×800，最小 920×680。外边距为左右 28px、顶部 22px、底部 20px；主要组件间距 12–18px，弹窗内容边距 22–24px。主内容随窗口伸展，模板和记录区域支持拖动分栏。模板编辑默认 1120×760、最小 980×680；创建预览默认 1050×720，两者均采用左侧任务树、右侧节点内容的可调分栏。

顶部是标题、连接状态及连接操作；中部固定四个标签：创建任务、我的模板、创建记录、更新与共享。底部常驻任务进度条与状态文本，创建期间显示停止按钮。创建流程按归属、内容、预览的顺序排列。

更新页沿用页面顶部留白（20px），以纵向区域分别展示程序与共享内容，每区都有标题、操作按钮、版本状态和可伸展的只读更新说明；页内进度与状态对应更新操作。导出共享内容使用独立原生弹窗，默认 600×560，内容边距 24px，以模板勾选列表、版本、更新说明和底部操作组成。

## Elevation & Depth

采用平面布局，以背景色、细边框、留白和选中状态区分区域，无自定义阴影。核对和编辑使用独立 Qt 模态弹窗。

## Shapes

按钮圆角 5px，输入与列表圆角 4px，常显说明区域圆角 6px。按钮通常使用 1px 边框，焦点状态加粗到 2px；以清晰的控件边界支持密集操作。

## Components

- **归属选择**：项目、任务组和可选父任务逐级选择。项目与任务组各有粘贴链接入口，支持 DAPD 复制的整段文字，并按实际 ID 定位归属。父任务选择弹窗内直接接受标题关键词、任务链接、任务 ID 或带链接的整段任务文字，并校验当前项目与任务组归属。
- **创建输入与预览**：空任务与模板批量创建使用各自输入区域；批量标题每行一个，数量实时显示。预览弹窗呈现目标归属、完整任务树、任务总数及图片和附件数量；选中节点即可只读查看其描述、图片和附件，确认按钮明确显示将创建的数量。
- **模板树与内容**：初始库为空且常显新建指引。树支持同级、子级、改名、删除、上下移动、升降级；选中主任务或任意子任务，右侧分别编辑固定文字、光标位置插图和附件。节点切换保留内容，未保存修改退出时明确确认。预览和记录复用相同层级表达。
- **模板来源与编辑**：共享条目使用“共享 · ”前缀，管理列表同时显示内容版本。选中共享模板时编辑与删除禁用，“复制为个人模板”保留为明确入口；双击共享条目也说明先复制再编辑。个人模板和共享模板均可用于创建，初始界面仍无默认模板。
- **图片与附件**：图片以移除元数据、最长边不超过 4096 像素的本地副本保存，按比例显示在描述中，原图保持不变。附件列表常显文件名和实际副本大小，小于 1024 字节显示 B，其余显示一位小数 KB；添加与移除使用明确按钮。文件选取后保存本地副本，创建时才上传，状态说明直接可见。
- **记录与恢复**：上方列出批次，下方显示逐项任务状态和 ID。支持打开任务、导出记录及继续批次。停止等待当前请求结束并保留进度；任务创建结果待核对时，可关联已创建任务或确认未创建。上传结果待核对时，继续会先查询已有文件，无法确认则保留待核对状态；只有用户核对文件不存在后才能重置上传。
- **更新与共享**：顶部常显公开仓库来源和每日启动检查说明，右侧提供“检查更新”。版本检查匿名读取公开仓库 `main/updates.json` 静态索引，资源仍从 GitHub Releases 下载；客户端无需 GitHub Token，也不消耗匿名 REST API 配额。程序与内容版本分别显示，有可用更新或待安装程序时标签显示“更新与共享（有更新）”。程序下载并校验后，按钮改为“重启并安装更新”；当前任务或网络操作进行时禁用重启并常显原因，结束后按钮与可安装说明同步恢复。重启前弹窗说明保留已保存的数据，以及尚未提交的标题需要重新填写。共享内容同步无需重启，页面直接说明共享模板只读、复制后可编辑，以及同步只更新共享库。
- **共享内容导出**：只列出可勾选的个人模板，顶部常显包内包含描述、图片与附件及公开分发含义。底部显示校验与导出状态；后台工作线程处理文件期间禁用输入、取消和导出，关闭操作也等待完成。导出空共享库需确认，完成后显示保存位置和发布入口说明。
- **状态与按钮**：未连接、未选择、加载、禁用、错误和完成均有具体文本。主要操作用青绿色，次要操作用白底；鼠标经过仅改变控件颜色，不显示解释文字。所有 Qt Tooltip 事件由应用级过滤器禁止。

**The Action Matches State Rule.** 按钮可用状态、动作名称与紧邻说明必须同步；操作结束后不得保留仍需等待的文字。

## Do's and Don'ts

- **Do** 保持可见键盘焦点、明确的任务归属、真实进度与先预览后提交的操作顺序。
- **Do** 让说明直接显示在界面中，错误恢复入口与相关记录放在一起。
- **Don't** 添加默认任务模板、装饰图片、网页视觉套路或悬停文字说明。
- **Don't** 将本文件的界面约定扩展到原有飞书控制器。
