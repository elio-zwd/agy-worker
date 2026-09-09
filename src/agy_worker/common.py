"""路径、持久化和错误在控制侧统一处理。"""
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path


class WorkerError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def digest(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_path(root: Path, relative: str, *, exists=True):
    # 拒绝 Windows 的备用数据流、设备路径与重解析点，不能只做字符串前缀比较。
    normalized = relative.replace("\\", "/")
    if not normalized or ":" in normalized or normalized.startswith("/"):
        raise WorkerError("permission_denied", "只接受工作区内的相对路径")
    parts = normalized.split("/")
    if any(p in ("", ".", "..") or p.endswith((" ", ".")) for p in parts):
        raise WorkerError("permission_denied", "路径包含不允许的片段")
    root = root.resolve(strict=True)
    path = root
    for part in parts:
        path = path / part
        if path.exists() and path.lstat().st_file_attributes & 0x400:
            raise WorkerError("permission_denied", "不允许重解析点")
    if not path.resolve().is_relative_to(root):
        raise WorkerError("permission_denied", "路径越界")
    if exists and not path.exists():
        raise WorkerError("artifact_not_found", "指定文件不存在")
    return path


def redact(value: str):
    value = re.sub(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s\"']+", r"\1[REDACTED]", value)
    return re.sub(r"(?i)((?:api[_-]?key|access[_-]?token|password|cookie)\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]", value)


def redact_value(value):
    if isinstance(value,dict):
        return {key:('[REDACTED]' if re.search(r'(?i)authorization|cookie|password|token|api.?key',key) else redact_value(item)) for key,item in value.items()}
    if isinstance(value,list):
        return [redact_value(item) for item in value]
    return redact(value) if isinstance(value,str) else value
