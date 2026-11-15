# 卫戍协议助手

Windows 桌面版 0.1.23，Python 3.13 / PySide6。用户说明见 [使用说明.txt](使用说明.txt)。便携发行包只保留程序、运行资源和必要许可证，使用说明与验证记录保留在源码中。

0.1.23 点击“新对局”时同步清空本局干员与装备追踪、所有置顶项和手动勾选、商店追踪标记，并保存空名单。悬浮终端底部也提供“新对局（一键清空）”，共用相同重置逻辑并保持终端打开。自动检测到新对局也执行同一清理；暂停识别或刷新建议仍保留本局追踪。后台验证：`python desktop/verify_tracking_ui.py`。

0.1.22 在“设置 → 画面识别 → 稳定性与频率”分别配置禁选和商店的连续一致帧数（1–6 帧）；1 帧表示关闭连续帧等待，仍保留单帧可信度与完整性检查。商店追踪标记沿用商店帧数，其他数值与阵容独立设置。旧配置自动继承原来的帧数；修改后重新计数，保留已确认禁选、阵容和追踪名单。后台验证：`python desktop/verify_stability_settings.py`。

0.1.21 将主导航整理为首页、资料图鉴、阵容攻略、对局工具、设置。首页提供绑定并同步、AI 开关、禁选与阵容确认；图鉴合并盟约、装备和策略资料；识别校准与 API 配置移入设置分页。手动追踪支持盟约、作用、类型与等阶按钮筛选，保留已追踪状态。后台工作流验证：`python desktop/verify_workspace.py`，不会启动可见窗口、截取游戏或调用真实服务。

0.1.20 从第 3 回合开始主动推荐可追踪阵容，不再等待核心到手或商店齐全。名单中的“追踪阵容”会加入推荐干员并保留已有追踪；装备可单选，路线可单独锁定。禁选、策略和获取条件仍然有效；没有满足条件的已收录攻略时不会强行凑队。新增后台验证：`python desktop/verify_early_lineup.py`。

0.1.19 增加漏检商品名称的局部复查，确认商品可独立更新并注明待确认卡位。实时识别先更新商店，战场小人另行处理；连续帧校验和过期检查继续保留。窗口采集默认请求关闭黄色边框，系统不支持时回退，实际边框表现尚未实测。本版使用保存画面与后台测试，没有操控游戏、启动可见程序或调用真实 AI。

0.1.18 修复阵容因短暂漏识别被排除的问题。漏识别、战斗阶段或收起商店时，最后确认的干员、位置、精锐与装备继续用于盟约和路线规划，界面及 AI 输入明确标为待核对；稳定重识别后自动恢复，确认移除或新对局才清理。通过本地规则与后台界面回放验证，未操作桌面或游戏，未调用真实 AI 接口。

0.1.17 修复 1 级 LEVEL 标签、渐淡罗马数字与灰色费用徽章漏读；按每帧定位验证升级后的调度面板和商店卡位，不依赖上一等级的位置。新增等级切换回放覆盖本次 1–4 级与历史 5、6 级真实样本。

0.1.16 用已精确抠图的右指表情替代商店金色框选，放在商品卡左侧标识区，避开名称和费用。跟随每帧卡位定位，保留原有逐商品稳定检查和取消追踪行为。画面暂不可用时明确提示自动重试。

0.1.15 增加本局攻略路线锁定，并修复商店追踪闪烁和开局禁选显示反复变化。稳定禁选固定展示；游戏切组须经新的完整稳定识别后更新。攻略锁定在主窗口和悬浮终端均可操作，随本局保存，禁选始终优先于锁定。

## 开发

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r desktop\requirements.txt
.venv\Scripts\python -m pip install --no-deps -r desktop\requirements-capture.txt
.venv\Scripts\python desktop\app.py
```

源代码默认从项目 `outputs` 中读取既有 JSON 与两份独立 SQLite 图片库。打包后从 `_internal/resources` 读取。原数据库不修改。
完整源码资源包另含战场小人数据库、盟约图标数据库、已编译的识别索引、待机动画模板和回放测试素材，可直接解压使用；无需读取开发者电脑上的个人目录。

```powershell
.venv\Scripts\python -m pytest desktop\tests -q
.venv\Scripts\python desktop\verify_recognition.py
.venv\Scripts\python desktop\verify_ui.py
.venv\Scripts\python desktop\build_release.py
.venv\Scripts\python desktop\package_distribution.py
```

`verify_ui.py` 使用隔离数据目录。可设置 `QT_QPA_PLATFORM=offscreen` 进行无窗口检查；脚本显式加载系统中文字体用于截图。

打包脚本移除从宿主 PATH 误收集的私有 ICU，使用 Windows 自带的 ICU API，同时统一随包 MSVC 运行库。发布前运行可执行文件的 `--self-check <report.json>`，确认冻结环境中 Qt、两份图片库、OCR 模型及关键窗口逻辑均能加载。

## 结构

- `garrison/core.py`：数据库、规则、序列费用核验、装备规则、状态与撤销。
- `garrison/recognition.py`：离线 OCR、名称匹配、严格头像相似度、区域校准、连续帧检查。
- `garrison/windows.py`：只读窗口截取、全局快捷键。
- `garrison/coach.py`：可取消的兼容 API 调用、调用限额与建议校验。
- `garrison/storage.py`：原子写入、本机 DPAPI 密钥、分享字段白名单。
- `garrison/ui.py` / `workspace.py` / `widgets.py`：主窗、五页任务布局、半透明面板、悬浮入口与控件。

## 已知边界

0.1.14 通过 159 项自动测试、38 项开局更新专项检查及冻结程序自检。包含可露希尔主题 1、5、6 级商店截图、两张开局截图和战场小人历史画面的离线回放；缩放、低难度和局内信息布局使用合成测试，不是新增实机验收。小人比对保持部分识别和待确认状态，不能由小人图像确定精锐；装备及不可见信息仍需核对。

开局盟约使用本地 PRTS 透明原图识别。支持核心全部启用、附加盟约不同禁用数量，以及在悬浮终端发起局内重新核对；局内确认保留回合、阵容、装备与资金。短暂漏读时保留已核验信息，新选组须重复完整核验后更新，不拼接缺失图标。

截取优先使用 Windows Graphics Capture 按 HWND 绑定窗口，兼容路径为 PrintWindow；没有截取整个桌面的回退。长时间稳定性、其他主题与推荐质量仍未验收。AI 为可独立关闭的自定义 Chat Completions 服务；个人 API 配置与密钥在本机保存，不随发布包上传。没有自动购买、注入、内存读取或操作游戏的代码。

截取依赖 [windows-capture 2.0.1](https://github.com/NiiightmareXD/windows-capture/tree/main/windows-capture-python)，单独以 `--no-deps` 安装，复用主依赖中的 headless OpenCV，避免两套 cv2 文件互相覆盖。

商店推荐是本地协同评分，不是胜率。替换分析比较盟约增减；技能与装备适配依据资料原文，未进行战斗数值模拟。自定义 API 当前支持 Chat Completions 协议。

## 设计参考与许可

[卫戍协议默认终端样张](https://prts.wiki/w/卫戍协议/终端主题一览)提供布局、边框和状态反馈参考；具体拆解与桌面适配见 [DESIGN.md](DESIGN.md)。[PRTS 表情套组](https://prts.wiki/w/表情套组)中的卫戍协议专用表情提供图标参考。新图标为生成素材，提示词与记录见 `assets/icon-generation.json`。

PRTS 文字遵循来源的 CC BY-NC-SA 3.0；游戏原图版权归权利人。随发行包附带第三方许可证，Qt/PySide6 动态库可在 `_internal` 替换为兼容版本。开发源码与构建步骤随项目交付。
