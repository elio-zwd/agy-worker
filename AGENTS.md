# 项目工作要求

这是 Windows 10 x64 的本地 AGY Worker，使用官方 MCP Python SDK。部署基准为 Python 3.13，包声明支持 Python 3.13～3.14。对外提供六个 MCP 工具（一个能力发现、五个任务工具）及两个只读资源。

调用链：Codex → 一次性 stdio Bridge → 常驻 Controller / 唯一 Runtime → AGY CLI → 私有 Broker → 已授权执行器。Controller 唯一持有 Runtime 与 runtime.lock。

## 接手顺序

1. 确认当前目录、分支和 `git status --short`；保留已有未提交修改，尤其是本机配置。
2. 阅读 `README.md`、`pyproject.toml` 和本文件，再按任务定位源码与测试。设计背景见 `docs/实施设计.md`，部署记录见 `docs/部署验收.md`；历史验收不等于当前环境已通过。
3. 先使用项目已有依赖与脚本，建立检查基线，再实施最小完整改动。初始化不默认重装依赖、重注册 MCP、重启 Controller 或清空任务证据。

## 架构与权限边界

- 报告和有意义的代码注释使用中文，PowerShell 使用 pwsh.exe。
- Codex 负责判断、源码分析和修复；AGY 编译任务只能执行与采集错误。
- 当用户要求“让 AGY/agy”执行本 Worker 已支持的编译、测试、日志、浏览器、图片或 Android UI 任务时，Codex 必须使用已注册的 `agy_worker` MCP；不得把正常任务改成 terminal/shell 直接调用 `agy`、`agy.exe`、`agy -p`，也不得先跑 `agy --help` 作为探测。MCP 不可用时应明确报告，不得静默回退。只有安装、更新、诊断 AGY CLI 本身或本仓库维护脚本明确需要时，才允许直接调用 CLI。
- 不开放任意 shell，不修改用户原项目，只在 data/sessions 的快照中执行。
- 权限在 hook 与私有 Broker 双重校验；当前没有通过系统级隔离验收，不能把它描述为安全沙箱。
- config/runtime.toml 是登记工作区与命令的唯一入口。AGY 不得修改这个文件。
- scripts/check.ps1 为权威检查入口。真实 AGY 验收会使用当前登录账号。
- 多 Bridge 必须共享同一 Controller；Bridge 退出不能停止 Runtime，Controller 重启不能自动重做未完成任务。
- data/、work/、.venv/ 和 vendor/browser/node_modules/ 不提交。
- 不删除或覆盖 C:/Users/70455/.gemini 下用户既有配置；仅管理 agy-worker-broker 条目。
- 源码写入与 shell 类型当前显式拒绝，不能通过添加兼容分支或移除检查来打开。

## 模块定位

| 位置 | 职责 |
|---|---|
| `src/agy_worker/server.py` | 公开 MCP 工具、只读资源和参数校验反馈 |
| `src/agy_worker/models.py`、`schemas/` | 请求模型与公开 JSON Schema |
| `src/agy_worker/controller*.py` | 常驻服务、本机通信协议、Bridge 客户端与启动协调 |
| `src/agy_worker/runtime.py` | 任务、会话、快照、授权与执行调度 |
| `src/agy_worker/broker.py`、`hook.py` | 私有执行入口与双重权限校验 |
| `src/agy_worker/processes.py`、`browser.py` | 进程树生命周期与浏览器执行 |
| `src/agy_worker/artifacts.py`、`logs.py` | 证据存取、脱敏与构建诊断提取 |
| `src/agy_worker/manage.py`、`scripts/` | 本机安装、接入、诊断与工具链适配 |
| `tests/` | 权限、路径、快照、Controller、进程与日志回归测试 |

## 常用命令

以下命令在仓库根目录通过 PowerShell 7 执行，Python 使用本项目 `.venv`。

```powershell
# 环境诊断：检查 AGY 必需参数与浏览器程序，结果写入 work/doctor.json。
pwsh.exe -NoProfile -File scripts/doctor.ps1

# 权威检查：源码编译检查与完整 pytest。
pwsh.exe -NoProfile -File scripts/check.ps1

# 按变更范围运行测试，例如 Controller 生命周期。
& ./.venv/Scripts/python.exe -m pytest -q tests/test_controller.py

# 修改请求模型后重新生成公开 Schema，并检查差异。
& ./.venv/Scripts/python.exe -m agy_worker.manage schemas
```

按任务需要使用以下维护入口，注意它们的实际副作用：

- 安装：`pwsh.exe -NoProfile -File scripts/install.ps1 -Python '<Python解释器完整路径>'`。创建或复用 `.venv`，安装锁定依赖与浏览器依赖，并执行诊断；不升级全局 Python。
- 注册：`pwsh.exe -NoProfile -File scripts/register.ps1`。修改 AGY 专用 Broker 和 Codex MCP 注册，并向 Codex `developer_instructions` 追加带边界标记的 AGY Worker 路由规则；既有用户指令必须保留。配置备份位于 `work/backups`，可能含敏感信息。
- Bridge 入口：`pwsh.exe -NoProfile -File scripts/start.ps1`。供 MCP 客户端使用；首个连接按需启动 Controller。
- 停止：`pwsh.exe -NoProfile -File scripts/stop.ps1`。会取消运行中的任务，后续工具调用可重新启动 Controller。
- 双 Bridge 验收：`& ./.venv/Scripts/python.exe scripts/verify-controller.py --config config/runtime.toml`。使用正式配置，可能启动常驻 Controller，结束后保持其运行。
- 真实任务验收：`scripts/run-task.py` 配合 `examples/` 请求文件；执行前检查登记工作区、命令和本轮授权，新的执行使用新的 `request_id`。

## 修改与完成要求

- 使用满足当前需求的简单、模块化实现；删除过时代码，不添加兼容层、migration 或 fallback。
- 注释使用简体中文，说明非显然的约束、并发、重试与生命周期原因；修改逻辑时同步修正失效注释。
- 修改公开请求时同步模型、生成 Schema、示例与相关说明；不得只修改生成文件。
- 修改权限、快照、取消或 Controller 生命周期时，补充或运行对应回归测试。最终执行 `scripts/check.ps1`；仅文档修改可检查命令准确性与差异，无需重复运行无关测试。
- `doctor.ps1` 和单元测试通过不代表真实 AGY、HBuilderX 或系统隔离验收通过。构建结果必须核对命令退出码与产物；Android 资源导出不等于 APK 打包或真机测试。
- 完成前检查 `git diff --check` 和工作区差异，报告改动、实际验证结果及未验证部分。提交信息使用 `英文类型: 中文说明`，例如 `docs: 完善项目初始化指南`。
