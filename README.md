# AGY Worker 本地部署

部署位置：`D:\My\_Elio\agy-worker`。宿主：Windows x64、PowerShell 7、Python 3.13。此安装复用已登录的 AGY CLI，并登记为 Codex 的 stdio MCP。

## 分工

Codex/GPT 负责需求、总控、判断、源码分析和核心修改。AGY 负责执行受控任务、读取高噪声内容、整理事实和证据。编译任务只采集错误原文与定位，不分析原因、不修代码。浏览器的 click 等细节只存在于 Worker 内部，不作为 Codex 的公开工具。

实际链路：Codex → 一次性 stdio Bridge → 常驻 Controller / 唯一 Runtime → 每轮独立 AGY CLI → 私有 Broker → 已授权执行器。Bridge 只处理 MCP 与本机转发；Controller 掌握命令、退出码、取消与证据，不能用 AGY 自称成功替代进程和产物验证。

### v0.3.1 Controller 加固状态

`fix/controller-hardening-v031` 已实现协议 v2 与 Controller 身份冻结、stale 配置/实现检测、跨协议显式停止、custom config Controller 生命周期、启动锁接管重试、最多 16 个 inflight 的背压、queued 立即取消，以及 data_dir ACL advisory。**这些新增行为在最终 Windows 本地验收完成前只视为“代码已实现、待验收”，不能据此宣称全部运行验证已通过。**

v0.3.1 不会自动停止或自动重启 stale Controller。新 Bridge 发现后台实例仍运行旧配置或旧实现时会 fail-closed，并要求维护者显式停止；未完成任务仍遵循“Controller 重启后标记 interrupted、不自动重做”的既有边界。

### v0.3.2 低上下文返回状态

`perf/context-efficient-status-v032` 收缩 Codex 默认可见的请求、状态与结果热路径：任务仍完整执行并保存证据，普通 status 不重复展开 warning/error 正文和 artifact manifest，`agy_capabilities` 默认只返回 workspace/command 路由字段；`agy_worker/agy_continue` 的公开输入也不再展示当前不可用的 shell/code_write 或无需模型调整的 artifact/summary 字节预算。当前分支的新一轮修补仍需 Windows + 真实 Codex 复验；在验收完成前不能把本节描述为正式已验证能力。

v0.3.2 不改变 Controller protocol v2、六个 MCP 工具、单 Runtime、单执行槽、16 inflight、Runtime 权限执行边界或 request_id 语义。Runtime 仍保存完整 progress/revision；MCP server 在一次 status 总等待预算内合并中间 progress/unchanged revision。公开 `agy_status` 默认等待 50 秒，Codex 可按预计任务耗时自主选择 50～600 秒；MCP 内部仍把该总预算切成最多 25 秒的 Controller long-poll，任务提前进入终态时立即返回，从而减少 Codex tool round-trip。**这里的 25 秒只是服务端内部实现值，不是公开 `wait_ms` 的合法候选。**

本轮针对 v0.3.2 后续问题把默认任务总预算从 300 秒提高到 600 秒，以给真实编译的前置快照、AGY 调度和约 3～5 分钟构建留出余量；上限仍为 1800 秒。公开 `agy_status.wait_ms` 仍严格保持 50000～600000ms，内部短轮询值不再出现在 Codex 的热路径工具说明与 Server instructions 中；如果只是读取当前或 terminal 快照，调用方应同时省略 `after_revision` 和 `wait_ms`。

## 当前可用范围

| 能力 | 本次状态 |
|---|---|
| 编译、测试、日志清洗 | 已启用；命令必须由本地配置登记 |
| 浏览器 | 已启用；独立无头 Edge，支持观察、截图、console/network；交互另需 `browser_interact` |
| 图片 | 已启用；真实 PNG/JPEG 输入，经 MCP 图片内容交给 AGY |
| Android / Logcat | 保留接口设计，未启用；尚未完成设备与包范围验收 |
| 任意 shell、源码写入 | 拒绝；公开 MCP schema 不再暴露这些字段，Runtime 内部仍 fail-closed |

**权限边界的实际强度：当前是 hook + Broker 的工具授权，不是 Windows 安全沙箱。** AGY 和已登记命令使用当前用户身份。项目副本避免常规构建写入原源码，但不是防恶意代码的隔离环境；已有 node_modules 通过 junction 复用，未设置系统只读权限。不要把这个版本用于不可信仓库的任意构建。浏览器 origins 校验覆盖入口 URL，不是重定向、子资源和网络出口防火墙。

AGY 原生写文件、原生命令、其他 MCP 被 hook 拒绝；允许的只有私有 Broker、结束/等待工具及 Broker 的一个本地工具描述文件。实测未授权写文件被阻止。未更改用户 AGY 账号、默认模型或既有浏览器 MCP 配置。

## 启动与接入

安装后由 Codex 按需启动。首个 stdio Bridge 会通过 Windows WMI 在 MCP Job Object 之外隐藏启动 Controller，后续 Codex 对话连接同一个 Controller；不需要常驻窗口、计划任务或 Windows Service。重新加载 MCP 或重启 Codex 后生效。

```powershell
Set-Location 'D:\My\_Elio\agy-worker'
pwsh.exe -NoProfile -File scripts/doctor.ps1
pwsh.exe -NoProfile -File scripts/check.ps1
pwsh.exe -NoProfile -File scripts/register.ps1
```

`register.ps1` 登记 AGY 私有 Broker 及 Codex 的 `agy_worker`，保留其他 MCP，并把 Codex 对该 MCP 的宿主 `tool_timeout_sec` 设为 660 秒，以覆盖合法的最长 600 秒 `agy_status` 等待；660 秒只是宿主调用上限，不会让每次调用固定等待这么久。升级到本轮代码后需重新执行注册入口使该配置生效。Codex 原配置备份在 `work/backups`，这些备份可能包含敏感配置，请勿提交。重新安装使用 `scripts/install.ps1 -Python <Python完整路径>`，依赖锁定在 `requirements.lock` 和 `vendor/browser/package-lock.json`。

同一数据目录仍只允许一个 Runtime，但可以同时存在多个 stdio Bridge。Controller 继续只有 1 个执行槽；v0.3.1 最多接受 16 个排队或运行中的 inflight 任务，第 17 个新的逻辑请求返回 `worker_busy`。同 `request_id`、同 fingerprint 的幂等重试在容量已满时仍返回原 task；queued Future 若尚未开始执行，`agy_cancel` 会直接进入 `cancelled`，无需等待前面的任务释放执行槽。

Bridge 同时首次连接时用启动锁协调。v0.3.1 的 `_ensure()` 会在同一 deadline 内重复尝试取得 launch lock，并在前一个启动者失败后接管；WMI 返回的创建 PID只用于 ownership/诊断，真正 ready 仍以带 Bearer 的 health 为准。

显式停止默认正式配置：

```powershell
pwsh.exe -NoProfile -File scripts/stop.ps1
```

停止指定 Runtime 配置：

```powershell
pwsh.exe -NoProfile -File scripts/stop.ps1 -Config 'D:\path\runtime.toml'
# 或
.venv/Scripts/python.exe -m agy_worker.manage stop --config 'D:\path\runtime.toml'
```

v0.3.1 的显式停止允许管理端读取 legacy v1 state，并用旧实例 state 自己的 `protocol_version` 发起停止；当前 v2 的 `/control/stop` 在 Bearer 鉴权成功后不再要求业务协议一致，但 `/control/call` 仍严格要求当前协议。停止会等待目标实例真正消失；若 state 已被 replacement instance 替换，则停止流程不会继续向新实例发送控制请求。

Controller 连接元数据保存在 `data/controller.json`。v2 state 包含 `protocol_version`、`implementation_version`、`implementation_sha256`、`config_sha256`、`instance_id`、PID、loopback endpoint、随机 token、config_path 和 started_at。endpoint 只接受精确的 `http://127.0.0.1:<port>`；不接受 localhost、0.0.0.0、IPv6、凭据、额外 path、query 或 fragment。state/health/当前磁盘实现身份必须一致才能用于普通业务调用。

Controller token 的保密性仍依赖本机用户和目录 ACL。`doctor` 在 v0.3.1 增加 data_dir ACL advisory：只报告是否成功检查、明显的宽泛读取主体和 token confidentiality 风险；检查失败显示 unknown，不会把未知状态当安全，也不会自动修改 ACL。此诊断不构成 Windows sandbox 或 effective-access 证明。

`start.ps1` 是 stdio Bridge 入口，不是供人输入命令的窗口。

## 公开 MCP 工具与资源

| 工具 | 用途 |
|---|---|
| `agy_capabilities` | 仅在 workspace_id 或 command_id 未知时查询紧凑路由表；完整诊断走只读资源 |
| `agy_worker` | 提交任务，立即返回 task_id、session_id 和状态 |
| `agy_continue` | 同工作区续轮；必须传 session_id、expected_turn 及本轮公开权限 |
| `agy_status` | 无 `after_revision` 时立即读取当前快照；有 revision 时默认最多等待 50 秒，也可由 Codex 选择 50～600 秒总预算；终态提前返回 |
| `agy_cancel` | 取消排队/运行任务，可重复调用 |
| `agy_artifact_read` | 按证据 ID 读取元数据、最多 200 行文本或图片 |

已知 `workspace_id` 和 `command_id` 时直接调用 `agy_worker`，不要仅为定位 AGY/MCP 路由而先执行 `git status`、`git branch`、`git log`、`rg AGY` 或 `agy --help`。映射未知时调用一次 `agy_capabilities`；其默认 structured result 只保留 `schema_version` 和每个 workspace 的 `workspace_id`、`registered_path`、`allowed_commands`，存在额外 Git worktree 时再带 `known_worktrees`。完整 limits、Controller、权限和 workspace/worktree 诊断仍保留在 `agy://capabilities` 与 `agy://workspaces` 冷资源中。

精确请求字段以 `schemas/*.json` 为准。当前公开 `agy_worker/agy_continue` 不包含 `kind=shell`、`permissions.shell`、`code_write/write_paths/write_reason`；这些未开放能力不会再诱导 Codex 申请。公开 `limits` 只允许可选的 `total_timeout_sec`（10～1800 秒，默认 600）。`summary_max_bytes=16384` 与 `artifact_max_bytes=536870912` 仍是 Runtime 内部安全默认值，不由普通 MCP 热路径调整。每轮重新授权，续会话不代表继承额外权限。

### v0.3.2 紧凑 status / result 合同

第一次只知道 `task_id`、还没有可作为变化基线的 revision 时，调用 `agy_status` 可省略 `after_revision`；MCP 会把这次请求转换为内部 `wait_ms=0`，立即取得当前快照。**如果只是读取当前状态或 terminal 快照，应同时省略 `after_revision` 和 `wait_ms`。** 之后 queued/running 状态把上一次看到的 `revision` 作为 `after_revision`。公开 `wait_ms` 省略时总等待预算为 50000ms；Codex 可根据任务预计耗时显式选择 50000～600000ms。这个值是**最多等待预算，不是固定 sleep**：AGY 在窗口内提前进入 terminal 时，本次 MCP 调用立即返回。

Runtime 内部仍可能因为 `captured_bytes/progress` 变化产生多个 revision。MCP server 在同一个公开总等待预算内持续观察并合并这些中间 revision，每次传给 Controller/Runtime 的内部 long-poll 仍不超过 25000ms，server→Controller 的单次 HTTP timeout 仍为 30 秒。**25000ms 只属于 Server→Controller 内部协议，调用 `agy_status` 时不得把它作为公开 `wait_ms` 传入；公开显式值最小仍是 50000ms。** 中间 revision 不会重置公开总等待 deadline；例如 Codex 选择 120 秒，不会因为每个 progress revision 再获得新的 120 秒。

如果等待窗口结束时仍没有新的可交付观察点且任务非终态，可返回最小无变化 envelope：

```json
{
  "task_id": "task-...",
  "status": "running",
  "revision": 5,
  "unchanged": true
}
```

`unchanged=true` 只表示这个观察窗口里没有新的状态 revision。**它不表示 AGY、Gradle 或其他操作卡死，也不会触发自动取消。** 若一次调用仍返回非终态，调用方应直接继续 `agy_status`；不需要在两次 status 之间生成“我再等一轮”等面向用户的等待说明。除非用户明确取消或既有总超时到达，否则仍等待实际进程终态。

终态 status 默认只返回决策摘要，包括 `summary`、真实 operation 退出码、错误/警告计数、termination reason、源码是否变化以及可追溯的 evidence/result artifact ID；不再默认展开 `errors[]`、`warnings[]` 和整份 `artifacts[]` metadata。需要细节时按需读取：

- `diagnostics_artifact_id`（通常为 `errors`）：结构化错误/警告正文；
- `operation.evidence.artifact_id`（通常为 `operation-log`）：带上下文的脱敏操作日志；
- `result_artifact_id`（通常为 `result`）：完整任务 result 证据。

普通 JSON MCP 工具以 `structuredContent` 为 canonical machine result；`TextContent` 只提供不超过 256 UTF-8 bytes 的人类短摘要，不再把同一完整 JSON 复制第二遍。`agy_artifact_read` 是显式高信息量冷路径：文本/metadata 只发送一份实际 payload，图片仍走 ImageContent。为降低上下文消耗，读取日志时优先指定必要的 `start_line` / `line_count`，不要无条件拉取整份证据。

v0.3.2 的公开字节门槛是：unchanged status ≤256B、changed nonterminal ≤512B、build/test terminal ≤1536B、其他 terminal ≤2048B、热路径 TextContent ≤256B。完整本地 evidence 不受这些热路径上限删除，仍由 artifact 机制保留。

### request_id 合同

`request_id` 用于整个 `data_dir` 历史范围内的幂等键。新逻辑请求推荐生成：

```text
req-<uuid4hex>
```

例如 `req-7d3f1b3c0b1e4f91a8c7e2d4f6a9b123`。每个新的逻辑请求、每个新的续轮都使用新的 ID；**只有同一个逻辑请求的 transport/reconnect 重试才复用原 request_id**。同 ID 同内容返回已有 task，同 ID 不同内容返回 `idempotency_conflict`。MCP 瘦请求在进入 Runtime 前会补齐固定内部安全默认值，因此正常省略隐藏字段不会改变内部 fingerprint。历史 ID 不因任务终态或 Controller 重启而自动释放，本次不修改 SQLite schema。

`workspace_id` 是 `agy_capabilities` 返回的登记别名，不是文件路径。对于任何已登记 Git 仓库，可通过额外的 `workspace_path` 指向该仓库由 Git 正式登记的主工作树或分离 worktree。Runtime 会校验 worktree 根目录、Git common-dir 和 `git worktree list`；其他仓库、普通目录、仓库子目录及不存在路径都会拒绝。续会话绑定首次使用的实际路径，不能中途换 worktree。

普通 MCP 一般完全省略 `limits`；只有任务确实需要超过默认 600 秒时才设置 `total_timeout_sec`。完整内部限制和默认值可通过冷资源 `agy://capabilities` 查看，但 `summary_max_bytes`、`artifact_max_bytes` 不再是普通 MCP 的可调输入。Codex MCP 注册的外层 `tool_timeout_sec` 为 660 秒，用于覆盖 `agy_status` 最长 600 秒公开等待预算；Controller status 单次 HTTP timeout 仍为 30 秒，内部单段 long-poll 仍最多 25 秒。若 Controller status 首次因 `controller_unavailable` 重连，既有 client 重连逻辑仍会把重试 `wait_ms` 置 0，避免重复消耗长等待预算。

编译真实项目示例：

```json
{
  "request_id": "req-9a4c2e71f0b84d5c8f3a6b1e7d2c4f90",
  "workspace_id": "life_archive",
  "workspace_path": "D:\\My_Elio\\life-archive-performance-verification",
  "kind": "build",
  "objective": "执行 Android 资源导出，只报告是否成功、错误原文和定位，不分析原因、不修改源码。",
  "permissions": {"build": true, "log": true},
  "inputs": {"command_id": "life_android_resource"},
  "limits": {"total_timeout_sec": 1200}
}
```

独立验收方式（仅在 Codex 未占用 Runtime 时）：

```powershell
.venv/Scripts/python.exe scripts/run-task.py examples/life-archive-build.json --output work/local-result.json
```

显式 `--config <runtime.toml>` 时，`run-task.py` 会在进入 stdio Bridge 前建立 ownership-aware Controller client：若这次 invocation 自己启动了 custom Controller，默认在 `finally` 中只停止同一个 `instance_id`；预先存在的 Controller 不会被它清理。需要保留本次新启动的 custom Controller 时可加 `--keep-controller`。未传 `--config` 时正式 Controller 继续常驻。

示例文件里的 request_id 只是静态示意；重复运行同一示例会按幂等合同返回原任务。需要新一轮真实执行时请生成新的 `req-<uuid4hex>`，不要通过修改内容复用旧 ID。可直接向 Codex 说：“用 agy_worker 编译 life_archive，只采集报错，不修改代码。”

浏览器示例：

```json
{
  "request_id": "req-4be2a06d98f24c62a1d7e53f0b8c9a11", "workspace_id": "demo", "kind": "browser",
  "objective": "打开指定网页，读取标题与正文并保存截图，返回观察结果与证据引用。",
  "permissions": {"browser": true, "origins": ["https://example.com"]},
  "inputs": {"url": "https://example.com"}
}
```

图片示例：`kind=vision`，`permissions.vision=true`，`inputs.files=["colors.png"]`，workspace_id 为 demo。日志任务对应 `kind=log`、`permissions.log=true` 和单个已登记工作区内的文件。

## 维护者辅助清洗流程

Codex 可以把依赖源码、长日志或大段终端输出作为只读文本任务交给 AGY 清洗，Codex 仍是实施主体。此流程要求目标只写“提取事实、定位和证据行号”，不让 AGY 判断架构、分析本项目根因或修改文件。AGY 的摘要必须由 Codex 回看原始证据后再用于改代码。

**“维护者辅助清洗流程”是维护者的调用约定，不是 Runtime-enforced `analysis_level` 模式。** 当前公开 MCP schema 没有 `analysis_level=extract_only` 等字段；真正由 Runtime 强制执行的仍是任务 kind、permissions、已登记 command、hook + 私有 Broker、路径/容量/超时等边界。不能把提示词里的“只提取”描述成系统安全控制。

需要检查尚未登记的依赖目录时，维护者可创建独立 Runtime 配置和数据目录，再用 `scripts/run-task.py --config <配置>` 运行；这不会扩大正式 Controller 的工作区。2026-09-09 已用此方式读取 MCP SDK 的 stdio 终止代码，AGY 只返回 Windows Job Object、两秒退出宽限和后代进程清理的行号证据，`source_changed=false`。

## 真实项目绑定

源项目是 **`D:\My_Elio\life-archive-app`**，与 Worker 的 `D:\My\_Elio` 路径不同。该项目为 HBuilderX / uni-app，不使用 Gradle。

Runtime 复制 Git 跟踪文件、未忽略的未跟踪文件，以及已初始化子模块中的同类文件，包含当前未提交内容。不会复制 .git、既有构建产物、AGY hooks 等。复制到 `data/sessions/<session_id>` 后再构建；续轮重新同步输入。未初始化子模块不自动联网拉取。

已登记命令：

- `life_android_resource`：将本轮副本导入现有 HBuilderX，调用项目已有 Android 导出脚本，校验本轮新生成的资源 manifest，最后关闭副本项目。
- `life_markdown_check`：运行项目既有 Markdown 检查。
- `life_node_tests`：运行项目 Node 测试。

**Android 资源导出不等于 APK 打包、安装或真机测试。** 不触发云打包。HBuilderX 某些业务失败返回 0，因此包装器同时检查错误文字和新产物，避免假成功。原项目脚本未被修改。

## 结果和证据

任务目录 `data/tasks/<task_id>` 保存 request.json、permissions.json、audit.ndjson、result.json、manifest.json、raw 日志、脱敏日志与截图。manifest 带 SHA-256、大小、类型和敏感标记。v0.3.2 的普通公开 status 使用独立紧凑预算，完整 result 和更多证据按 ID 读取；原始敏感日志只能本机查看，不通过普通 artifact 文本读取接口返回。

编译摘要区分 AGY 执行状态与实际命令退出码。错误列表保留原文、可提取的文件/行列、Gradle task（如存在）及日志行引用；编译器未提供行列时返回 null，不编造。stdout 和 stderr 原始文件分开保存，合并日志是 stdout 后接 stderr，不能据此推断跨流时间顺序。

默认不自动删除日志和会话副本，避免丢失证据。当前没有自动留存清理任务；本机磁盘需要自行管理，建议确认任务结束、导出证据后定期清理。取消通过 Windows Job Objects 终止本轮创建的进程树；既有共享 HBuilderX 可能继续已经提交的导出，不强杀用户 GUI。Controller 重启将未完成任务标为 interrupted，不自动重做外部操作；历史 task、session 与 artifact 仍可查询。Controller 日志位于 `data/logs/controller.log`。

## 目录

```text
config/runtime.toml       本机能力、工作区、固定命令
src/agy_worker/           stdio Bridge、Controller、Runtime、Broker、hook、执行与证据模块
scripts/                 安装、检查、注册、运行和 HBuilderX 适配器
schemas/                 六个公开工具的 JSON Schema
examples/                样例请求和最小验证项目
tests/                   权限、状态、路径、进程树和快照回归测试
vendor/browser/          锁定的浏览器 MCP 依赖
docs/                    实施设计与验收记录
data/                    会话副本、SQLite 状态和任务证据（不提交 Git）
work/                    诊断脚本、配置备份和验收中间结果（不提交 Git）
```

## 后续阶段

1. 已完成任务控制、AGY direct CLI、日志/构建端到端；系统隔离验收仍未完成。
2. 已完成浏览器观察/截图端到端；进一步验收交互、网络范围及敏感字段处理。
3. Android：按设备序列号和包名授权，先验收观察/Logcat，再启用点击、滑动与输入。
4. 已完成真实图片读取；扩展多图证据对比及精度验证。
5. 增强 Windows 账户/沙箱、工具链与网络隔离、审计留存。通过源码只读隔离验收后，才能设计有明确路径和理由的 code_write 授权。独立 Git worktree 可用于后续有意修改源码的任务，不能把 worktree 当作系统安全边界。

卸载连接使用 `scripts/uninstall.ps1`；默认保留所有代码和证据，不递归删除用户文件。