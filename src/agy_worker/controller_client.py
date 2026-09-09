"""stdio Bridge 使用的 Controller 启动器与 HTTP 客户端。"""
import json
import os
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

from pydantic import ValidationError

from .common import WorkerError, atomic_json
from .controller_protocol import CONTROLLER_LAUNCH_LOCK, CONTROLLER_STATE_FILE, PROTOCOL_VERSION
from .controller_state import (
    ControllerHealth,
    ControllerState,
    LegacyControllerState,
    config_sha256,
    controller_implementation_sha256,
    implementation_version,
    validate_controller_endpoint,
)


class ControllerClient:
    def __init__(self, config_path, *, startup_timeout=15, autostart=True):
        self.config_path = Path(config_path).resolve()
        config = tomllib.loads(self.config_path.read_text("utf-8"))
        self.data_dir = Path(config["data_dir"]).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.data_dir / CONTROLLER_STATE_FILE
        self.current_config_sha256 = config_sha256(self.config_path)
        self.current_implementation_version = implementation_version()
        self.current_implementation_sha256 = controller_implementation_sha256()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.last_launch_pid = None
        if autostart:
            self.state = self._ensure(startup_timeout)
        else:
            self.state = self._read_state()
            if not self._healthy(self.state):
                raise WorkerError("controller_unavailable", "AGY Worker Controller 当前未运行")

    @staticmethod
    def _invalid_state(message="Controller 连接元数据无效"):
        return WorkerError("controller_state_invalid", message)

    @staticmethod
    def _management_state(config_path, state_path):
        """读取显式管理操作所需的 legacy state，不套用当前 Bridge 身份检查。"""
        try:
            value = json.loads(state_path.read_text("utf-8"))
        except FileNotFoundError:
            return None
        except (ValueError, OSError) as error:
            raise ControllerClient._invalid_state() from error

        try:
            legacy = LegacyControllerState.model_validate(value)
            endpoint = validate_controller_endpoint(legacy.endpoint)
            state_config_path = Path(legacy.config_path).resolve()
        except (ValidationError, ValueError, TypeError, OSError) as error:
            raise ControllerClient._invalid_state(
                "Controller 管理元数据无效；endpoint 必须是 http://127.0.0.1:<port>"
            ) from error
        if state_config_path != config_path:
            raise WorkerError("controller_conflict", "数据目录正由另一份配置使用")
        return value, legacy, endpoint

    @staticmethod
    def stop_existing(config_path, timeout=10):
        """显式停止指定配置的现有 Controller，并等待目标实例真实退出。"""
        config_path = Path(config_path).resolve()
        config = tomllib.loads(config_path.read_text("utf-8"))
        data_dir = Path(config["data_dir"]).resolve()
        state_path = data_dir / CONTROLLER_STATE_FILE
        initial = ControllerClient._management_state(config_path, state_path)
        if initial is None:
            raise WorkerError("controller_unavailable", "AGY Worker Controller 当前未运行")

        raw_state, legacy, endpoint = initial
        target_instance_id = raw_state.get("instance_id")
        if not isinstance(target_instance_id, str) or not target_instance_id:
            target_instance_id = None
        target_pid = legacy.pid
        target_token = legacy.token
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def request(state_value, request_endpoint, path, payload=None, request_timeout=1):
            body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
            request_object = urllib.request.Request(
                request_endpoint + path,
                data=body,
                method="GET" if payload is None else "POST",
                headers={
                    "Authorization": "Bearer " + state_value["token"],
                    "Content-Type": "application/json",
                },
            )
            try:
                with opener.open(request_object, timeout=request_timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except (urllib.error.URLError, TimeoutError, ValueError, OSError) as error:
                raise WorkerError("controller_unavailable", "AGY Worker Controller 无法连接") from error

        stop_timeout = max(0.1, min(float(timeout), 3.0))
        response = request(
            raw_state,
            endpoint,
            "/control/stop",
            {"protocol_version": legacy.protocol_version},
            request_timeout=stop_timeout,
        )
        if not response.get("ok"):
            error = response.get("error", {})
            raise WorkerError(
                error.get("code", "runtime_error"),
                error.get("message", "Controller 停止请求失败"),
            )

        deadline = time.monotonic() + max(0.1, float(timeout))
        while time.monotonic() < deadline:
            current = ControllerClient._management_state(config_path, state_path)
            if current is None:
                return {"ok": True, "status": "stopped"}
            current_raw, current_legacy, current_endpoint = current

            if target_instance_id is not None:
                if current_raw.get("instance_id") != target_instance_id:
                    return {"ok": True, "status": "replaced"}
            elif current_legacy.pid != target_pid or current_legacy.token != target_token:
                return {"ok": True, "status": "replaced"}

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                health = request(
                    current_raw,
                    current_endpoint,
                    "/control/health",
                    request_timeout=min(0.5, remaining),
                )
            except WorkerError as error:
                if error.code == "controller_unavailable":
                    return {"ok": True, "status": "stopped"}
                raise

            if health.get("status") != "ready":
                return {"ok": True, "status": "stopped"}
            if target_instance_id is not None and health.get("instance_id") not in (None, target_instance_id):
                return {"ok": True, "status": "replaced"}
            if target_instance_id is None and health.get("pid") not in (None, target_pid):
                return {"ok": True, "status": "replaced"}
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

        raise WorkerError("controller_stop_timeout", "Controller 未在超时内完全退出")

    def _read_state(self):
        try:
            value = json.loads(self.state_path.read_text("utf-8"))
        except FileNotFoundError:
            return None
        except (ValueError, OSError) as error:
            raise self._invalid_state() from error

        try:
            legacy = LegacyControllerState.model_validate(value)
            validate_controller_endpoint(legacy.endpoint)
        except (ValidationError, ValueError, TypeError) as error:
            raise self._invalid_state("Controller 连接元数据无效；endpoint 必须是 http://127.0.0.1:<port>") from error

        try:
            state_config_path = Path(legacy.config_path).resolve()
        except (OSError, TypeError, ValueError) as error:
            raise self._invalid_state("Controller config_path 无效") from error
        if state_config_path != self.config_path:
            raise WorkerError("controller_conflict", "数据目录正由另一份配置使用")

        # 当前协议必须在任何网络访问前通过严格 state 校验；旧协议只保留
        # 管理/诊断所需的最小字段，是否真的有活实例由 authenticated health 证明。
        if legacy.protocol_version != PROTOCOL_VERSION:
            return legacy.model_dump()
        try:
            return ControllerState.model_validate(value).model_dump()
        except ValidationError as error:
            raise self._invalid_state("当前协议的 Controller state 缺失身份字段或包含未知字段") from error

    def _request(self, state, path, payload=None, timeout=30):
        try:
            endpoint = validate_controller_endpoint(state["endpoint"])
        except (KeyError, TypeError, ValueError) as error:
            raise self._invalid_state("Controller endpoint 必须是 http://127.0.0.1:<port>") from error

        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            endpoint + path,
            data=body,
            method="GET" if payload is None else "POST",
            headers={"Authorization": "Bearer " + state["token"], "Content-Type": "application/json"},
        )
        try:
            with self.opener.open(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as error:
            raise WorkerError("controller_unavailable", "AGY Worker Controller 无法连接") from error

    def _healthy(self, state):
        if not state:
            return False
        try:
            result = self._request(state, "/control/health", timeout=0.8)
        except WorkerError as error:
            if error.code == "controller_unavailable":
                return False
            raise

        # 先由 Bearer health 证明 endpoint 对应的是活 Controller，再判断协议和
        # stale 身份；否则残留 controller.json 可能被误报成仍在运行的旧实例。
        if result.get("protocol_version") != PROTOCOL_VERSION:
            raise WorkerError("protocol_mismatch", "Controller 与 Bridge 协议版本不一致，请停止旧 Controller 后重试")
        if state.get("protocol_version") != PROTOCOL_VERSION:
            raise WorkerError("protocol_mismatch", "Controller 与 Bridge 协议版本不一致，请停止旧 Controller 后重试")

        try:
            health = ControllerHealth.model_validate(result)
        except ValidationError as error:
            raise self._invalid_state("Controller health 身份结构无效") from error

        if health.config_sha256 != self.current_config_sha256:
            raise WorkerError("controller_stale_config", "后台 Controller 仍使用旧配置；请显式停止旧 Controller 后重试")
        if (
            health.implementation_version != self.current_implementation_version
            or health.implementation_sha256 != self.current_implementation_sha256
        ):
            raise WorkerError("controller_stale_implementation", "后台 Controller 仍运行旧 Worker 实现；请显式停止旧 Controller 后重试")

        identity_keys = (
            "protocol_version",
            "implementation_version",
            "implementation_sha256",
            "config_sha256",
            "instance_id",
            "pid",
        )
        if any(state[key] != getattr(health, key) for key in identity_keys):
            raise self._invalid_state("Controller state 与 health 不是同一个实例")
        return health.status == "ready"

    def _launch_windows(self, log_dir):
        """通过 WMI 服务创建进程，避免 Controller 被 stdio MCP 的 Job Object 回收。"""
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        pwsh = shutil.which("pwsh.exe")
        if not pythonw.is_file() or not pwsh:
            raise WorkerError("dependency_missing", "启动 Controller 需要 pythonw.exe 与 PowerShell 7")
        environment_file = self.data_dir / "controller-environment.json"
        proxy_names = {
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
            "http_proxy", "https_proxy", "all_proxy", "no_proxy", "wss_proxy",
        }
        atomic_json(environment_file, {name: os.environ[name] for name in proxy_names if name in os.environ})
        command = subprocess.list2cmdline([
            str(pythonw), "-m", "agy_worker.controller", "--config", str(self.config_path),
            "--environment-file", str(environment_file), "--log-file", str(log_dir / "controller.log"),
        ])
        environment = dict(os.environ)
        environment["AGY_WORKER_CONTROLLER_COMMAND"] = command
        script = (
            "$created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
            "-Arguments @{CommandLine=$env:AGY_WORKER_CONTROLLER_COMMAND}; "
            "if ($created.ReturnValue -ne 0) { exit $created.ReturnValue }; "
            "Write-Output $created.ProcessId"
        )
        result = subprocess.run(
            [pwsh, "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            env=environment,
            timeout=15,
        )
        if result.returncode:
            environment_file.unlink(missing_ok=True)
            raise WorkerError("controller_start_failed", "Windows WMI 无法创建 Controller 进程")
        try:
            pid = int(result.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError) as error:
            raise WorkerError("controller_start_failed", "Windows WMI 未返回有效 Controller PID") from error
        if pid <= 0:
            raise WorkerError("controller_start_failed", "Windows WMI 返回了无效 Controller PID")
        return pid

    def _launch(self):
        log_dir = self.data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            return self._launch_windows(log_dir)
        stdout = (log_dir / "controller.stdout.log").open("ab")
        stderr = (log_dir / "controller.stderr.log").open("ab")
        try:
            process = subprocess.Popen(
                [sys.executable, "-m", "agy_worker.controller", "--config", str(self.config_path)],
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                close_fds=True,
                creationflags=0,
                start_new_session=True,
            )
            return process.pid
        finally:
            stdout.close()
            stderr.close()

    def _ensure(self, startup_timeout):
        """在同一 deadline 内反复观察 health、抢启动锁并按 cooldown 重试。"""
        import msvcrt

        deadline = time.monotonic() + startup_timeout
        next_launch_at = 0.0
        last_launch_error = None
        lock_path = self.data_dir / CONTROLLER_LAUNCH_LOCK

        while time.monotonic() < deadline:
            state = self._read_state()
            if self._healthy(state):
                return state

            lock_file = lock_path.open("a+b")
            lock_file.seek(0)
            acquired = False
            try:
                try:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    acquired = True
                except OSError:
                    pass

                if acquired:
                    # 抢到锁后再次检查，避免另一个 owner 刚刚把 Controller 启好。
                    state = self._read_state()
                    if self._healthy(state):
                        return state
                    now_monotonic = time.monotonic()
                    if now_monotonic >= next_launch_at:
                        try:
                            self.last_launch_pid = self._launch()
                            last_launch_error = None
                        except WorkerError as error:
                            if error.code == "dependency_missing":
                                raise
                            last_launch_error = error
                        next_launch_at = time.monotonic() + 0.5
            finally:
                if acquired:
                    lock_file.seek(0)
                    try:
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
                lock_file.close()

            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(0.1, remaining))

        if last_launch_error is not None:
            raise WorkerError(
                "controller_start_failed",
                f"Controller 启动失败：{last_launch_error}；请查看 {self.data_dir / 'logs' / 'controller.log'}",
            ) from last_launch_error
        raise WorkerError(
            "controller_start_failed",
            f"Controller 未在 {startup_timeout} 秒内就绪；请查看 {self.data_dir / 'logs' / 'controller.log'}",
        )

    def call(self, method, params=None, *, timeout=30):
        payload = {"protocol_version": PROTOCOL_VERSION, "method": method, "params": params or {}}
        try:
            response = self._request(self.state, "/control/call", payload, timeout=timeout)
        except WorkerError as error:
            if error.code != "controller_unavailable":
                raise
            # 所有任务级调用都具备幂等标识或只读/幂等语义，可以在重连后安全重试一次。
            self.state = self._ensure(15)
            response = self._request(self.state, "/control/call", payload, timeout=timeout)
        if not response.get("ok"):
            error = response.get("error", {})
            raise WorkerError(error.get("code", "runtime_error"), error.get("message", "Controller 调用失败"))
        return response.get("result")

    def stop(self):
        response = self._request(
            self.state,
            "/control/stop",
            {"protocol_version": PROTOCOL_VERSION},
            timeout=3,
        )
        return response
