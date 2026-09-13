# v0.4.0 整合基线说明

## 当前事实

最终整合分支为：

```text
feat/leader-member-questions-v2
```

它以已完成但尚未合并到 `main` 的 PR #4 分支 `fix/v033-timeout-status-guidance` 为前置基线。PR #4 HEAD：

```text
cf089281165fc07243afe609eeaa1076b3993c76
```

v2 的整合 merge commit 为：

```text
dd923eab442a83ea8fdc222de5ef96a052214778
```

该 merge commit 的两个父提交分别为 PR #4 HEAD 与旧 `feat/leader-member-questions` HEAD，因此保留两边开发历史；冲突解析以 v0.3.3 已完成行为为底，再叠加 v0.4.0 协作功能。

## 必须保留的 v0.3.3 行为

- 默认 `total_timeout_sec = 600`；
- 公开 `agy_status.wait_ms` 仍只接受 50000～600000ms；
- 25000ms 只属于内部 Controller long-poll，不进入模型可见调用建议；
- 当前/terminal 快照应省略 `after_revision` 和 `wait_ms`；
- PR #4 的 `runtime.py`、worker/continue schema、`tests/test_v033_followups.py` 与 `tests/test_manage.py` 回归继续保留。

## v0.4.0 叠加能力

- 私有 `worker_action.ask_leader`；
- 公开 `agy_answer`；
- `agy_status` 对 `leader_question` 立即返回，不把它当普通 progress 合并；
- `CollaborativeRuntime` 负责问题等待、回答、幂等、取消/超时/重启 fail-closed；
- `collaboration.py` 纳入 Controller implementation hash。

## 历史文档说明

`docs/superpowers/` 下的设计/计划，以及 `docs/实施设计.md` 中出现的旧分支名 `feat/leader-member-questions`，记录的是第一轮实现时的历史上下文。**当前验收、后续修复和 PR 均以 `feat/leader-member-questions-v2` 为准。**

本地验收以同目录的 `LOCAL-ACCEPTANCE.md` 为当前执行清单。
