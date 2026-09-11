"""MCP 热路径只暴露当前可用字段；Runtime 内部模型保留完整安全默认值。"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_TOTAL_TIMEOUT_SEC = 600


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class McpPermissions(Strict):
    """Codex 可直接申请的当前公开权限；未开放能力不进入 MCP schema。"""
    build: bool = False
    test: bool = False
    log: bool = False
    browser: bool = False
    browser_interact: bool = False
    origins: list[str] = Field(default_factory=list, max_length=16)
    android_ui: bool = Field(False, alias="android-ui")
    device_serial: str | None = None
    package: str | None = None
    vision: bool = False

    @model_validator(mode="after")
    def scope(self):
        if self.browser and not self.origins:
            raise ValueError("浏览器任务必须指定 origins")
        if self.browser_interact and not self.browser:
            raise ValueError("browser_interact 需要 browser=true")
        if self.android_ui and not (self.device_serial and self.package):
            raise ValueError("Android 任务必须指定设备序列号和包名")
        return self


class Permissions(McpPermissions):
    """Runtime 内部权限模型；禁用字段保留用于 fail-closed 兼容与审计。"""
    shell: bool = False
    code_write: bool = False
    write_paths: list[str] = Field(default_factory=list, max_length=30)
    write_reason: str | None = None

    @model_validator(mode="after")
    def write_scope(self):
        if self.code_write and (not self.write_paths or not self.write_reason):
            raise ValueError("源码修改必须给出 write_paths 和 write_reason")
        if not self.code_write and self.write_paths:
            raise ValueError("code_write=false 时不接受写入路径")
        return self


class Inputs(Strict):
    command_id: str | None = None
    files: list[str] = Field(default_factory=list, max_length=20)
    url: str | None = None


class McpLimits(Strict):
    """正常 MCP 调用只允许调整任务总时长；上下文/证据预算使用服务端安全默认值。"""
    total_timeout_sec: int = Field(DEFAULT_TOTAL_TIMEOUT_SEC, ge=10, le=1800)


class Limits(McpLimits):
    summary_max_bytes: int = Field(16384, ge=2048, le=16384)
    artifact_max_bytes: int = Field(536870912, ge=1048576, le=536870912)


class CapabilitiesRequest(Strict):
    pass


class McpWorkerRequest(Strict):
    """Codex 看到的 agy_worker 请求模型。"""
    request_id: str = Field(min_length=1, max_length=100, pattern=r"^[\w.-]+$")
    workspace_id: str = Field(min_length=1, max_length=80)
    workspace_path: str | None = Field(default=None, min_length=1, max_length=1024)
    kind: Literal["build", "test", "log", "browser", "android-ui", "vision"]
    objective: str = Field(min_length=1, max_length=12000)
    permissions: McpPermissions = Field(default_factory=McpPermissions)
    inputs: Inputs = Field(default_factory=Inputs)
    limits: McpLimits = Field(default_factory=McpLimits)


class WorkerRequest(McpWorkerRequest):
    """Controller/Runtime 内部完整请求；禁用 shell 仍由 Runtime 明确拒绝。"""
    kind: Literal["build", "test", "log", "browser", "android-ui", "vision", "shell"]
    permissions: Permissions = Field(default_factory=Permissions)
    limits: Limits = Field(default_factory=Limits)


class McpContinueRequest(McpWorkerRequest):
    session_id: str
    expected_turn: int = Field(ge=1)


class ContinueRequest(WorkerRequest):
    session_id: str
    expected_turn: int = Field(ge=1)


class McpStatusRequest(Strict):
    """Codex 可选择的单次 MCP 总等待预算；省略时默认 50 秒。"""
    task_id: str
    after_revision: int | None = None
    wait_ms: int = Field(50000, ge=50000, le=600000)


class StatusRequest(Strict):
    """Controller/Runtime 内部单段等待；MCP 会把较长总预算切成最多 25 秒的分片。"""
    task_id: str
    after_revision: int | None = None
    wait_ms: int = Field(0, ge=0, le=25000)


class CancelRequest(Strict):
    task_id: str
    reason: str = Field("Codex 请求取消", max_length=500)


class ArtifactRequest(Strict):
    task_id: str
    artifact_id: str
    view: Literal["metadata", "text", "image"] = "text"
    start_line: int = Field(1, ge=1)
    line_count: int = Field(100, ge=1, le=200)
