# 卫戍协议助手

配合《明日方舟》卫戍协议·规程使用的 Windows 桌面助手，优先适配官方 PC 端。当前版本 **0.1.14**。

## 下载与启动

在 [Releases](../../releases) 下载 `GarrisonAssistant-0.1.14-Windows-x64.zip`，完整解压后运行 `卫戍协议助手.exe`。保留同目录的 `_internal` 和 `第三方许可`。

便携发行包只有程序、运行资源与必要许可证，不包含使用说明、更新记录、设计说明、预览或验证报告。个人对局与 API 设置保存在本机用户目录，未包含在发行包中。

## 功能

- 四列干员图鉴，核心盟约、附加盟约与作用按钮筛选，详情分页及普通 / 精锐切换。
- 阵容与盟约计算、技能与装备建议、商店晋升、资金规划、攻略参考及阵容保存分享。
- PRTS 原始盟约图标识别开局信息；按盟约推算禁用干员，提供单人选组建议。
- 支持核心全部启用及不同数量的附加盟约禁选。悬浮终端可发起局内禁选复核，保留当前回合、资金、阵容和装备。
- 战场小人数据库比对、商店识别、干员与装备追踪和商店高亮。
- 半透明悬浮终端、最小化浮动入口、自定义快捷键，以及可独立关闭的自定义 API 回合教练。
- 未启用 AI 时使用本地攻略；启用后将已确认局面、禁选约束与相关攻略材料发给所配置服务。

助手只读取画面和提供建议，不替玩家购买、部署或开始对局。

## 源码与资源

`GarrisonAssistant-0.1.14-CompleteSource.zip` 包含完整桌面源码、测试、构建工具、游戏资料数据库、头像与立绘库、战场小人库、PRTS 盟约图标库、识别索引、动画模板和回放素材。

仓库中可直接审阅源码与较小资源。超过 Git 单文件限制的资源随完整源码包提供；开发和构建建议使用完整源码包解压后的目录。

需要 Windows、Python 3.13；部分规则对照检查另需 Node.js。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r desktop\requirements.txt
.venv\Scripts\python -m pip install --no-deps -r desktop\requirements-capture.txt
.venv\Scripts\python desktop\app.py
.venv\Scripts\python -m pytest desktop\tests -q
.venv\Scripts\python desktop\build_release.py
```

更多使用与构建信息见 [desktop/README.md](desktop/README.md) 和 [使用说明](desktop/使用说明.txt)。

## 验证范围

0.1.14 通过 159 项自动测试、38 项开局更新专项检查、33 项冻结程序检查，以及历史截图回放。新的低难度、局内信息布局与反复选组场景使用合成素材和离屏交互测试，尚未新增实机验证；这些结果不代表所有游戏场景的识别准确率或攻略胜率。

## 素材来源

资料和游戏图片来源于 PRTS Wiki；攻略来源及作者署名保留在攻略材料中。游戏素材归原权利人所有，PRTS 文字和第三方软件依各自许可使用。发行包保留必要许可证与来源说明。
