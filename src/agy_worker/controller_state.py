"""Controller 冻结身份、连接元数据与摘要的单一来源。"""
import hashlib
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field


PACKAGE_NAME = "elio-agy-worker"
CONTROLLER_IMPLEMENTATION_FILES = (
    "artifacts.py",
    "browser.py",
    "common.py",
    "controller.py",
    "controller_protocol.py",
    "controller_state.py",
    "logs.py",
    "models.py",
    "processes.py",
    "runtime.py",
)


class LegacyControllerState(BaseModel):
    """只用于识别旧 Controller 的最小连接信息；管理停止在 T2 使用。"""

    model_config = ConfigDict(extra="allow")

    protocol_version: int = Field(ge=1)
    pid: int = Field(gt=0)
    endpoint: str
    token: str = Field(min_length=32)
    config_path: str
    started_at: str


class ControllerState(LegacyControllerState):
    """当前协议的严格 state；普通 Bridge 只接受这个结构。"""

    model_config = ConfigDict(extra="forbid")

    implementation_version: str = Field(min_length=1)
    implementation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    instance_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class ControllerHealth(BaseModel):
    """鉴权 health 返回的冻结身份；必须和 state 指向同一个实例。"""

    model_config = ConfigDict(extra="forbid")

    status: str
    protocol_version: int = Field(ge=1)
    implementation_version: str = Field(min_length=1)
    implementation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    instance_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    pid: int = Field(gt=0)


def validate_controller_endpoint(url: str) -> str:
    """只接受没有额外 URL 成分的 IPv4 loopback HTTP endpoint。"""

    try:
        parsed = urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError) as error:
        raise ValueError("Controller endpoint 必须是 http://127.0.0.1:<port>") from error

    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or port is None
        or not 1 <= port <= 65535
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Controller endpoint 必须是 http://127.0.0.1:<port>")
    return f"http://127.0.0.1:{port}"


def config_sha256(path) -> str:
    """对 Controller 实际读取的配置原始字节做 SHA-256。"""

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def controller_implementation_sha256() -> str:
    """对常驻 Controller 会加载的 Worker 模块做稳定摘要。"""

    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for relative in sorted(CONTROLLER_IMPLEMENTATION_FILES):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update((root / relative).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def implementation_version() -> str:
    """包版本的唯一运行时来源。"""

    return version(PACKAGE_NAME)
