"""只提取错误原文和定位，不判断原因或生成修复建议。"""
import re
from .common import redact

LOCATION = re.compile(r"(?P<file>(?:[A-Za-z]:)?[^\r\n]*?\.(?:kt|java|py|c|cpp|h|cs|ts|tsx|js))[:(](?P<line>\d+)(?:[:,](?P<column>\d+))?\)?[: ]*(?P<message>.*)")
SEVERITY = re.compile(r"(?i)\b(error|warning|fatal|failed|exception)\b|\(!\)|Could not resolve|\b\w+(?:Error|Exception):|^[ew]:|编译失败|导出失败|不存在，请先导入|错误|警告")


def extract(path, destination, artifact_id="operation-log"):
    errors, warnings, index, task, total_lines = [], [], {}, None, 0
    python_location = None
    with path.open(encoding="utf-8", errors="replace") as stream, destination.open("w", encoding="utf-8") as clean:
        for n, raw in enumerate(stream, 1):
            total_lines = n
            raw = redact(raw.rstrip("\r\n"))
            clean.write(raw + "\n")
            if raw.startswith("> Task "):
                task = raw[7:].split()[0]
            traceback = re.search(r'File "([^"]+)", line (\d+)', raw)
            if traceback:
                python_location = {"file": traceback[1], "line": traceback[2]}
            if not SEVERITY.search(raw):
                continue
            location = LOCATION.search(raw)
            fields = location.groupdict() if location else (python_location or {})
            item = {"file": fields.get("file", "").removeprefix("e: ").strip() or None,
                    "line": int(fields["line"]) if fields.get("line") else None,
                    "column": int(fields["column"]) if fields.get("column") else None,
                    "message": fields.get("message") or raw, "raw": raw,
                    "task": task, "count": 1,
                    "evidence": {"artifact_id": artifact_id, "start_line": n, "end_line": n}}
            key = (item["file"], item["line"], item["column"], raw, task)
            if key in index:
                index[key]["count"] += 1
                index[key]["last_line"] = n
            else:
                index[key] = item
                (warnings if re.search(r"(?i)warning|\(!\)|^w:|警告", raw) else errors).append(item)
    return {"errors": errors, "warnings": warnings, "total_lines": total_lines}
