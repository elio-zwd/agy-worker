"""接口默认拒绝未知字段，权限不能靠自然语言隐式开启。"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Permissions(Strict):
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
    shell: bool = False
    code_write: bool = False
    write_paths: list[str] = Field(default_factory=list, max_length=30)
    write_reason: str | None = None

    @model_validator(mode="after")
    def scope(self):
        if self.code_write and (not self.write_paths or not self.write_reason):
            raise ValueError("源码修改必须给出 write_paths 和 write_reason")
        if not self.code_write and self.write_paths:
            raise ValueError("code_write=false 时不接受写入路径")
        if self.browser and not self.origins:
            raise ValueError("浏览器任务必须指定 origins")
        if self.browser_interact and not self.browser:
            raise ValueError("browser_interact 需要 browser=true")
        if self.android_ui and not (self.device_serial and self.package):
            raise ValueError("Android 任务必须指定设备序列号和包名")
        return self


class Inputs(Strict):
    command_id: str | None = None
    files: list[str] = Field(default_factory=list, max_length=20)
    url: str | None = None


class Limits(Strict):
    total_timeout_sec: int = Field(300, ge=10, le=1800)
    summary_max_bytes: int = Field(16384, ge=2048, le=16384)
    artifact_max_bytes: int = Field(536870912, ge=1048576, le=536870912)


class CapabilitiesRequest(Strict):
    pass


class WorkerRequest(Strict):
    request_id: str = Field(min_length=1, max_length=100, pattern=r"^[\w.-]+$")
    workspace_id: str = Field(min_length=1, max_length=80)
    workspace_path: str | None = Field(default=None, min_length=1, max_length=1024)
    kind: Literal["build", "test", "log", "browser", "android-ui", "vision", "shell"]
    objective: str = Field(min_length=1, max_length=12000)
    permissions: Permissions = Field(default_factory=Permissions)
    inputs: Inputs = Field(default_factory=Inputs)
    limits: Limits = Field(default_factory=Limits)


class ContinueRequest(WorkerRequest):
    session_id: str
    expected_turn: int = Field(ge=1)


class StatusRequest(Strict):
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
