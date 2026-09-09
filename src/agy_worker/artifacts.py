"""默认只回传有界脱敏片段，原始字节留在任务目录。"""
import json
import mimetypes
from pathlib import Path
from .common import WorkerError, atomic_json, digest, now, redact


class Artifacts:
    def __init__(self, root: Path):
        self.root = root
        self.manifest = root / "manifest.json"
        self.items = json.loads(self.manifest.read_text("utf-8")) if self.manifest.exists() else {}

    def add(self, key, path: Path, *, sensitive=False):
        path = path.resolve()
        if not path.is_relative_to(self.root.resolve()) or path.is_symlink():
            raise WorkerError("permission_denied", "证据不在当前任务目录")
        entry = {"artifact_id": key, "path": path.relative_to(self.root.resolve()).as_posix(),
                 "size_bytes": path.stat().st_size, "sha256": digest(path),
                 "media_type": ("text/plain" if path.suffix in (".log",".ndjson") else mimetypes.guess_type(path.name)[0]) or "application/octet-stream",
                 "created_at": now(), "sensitive": sensitive}
        self.items[key] = entry
        atomic_json(self.manifest, self.items)
        return {k: v for k, v in entry.items() if k != "path"}

    def read(self, key, view="text", start_line=1, line_count=100):
        from .common import safe_path
        item = self.items.get(key)
        if not item:
            raise WorkerError("artifact_not_found", "当前任务没有这个证据")
        metadata = {k: v for k, v in item.items() if k != "path"}
        if view == "metadata":
            return metadata
        if item["sensitive"]:
            raise WorkerError("permission_denied", "原始敏感证据只在本机保留，请读取脱敏派生证据")
        path = safe_path(self.root, item["path"])
        if digest(path) != item["sha256"]:
            raise WorkerError("artifact_integrity_error", "证据哈希已改变")
        if view == "image":
            if item["media_type"] not in ("image/png", "image/jpeg") or item["size_bytes"] > 5*1024*1024:
                raise WorkerError("invalid_request", "仅支持不超过 5 MiB 的 PNG/JPEG")
            return metadata, path.read_bytes()
        kept, size, more = [], 0, False
        with path.open(encoding="utf-8", errors="replace") as stream:
            for n, line in enumerate(stream, 1):
                if n < start_line:
                    continue
                line = redact(line.rstrip("\r\n"))
                if not kept and len(line.encode("utf-8")) > 65536:
                    raise WorkerError("line_too_large", "单行超过 64 KiB，请在本机读取此证据或先生成分行派生日志")
                if len(kept) >= line_count or size + len(line.encode("utf-8")) > 65536:
                    more = True
                    break
                kept.append(line)
                size += len(line.encode("utf-8"))
        return {**metadata, "start_line": start_line, "end_line": start_line+len(kept)-1,
                "text": "\n".join(kept), "truncated": more,
                "next_start_line": start_line+len(kept) if more else None}
