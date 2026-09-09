"""常驻 Controller：唯一持有 Runtime，并向本机 Bridge 提供受控 IPC。"""
import argparse
import json
import os
import signal
import sys
import threading
from pathlib import Path

from .common import WorkerError, atomic_json, now
from .controller_protocol import CONTROLLER_STATE_FILE, PROTOCOL_VERSION
from .runtime import Runtime


class ControllerService:
    """管理唯一 Runtime 的生命周期，并在就绪后发布连接信息。"""

    def __init__(self, config_path):
        self.config_path = Path(config_path).resolve()
        self.stop_event = threading.Event()
        self.runtime = Runtime(
            self.config_path,
            control_token=os.urandom(32).hex(),
            control_stop=self.stop_event.set,
        )
        self.state_path = self.runtime.root / CONTROLLER_STATE_FILE
        self.state = {
            "protocol_version": PROTOCOL_VERSION,
            "pid": os.getpid(),
            "endpoint": self.runtime.endpoint,
            "token": self.runtime.control_token,
            "config_path": str(self.config_path),
            "started_at": now(),
        }
        # 只有 Runtime、HTTP 监听和鉴权都就绪后才发布，Bridge 不会连到半启动进程。
        atomic_json(self.state_path, self.state)

    def wait(self):
        self.stop_event.wait()

    def close(self):
        self.runtime.close()
        try:
            current = json.loads(self.state_path.read_text("utf-8"))
            if current.get("pid") == os.getpid() and current.get("token") == self.state["token"]:
                self.state_path.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass


def run(config_path):
    service = ControllerService(config_path)

    def request_stop(_signum, _frame):
        service.stop_event.set()

    for name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), request_stop)
    try:
        service.wait()
    finally:
        service.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--environment-file")
    parser.add_argument("--log-file")
    args = parser.parse_args()
    if args.environment_file:
        environment_path = Path(args.environment_file)
        try:
            values = json.loads(environment_path.read_text("utf-8"))
            os.environ.update({key: value for key, value in values.items() if isinstance(value, str)})
        finally:
            environment_path.unlink(missing_ok=True)
    log = None
    if args.log_file:
        log_path = Path(args.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = log_path.open("a", encoding="utf-8", buffering=1)
        sys.stdout = log
        sys.stderr = log
    try:
        run(args.config)
    except WorkerError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        raise SystemExit(2) from error
    finally:
        if log:
            log.close()


if __name__ == "__main__":
    main()
