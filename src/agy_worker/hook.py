"""AGY PreToolUse 入口；任何异常都输出明确 deny。"""
import json
import os
import sys
import urllib.request


def main():
    decision = {"decision": "deny", "reason": "Worker 权限检查不可用"}
    try:
        raw = sys.stdin.buffer.read(1024*1024+1)
        if len(raw) > 1024*1024:
            raise ValueError("hook 输入过大")
        address = os.environ["AGY_WORKER_ENDPOINT"]
        token = os.environ["AGY_WORKER_TOKEN"]
        if not address.startswith("http://127.0.0.1:"):
            raise ValueError("非本机控制端")
        request = urllib.request.Request(address+"/hook", data=raw,
                 headers={"Authorization": "Bearer "+token, "Content-Type": "application/json"})
        # 私有令牌不得经过用户配置的 HTTP 代理。
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=3) as response:
            decision = json.load(response)
        if decision.get("decision") not in ("allow", "deny"):
            raise ValueError("未知权限决定")
    except Exception:
        decision = {"decision": "deny", "reason": "Worker 权限检查失败，拒绝执行"}
    sys.stdout.buffer.write(json.dumps(decision, ensure_ascii=False).encode("utf-8"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
