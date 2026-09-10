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
validated executable head: b00a5a8853336c345fc186bb9049c44931f19149
phase: final_acceptance_passed_ready_for_draft_pr
production code changed: yes
user approval to start production implementation: approved_2026-09-09
final Windows acceptance: PASS
full repository check: 77 passed, 0 failed, 0 skipped, 0 warnings
remote spec/code-quality review: no open Critical/Important
open PR: pending Draft creation
merge authorized: false
```

用户已确认 SPEC / PLAN 并授权在独立分支连续开发。第一次 Final Acceptance 暴露 signal thread、stop/state race、Windows venv WMI ownership、shared pending 测试稳定性和 trailing whitespace 等问题；这些 finding 经 `receiving-code-review` 技术复核后完成 remediation。

第二次完整 Windows Final Acceptance 在精确代码/测试 HEAD `b00a5a8853336c345fc186bb9049c44931f19149` 上执行并返回 PASS：`scripts/check.ps1` exit 0、77/77 pytest，通过真实 WMI ownership、fresh 双 Bridge lifecycle、custom-config no-leak / pre-existing preservation / `--keep-controller`、ACL advisory 和两个 `git diff --check`。

后续 `TASKS.md` / `docs/部署验收.md` 等提交只记录验收状态，不修改生产代码、测试、脚本或依赖。执行证据仍明确绑定 `b00a5a8...`，不能说文档记录提交之后又重新执行过 Windows 测试。

## 最终审查结论

规划阶段按 Superpowers `writing-plans` / plan reviewer 的 Completeness、Spec Alignment、Task Decomposition、Buildability 做过自审。开发完成后又按 Web Adapter 分成独立的规格复核与代码质量复核，最终覆盖：

- stale config / stale implementation；
- protocol v2 与旧 Controller 显式 stop；
- stop 等待 state 真正消失与 replacement 防误停；
- custom `run-task --config` Controller ownership / cleanup；
- launch lock takeover、retry cooldown、shared pending PID；
- Windows venv launcher PID 与 Controller 后代 ownership；
- state endpoint fail-closed 与 authenticated health object validation；
- `controller_data_acl` advisory；
- status reconnect timeout budget；
- 单执行槽 + 16 inflight backpressure；
- queued task immediate cancel；
- request_id 全 data_dir 历史唯一语义；
- `jsonschema==4.26.0` 正式依赖和 package/server `0.3.1` 单一版本来源；
- “维护者辅助清洗流程”不是 Runtime analysis mode；
- fresh 双 Bridge lifecycle 与 same-instance stop；
- 完成前 full check / diff-check / local acceptance / 最终远端复核。

远端最终审查没有开放的 Critical / Important finding。

## 最终 Windows 证据摘要

```text
OS: Windows 10 Pro 19045 x64
PowerShell: 7.6.5
Python: 3.13.9
Package metadata: 0.3.1

scripts/check.ps1:
  exit 0
  compileall successful
  77 passed in 37.92s
  failed=0
  skipped=0
  warnings=0

verify-controller.py --fresh --stop-after:
  exit 0
  two Bridges: 6 tools each
  protocol=2
  controller remains alive after Bridges
  max_concurrent_tasks=1
  max_inflight_tasks=16
  same-instance stop=true
  verification_passed=true
  final state absent

Windows venv ownership:
  launcher PID != Controller PID accepted
  started_controller=true
  started_instance_id == state.instance_id
  no residual state/process

Git integrity:
  fixed-base diff-check exit 0
  origin/main...HEAD diff-check exit 0
  tracked status clean
```

## ACL advisory

最终 doctor：`controller_data_acl.checked=true`，检测到 `NT AUTHORITY\Authenticated Users` 与 `BUILTIN\Users` broad read，`token_confidentiality_advisory=true`，同时 `os_isolation=false`。

这仍然只是设计允许的 advisory：不自动写 ACL，不把当前系统描述成 Windows sandbox 或完整 effective-access 隔离。

## 当前门禁

```text
第二次完整 Final Acceptance PASS
→ ChatGPT receiving-code-review 技术复核 PASS 证据
→ TASKS.md / docs/部署验收.md 回填真实结果
→ verification-before-completion 核对证据边界
→ 创建 Draft PR
→ 保留 feature branch
→ 不 merge；最终 merge 由用户决定
```

## 未验证 / 不在本次范围

本轮 Controller hardening 最终验收没有重新执行真实 AGY 业务任务、HBuilderX、Android/ADB/真机或真实 browser 业务流。这些不属于本次必要通过条件，不能写成此次已验证。

未经用户明确授权，不合并 `main`、不删除分支、不启用自动合并、不强制推送。