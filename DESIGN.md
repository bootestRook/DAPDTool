---
name: DAPD 桌面工具
description: 面向任务层级、富文本模板、批量创建与任务编辑的 Windows 工具
colors:
  primary: "#146979"
  update-notification: "#c9363e"
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
  editor-text: "#202124"
  editor-muted: "#60646c"
  editor-line: "#ececec"
  editor-focus: "#1677ff"
  editor-selection: "#3468db"
  editor-format-active: "#404040"
  assignee-tab-active: "#252525"
  assignee-tabs-border: "#d8dfe3"
  avatar-background: "#e7f1f4"
  avatar-initial: "#226274"
  assignee-marker: "#168bd2"
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
  editor-body:
    fontFamily: "Microsoft YaHei UI, sans-serif"
    fontSize: "14px"
    lineHeight: 1.65
  editor-control:
    fontFamily: "Microsoft YaHei UI, sans-serif"
    fontSize: "12px"
rounded:
  field: "4px"
  button: "5px"
  notice: "6px"
  assignee-popup: "8px"
  assignee-tab: "13px"
  assignee-search: "7px"
  assignee-tabs: "16px"
  editor-popup: "5px"
  editor-control: "3px"
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
  editor-format-toolbar:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.editor-text}"
    typography: "{typography.editor-control}"
    rounded: "{rounded.editor-popup}"
    padding: "3px 5px"
  editor-format-active:
    backgroundColor: "{colors.editor-format-active}"
    textColor: "{colors.surface}"
    rounded: "{rounded.editor-control}"
    size: "24px"
  editor-insert-menu:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.editor-text}"
    rounded: "{rounded.editor-popup}"
    padding: "4px"
    width: "256px"
  editor-content:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.editor-text}"
    typography: "{typography.editor-body}"
    padding: "16px 28px 36px 42px"
  assignee-popup:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    rounded: "{rounded.assignee-popup}"
    padding: "12px 12px 10px"
    width: "360px"
    height: "520px"
  assignee-tab-active:
    backgroundColor: "{colors.assignee-tab-active}"
    textColor: "{colors.surface}"
    rounded: "{rounded.assignee-tab}"
    padding: "4px 8px"
  assignee-search:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    rounded: "{rounded.assignee-search}"
    padding: "6px 9px"
  assignee-tabs:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.assignee-tabs}"
    padding: "3px"
    height: "36px"
---

# DAPD 桌面工具界面

## Overview

**Creative North Star: "浅色原生任务工作台"**

范围仅为独立 DAPD 工具，依据 `dapd_tool/ui/main_window.py`、`ui/pages/`、`ui/dialogs/`、`ui/widgets/` 与 `editor/src` 的当前实现记录。用户已确认 Python + PySide6 的 Windows Qt Widgets 方案；以浅色、系统中文字体和直接操作支撑办公屏幕中的高频任务管理。模板主任务与各级子任务均可配置默认负责人、富文本描述、内嵌图片和附件。模板与已有任务共用支持头像、搜索和组织范围切换的原生负责人选择器。

采用 Operate 模式，窗口、表单与列表使用标准 Qt 控件和 Fusion 样式；描述区嵌入本地打包的 BlockNote 编辑器，沿用桌面字体，并按用户提供的 DAPD 截图复现白色画布、行首添加和选区格式浮层。编辑器的局部配色不改变桌面青绿主色。DESIGN_VARIANCE=3，MOTION_INTENSITY=1，VISUAL_DENSITY=5。无装饰图片、无自定义动画。保留已确认的原生工具视觉方向（方向脚本记录：91dbc398）。

**Key Characteristics:**

- 浅灰背景、白色操作区与单一青绿主色。
- 标准原生控件、清楚的文字状态和可见键盘焦点。
- 中等信息密度、可调分栏和可伸展内容区。
- 富文本格式状态、任务层级与时间信息直接可见。
- 必要说明常显，所有悬停文字说明均禁用。

## Colors

青绿色用于主要操作、选中标签下划线与进度；浅灰底色承托白色输入和树形列表。正文、次要正文、标题分层清晰；选中行使用淡青底与深色文字。键盘焦点有独立边框颜色。

负责人弹层的局部范围标签以深灰底、白字表示选中；人员行使用浅灰选中底和蓝色勾选标记。头像不可用时显示淡青底首字，姓名和部门始终使用正文与次要正文色，不能只靠头像辨认人员。

描述区局部使用白色画布、`editor-text` 正文和 `editor-line` 细边框；格式浮层同为白底，启用的格式按钮使用 `editor-format-active` 深灰底与白色图标。开关及键盘焦点使用 `editor-focus` 蓝色，文字选区使用 `editor-selection` 蓝底白字；这些局部状态不复用原生列表的淡青选中底。

输入占位文字显式使用不透明的 `muted` 色，在白色输入背景上的对比度为 5.78:1。必要说明使用常显正文，不能依赖占位文字或悬停。

**The Visible Status Rule.** 状态必须使用具体文字说明；颜色、进度条和标签下划线只提供辅助识别。

## Typography

桌面控件统一使用 Microsoft YaHei UI（10pt）；页面主标题（20pt、600 字重），区域标题（12pt、600 字重）。嵌入编辑器正文使用同一字体（14px、1.65 行高），选区格式浮层使用较紧凑的文字（12px），插入菜单条目标题为 13px。普通说明及内容编辑区的长节点标题按可用宽度换行，保留中文操作名称与完整状态文本。富文本内容保留自身的标题层级和字号，不能改变应用界面的字号层级。

负责人弹层沿用桌面字体与正文字号；“当前”“常用”“全部”分段标题使用同一字体的 9pt 粗体，不引入独立字体体系。

## Layout

主窗口默认 1120×800，最小 920×680。外边距为左右 28px、顶部 22px、底部 20px；主要组件间距 12–18px，弹窗内容边距 22–24px。主内容随窗口伸展，模板和记录区域支持拖动分栏。模板编辑默认 1120×760、最小 980×680；创建预览默认 1050×720，两者均采用左侧任务树、右侧节点内容的可调分栏。任务编辑默认 1220×820、最小 1000×700，左侧为可滚动字段表单，右侧为负责人、描述及附件；只读项目名称保持紧凑行高，不吸收表单的剩余高度。

顶部是标题、连接状态及连接操作；中部依次固定五个标签：创建任务、我的模板、创建记录、更新与共享、我创建的任务。底部常驻任务进度条与状态文本，创建期间显示停止按钮。创建流程按归属、内容、预览的顺序排列；批量输入使用可伸展的两列表格，逐行展示主任务名称与所用模板。

描述区展开时最小高度为 200px，收起时原生容器压缩至 48px，展开或重新加载节点后恢复伸展；顶部仅显示可收起的“描述”标题及“媒体自动横排”开关，正文留出行首“+”入口的位置。点击“+”或输入 `/` 打开 256px 宽、随可用高度滚动的分组插入菜单；仅在选择文字时显示紧凑格式浮层。480px 及以下宽度时浮层可换行且受视口宽度约束，横排媒体改为逐项占满一行。附件标题和添加入口保留，附件列表仅在存在文件时占用空间（45–90px）。任务树使用横向滚动容纳元数据，创建时间、截止时间、更新时间三列各预留 160px，时间格式为 `YYYY-MM-DD HH:mm`。

更新页沿用页面顶部留白（20px），以纵向区域分别展示程序与共享内容，每区都有标题、操作按钮、版本状态和可伸展的只读更新说明；页内进度与状态对应更新操作。导出共享内容使用独立原生弹窗，默认 600×560，内容边距 24px，以模板勾选列表、版本、更新说明和底部操作组成。

负责人选择在字段下方打开紧凑弹层（常规屏幕 360×520px），空间不足时移到字段上方并限制在屏幕内。上部依次为搜索、范围标签和可滚动的部门或分组入口，中部为人员列表，底部常显当前项目名或“全部用户”。人员行高 40px、分段标题高 30px，头像显示为 24px 圆形；组织入口区最高 150px，保留人员列表的可用空间。

## Elevation & Depth

任务列表的“高亮我创建的任务”勾选项默认关闭，与筛选框同排。开启时按任务 ID 精确标记归属，使用 `notice-background` 浅青底、`notice-text` 正文色、加粗标题和“我创建的”前缀；其他创建者的父任务不随子单高亮。切换不改变筛选、展开或选中状态，不提供悬停说明。

原生窗口采用平面布局，以背景色、细边框、留白和选中状态区分区域；核对和编辑使用独立 Qt 模态弹窗。描述区的插入菜单和选区格式浮层局部使用 `0 3px 12px rgb(0 0 0 / 15%)` 柔和阴影，表明其覆盖正文的临时操作层级；静止画布保持平面。

## Shapes

按钮圆角 5px，输入与列表圆角 4px，常显说明区域圆角 6px。按钮通常使用 1px 边框，焦点状态加粗到 2px；以清晰的控件边界支持密集操作。

负责人选择器局部沿用 DAPD 参考的柔和形状：搜索框采用 `assignee-search` 圆角，范围标签外框采用 `assignee-tabs` 圆角及 `assignee-tabs-border` 细边框。这些令牌仅用于该弹层，通用输入与按钮继续使用原有形状。

## Components

- **归属选择**：项目、任务组和可选父任务逐级选择。项目与任务组各有粘贴链接入口，支持 DAPD 复制的整段文字，并按实际 ID 定位归属。父任务选择弹窗内直接接受标题关键词、任务链接、任务 ID 或带链接的整段任务文字，并校验当前项目与任务组归属。
- **创建输入与预览**：空任务与模板批量创建使用各自输入区域。批量表格每行独立填写主任务名称并选择模板，同一批次可以混用模板；顶部模板选择用于新增行的默认值。使用“+ 添加任务”逐行添加，或指定数量后点击“按数量添加”，并通过“删除所选行”移除条目。数量实时显示。预览弹窗呈现目标归属、完整任务树、任务总数及图片和附件数量；选中节点即可只读查看其负责人、描述、图片和附件，确认按钮明确显示将创建的数量。
- **模板树与内容**：初始库为空且常显新建指引。树支持同级、子级、改名、删除、上下移动、升降级；选中主任务或任意子任务，右侧分别编辑默认负责人、富文本描述、光标位置插图和附件。负责人范围沿用创建任务页选中的项目，尚未选择项目时使用全部用户，各级节点独立保存。节点切换保留内容，未保存修改退出时明确确认。预览和记录复用相同层级表达。
- **负责人选择器**：模板节点与任务编辑共用原生单选弹层，字段显示头像与姓名，打开后聚焦“搜索用户…”。搜索支持姓名、部门名、项目成员分组名的片段、拼音全拼与首字母，多词共同筛选当前范围。“全部”按需显示“当前”“常用”“全部”及数量；“常用”是当前 API 账号与项目范围内最近选择的最多 10 人。“无负责人”在“全部”且搜索为空时清除选择。“按部门”逐级进入部门并显示路径、人数及“返回上一级部门”；“按分组”切换项目成员分组或“未分组”，未选择项目时常显先选项目的说明。任务编辑始终使用任务所属项目成员。真实头像异步加载为移除元数据的 64×64 缩略图，不可用时显示姓名首字。搜索无匹配和范围无成员分别显示明确空态。上下方向键跳过分段标题移动选择，Enter 确认，Escape 关闭并返回字段焦点；点击人员立即选定并关闭。选中标记与可见焦点支持键盘核对，禁止任何悬停文字说明。
- **富文本编辑器**：描述区使用本地打包的 BlockNote，交互和局部外观以用户提供的 DAPD 截图为准。点击“描述”标题收起或展开正文；“媒体自动横排”控制图片、视频、音频块的两列排列，状态通过 HTML 的 `data-media-layout="row"` 包裹层保存并在读取时恢复。行首“+”和 `/` 打开同一插入菜单，按“基础 / 媒体 / 折叠 / 其他”分组：文本、H1–H6、有序列表、无序列表、检查清单、代码块、表格、引用、分割线；图片、视频、音频、文件；可折叠 H1–H3 和可折叠列表；表情。选择文字时出现紧凑图标格式浮层，格式状态随选区同步，启用按钮为深灰底白图标。支持直接粘贴图片，媒体插入由菜单进入；无常显顶部工具栏和原生独立“插入图片”按钮。错误直接显示在编辑区。只读预览隐藏编辑入口及媒体排列开关，保留描述收起与展开。禁止通过悬停显示库默认提示或 HTML `title` 文字。
- **模板来源与编辑**：共享条目使用“共享 · ”前缀，管理列表同时显示内容版本。选中共享模板时编辑与删除禁用，“复制为个人模板”保留为明确入口；双击共享条目也说明先复制再编辑。个人模板和共享模板均可用于创建，初始界面仍无默认模板。
- **模板文件**：“我的模板”在独立操作行提供“导入模板文件”和“导出所选模板”，与“导出共享内容包”明确区分。文件使用 `.dapd-template` 扩展名，包含所选模板及素材；同名导入以个人副本呈现。
- **图片与附件**：图片以移除元数据、最长边不超过 4096 像素的本地副本保存，按比例显示在描述中，原图保持不变。描述中的视频、音频和文件保存为独立文件素材并注册本地地址，和图片一起以描述素材上传，远程地址写入描述后再提交任务；它们不混入下方附件列表。有附件时列表常显文件名和实际副本大小，小于 1024 字节显示 B，其余显示一位小数 KB；无附件时折叠空列表。添加与移除使用明确按钮。文件选取后保存本地副本，模板内容在创建时上传，任务编辑在“保存更新”时上传；状态说明与当前动作一致。
- **我创建的任务**：使用可调分栏，左侧“我的项目”提供项目搜索及项目列表，每项显示项目名和本次会话已读的个人任务数，部分读取标明“未读完”；右侧标题显示当前项目，提供“读取项目任务 / 刷新项目任务”、任务筛选及阶段进度。读取时显示“取消读取”，取消等待当前请求结束，并明确说明是否为部分结果。切换项目使用会话缓存，刷新失败保留原数据。右侧用 Qt 模型视图展示任务层级、任务组、负责人、状态、优先级、创建时间、截止时间、更新时间、创建者与任务 ID，项目归属由标题和左侧选择表达。支持全部展开、全部收起、双击和“编辑所选任务”。为补全层级读取的其他创建者父任务带有“父任务，仅展示”文字，不可编辑；筛选以线性遍历保留匹配任务的父级上下文。未选择项目、无任务和无匹配各有常显说明。
- **任务编辑**：标题和创建、更新时间位于弹窗顶部；左侧表单包括只读项目、任务组、父任务、状态、优先级、截止时间、标签、抄送成员、关联任务和适用的自定义字段，右侧编辑负责人、描述及新增附件。点击“保存更新”才写入，保存前检查并发变更，完成后回读并显示确认文字；未保存退出需确认。工作流任务的状态控件禁用，常显文字指向 DAPD 中的节点流转；已有远程附件仅列出名称，删除仍在 DAPD 中操作。此界面不声称覆盖 DAPD 的全部编辑能力。
- **记录与恢复**：上方列出批次，下方显示逐项任务状态和 ID。支持打开任务、导出记录及继续批次。停止等待当前请求结束并保留进度；任务创建结果待核对时，可关联已创建任务或确认未创建。上传结果待核对时，继续会先查询已有文件，无法确认则保留待核对状态；只有用户核对文件不存在后才能重置上传。
- **更新与共享**：顶部常显公开仓库来源和每日启动检查说明，右侧提供“检查更新”。版本检查匿名读取公开仓库 `main/updates.json` 静态索引，资源仍从 GitHub Releases 下载；客户端无需 GitHub Token，也不消耗匿名 REST API 配额。程序与内容版本分别显示，有可用更新或待安装程序时标签显示“更新与共享（有更新）”，右侧显示 8px 的 `update-notification` 红点，无悬停说明。更新状态由页面发出信号，主窗口只组装标签与红点。程序下载校验完成后显示原生弹窗，“立即重启（5 秒后自动）”按钮每秒更新并在到时执行，另有“稍后重启”。后台任务进行时按钮禁用、倒计时暂停并说明原因，全部结束后重新计时 5 秒；安装前再次检查运行状态。弹窗常显已保存数据保留、未提交输入需重填的说明。选择稍后可通过“重启并安装更新”重新打开提示。共享内容同步完成后弹出成功提示，立即可用，无需重启；页面直接说明共享模板只读、复制后可编辑，以及同步只更新共享库。
- **共享内容导出**：只列出可勾选的个人模板，顶部常显包内包含描述、图片与附件及公开分发含义。底部显示校验与导出状态；后台工作线程处理文件期间禁用输入、取消和导出，关闭操作也等待完成。导出空共享库需确认，完成后显示保存位置和发布入口说明。
- **状态与按钮**：未连接、未选择、加载、禁用、错误和完成均有具体文本。主要操作用青绿色，次要操作用白底；鼠标经过仅改变控件颜色，不显示解释文字。所有 Qt Tooltip 事件由应用级过滤器禁止；嵌入编辑器也禁用库 Tooltip 并移除原生悬停文字属性。

**The Action Matches State Rule.** 按钮可用状态、动作名称与紧邻说明必须同步；操作结束后不得保留仍需等待的文字。

## Do's and Don'ts

- **Do** 保持可见键盘焦点、明确的任务归属、真实进度与先预览后提交的操作顺序。
- **Do** 让说明直接显示在界面中，错误恢复入口与相关记录放在一起。
- **Do** 保持选区格式浮层与所选文字格式同步，描述区的添加和格式操作按需展开；区分模板的“默认负责人”和已有任务的“负责人”，让上传说明对应“创建”或“保存更新”。
- **Do** 在负责人选择器中常显人员范围，搜索与组织筛选保持同一范围；头像与姓名一起展示，空态说明当前范围的实际结果。
- **Don't** 添加默认任务模板、装饰图片、网页视觉套路或悬停文字说明。
- **Don't** 将本文件的界面约定扩展到原有飞书控制器。
