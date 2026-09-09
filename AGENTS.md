# 项目工作要求

这是 Windows 10 x64 的本地 AGY Worker，Python 3.13、官方 MCP Python SDK，对外提供能力发现、五个任务级 MCP 工具及两个只读资源。

- 报告和有意义的代码注释使用中文，PowerShell 使用 pwsh.exe。
- Codex 负责判断、源码分析和修复；AGY 编译任务只能执行与采集错误。
- 不开放任意 shell，不修改用户原项目，只在 data/sessions 的快照中执行。
- 权限在 hook 与私有 Broker 双重校验；当前没有通过系统级隔离验收，不能把它描述为安全沙箱。
- config/runtime.toml 是登记工作区与命令的唯一入口。AGY 不得修改这个文件。
- scripts/check.ps1 为权威检查入口。真实 AGY 验收会使用当前登录账号。
- data/、work/、.venv/ 和 vendor/browser/node_modules/ 不提交。
- 不删除或覆盖 C:/Users/70455/.gemini 下用户既有配置；仅管理 agy-worker-broker 条目。
- 源码写入与 shell 类型当前显式拒绝，不能通过添加兼容分支或移除检查来打开。
