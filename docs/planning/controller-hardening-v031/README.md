# Controller v0.3.1 Planning Hub

本目录是 `fix/controller-hardening-v031` 的跨对话持久上下文。后续 ChatGPT、本地 AI 或新的开发对话应先读这里，不要只依赖聊天记录。

## 阅读顺序

1. `SPEC.md` — 已批准的目标、架构决定、安全边界和验收标准；冲突时它高于施工计划。
2. `PLAN.md` — T1～T9 的逐任务 TDD 实施步骤、文件、接口、提交和审查 gate；其中未勾选步骤是原始施工清单，不等于当前执行状态。
3. `TASKS.md` — **唯一当前进度追踪表**；当前 HEAD、远端实现状态、审查发现和真实验证证据以这里为准。
4. `LOCAL-ACCEPTANCE.md` — 最终一次性 Windows 本地验收协议和报告格式。

## 当前状态

```text
base: 904b75a6e7b9d0b75c0ae8f63924c3ed0acf5066
branch: fix/controller-hardening-v031
phase: final_remote_review_complete_waiting_local_acceptance
production code changed: yes
user approval to start production implementation: approved_2026-09-09
final Windows acceptance for current HEAD: pending
open PR: none
merge authorized: false
```

用户已确认 SPEC / PLAN 并授权在独立分支连续开发。T1～T9 的计划范围已经写入远端分支，随后又执行了独立规格复核和代码质量复核；审查中发现的 ACL 字段漂移、`--fresh` 对不可达旧 state 的误判，以及 WMI 重试共用环境文件的竞态，均已在分支上追加回归测试和修正。

**这不等于最终运行验证已通过。** 当前 ChatGPT Web 没有本地 Windows test runner，仓库也没有可替代本地验收的 GitHub Actions。最终树必须由本地 AI 按 `LOCAL-ACCEPTANCE.md` 一次性执行定向 pytest、`scripts/check.ps1`、fresh 双 Bridge/WMI 生命周期、custom-config ownership、ACL doctor 和 `git diff --check`。只有拿到这些新鲜证据后，才能进入最终验收记录和 Draft PR 阶段。

## 计划自审结论

规划阶段按 Superpowers `writing-plans` / plan reviewer 的 Completeness、Spec Alignment、Task Decomposition、Buildability 做过自审。远端最终审查再次逐项覆盖：

- stale config / stale implementation；
- protocol v2 与旧 Controller 显式 stop；
- custom `run-task --config` Controller ownership / cleanup；
- launch lock takeover、retry cooldown、WMI PID ownership；
- state endpoint fail-closed；
- `controller_data_acl` advisory；
- status reconnect timeout budget；
- 单执行槽 + 16 inflight backpressure；
- queued task immediate cancel；
- request_id 全 data_dir 历史唯一语义；
- `jsonschema==4.26.0` 正式依赖和 package/server `0.3.1` 单一版本来源；
- “维护者辅助清洗流程”不是 Runtime analysis mode；
- fresh 双 Bridge 生命周期与 same-instance stop；
- 完成前 spec review / code-quality review / local acceptance / Git diff review。

## 已保留的两项验收修正

### R1 — editable metadata 必须刷新

最终验收先执行：

```powershell
& ./.venv/Scripts/python.exe -m pip install --no-deps --no-build-isolation -e .
& ./.venv/Scripts/python.exe -c "import importlib.metadata as m; print(m.version('elio-agy-worker'))"
```

期望 metadata 为 `0.3.1`，避免旧 editable `.dist-info` 让 server version 测试产生假结论。

### R2 — custom run-task no-leak 不依赖 AGY 登录

`LOCAL-ACCEPTANCE.md` 使用不存在的 `workspace_id` 让请求在 Runtime 前置校验阶段稳定拒绝。这样可以真实启动/复用 Controller 并验证 cleanup，却不会调用 AGY；业务请求非零退出是该探针的预期，lifecycle 结论只看 state/instance ownership。

## 当前门禁

```text
远端最终 HEAD 锁定
→ 本地 AI 按 LOCAL-ACCEPTANCE.md 一次性执行最终 Windows 验收
→ ChatGPT 按 receiving-code-review 技术复核每条证据/失败
→ 若存在缺陷：新增回归测试并修复，再重新验收最终树
→ 若全部必要证据通过：更新 TASKS.md / docs/部署验收.md
→ 再进入 finishing-a-development-branch 的 PR/集成决策
```

未经用户明确授权，不合并 `main`、不删除分支、不启用自动合并、不强制推送。