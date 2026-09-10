"""隔离验证两个 stdio Bridge 共享常驻 Controller，并可安全清理目标实例。"""
import argparse
import asyncio
import json
import sys
import tomllib
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agy_worker.common import WorkerError
from agy_worker.controller_client import ControllerClient
from agy_worker.controller_state import implementation_version

EXPECTED_VERSION = "0.3.1"
EXPECTED_PROTOCOL = 2
EXPECTED_TOOL_COUNT = 6
EXPECTED_MAX_CONCURRENT = 1
EXPECTED_MAX_INFLIGHT = 16


@asynccontextmanager
async def bridge(config):
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "agy_worker.server", "--config", str(config)],
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            initialized = await session.initialize()
            yield initialized, session


def controller_state_path(config):
    value = tomllib.loads(Path(config).read_text("utf-8"))
    return Path(value["data_dir"]).resolve() / "controller.json"


def stop_for_fresh_start(config):
    """清理 --fresh 的既有目标；state 仍存在但暂时不可达时必须 fail-closed。"""
    try:
        result = ControllerClient.stop_existing(config, timeout=10)
    except WorkerError as error:
        if error.code == "controller_unavailable":
            # stop_existing 的 controller_unavailable 既可能代表“根本没有 state”，
            # 也可能代表“已有 state 但 stop 请求暂时无法连接”。--fresh 只能把前者
            # 视为干净起点，后者必须停止验收，避免把可疑旧实例当成不存在。
            return "unreachable" if controller_state_path(config).exists() else "not_running"
        raise
    return result.get("status", "unknown")


async def verify_bridges(config):
    async with AsyncExitStack() as stack:
        first_init, first = await stack.enter_async_context(bridge(config))
        second_init, second = await stack.enter_async_context(bridge(config))
        first_tools = await first.list_tools()
        second_tools = await second.list_tools()
        capabilities = await second.call_tool("agy_capabilities", {})
        first_tool_count = len(first_tools.tools)
        second_tool_count = len(second_tools.tools)
        result = {
            "first_server_version": first_init.server_info.version,
            "second_server_version": second_init.server_info.version,
            "tool_count": first_tool_count,
            "second_tool_count": second_tool_count,
            "workspace_count": len(capabilities.structured_content["workspaces"]),
        }

    # 两个 stdio Bridge 都已关闭。此处必须用 autostart=False 证明同一后台
    # Controller 仍然活着，不能因为验收查询本身又悄悄拉起一个新实例。
    controller = ControllerClient(config, autostart=False)
    status = controller.call("capabilities")
    result.update(
        controller_pid=controller.state["pid"],
        controller_instance_id=controller.state["instance_id"],
        controller_protocol=controller.state["protocol_version"],
        controller_alive_after_bridges=True,
        max_concurrent_tasks=status["controller"]["max_concurrent_tasks"],
        max_inflight_tasks=status["controller"]["max_inflight_tasks"],
    )
    return result


def evaluate(result, *, fresh_status=None, stop_after_requested=False):
    """把验收合同转成显式 checks；任何缺口都让脚本非零退出。"""
    expected_version = implementation_version()
    checks = {
        "package_version_is_0_3_1": expected_version == EXPECTED_VERSION,
        "first_server_version_matches_package": result.get("first_server_version") == expected_version,
        "second_server_version_matches_package": result.get("second_server_version") == expected_version,
        "first_bridge_has_six_tools": result.get("tool_count") == EXPECTED_TOOL_COUNT,
        "second_bridge_has_six_tools": result.get("second_tool_count") == EXPECTED_TOOL_COUNT,
        "controller_protocol_is_v2": result.get("controller_protocol") == EXPECTED_PROTOCOL,
        "controller_instance_id_present": bool(result.get("controller_instance_id")),
        "controller_pid_positive": isinstance(result.get("controller_pid"), int) and result["controller_pid"] > 0,
        "controller_alive_after_bridges": result.get("controller_alive_after_bridges") is True,
        "max_concurrent_tasks_is_one": result.get("max_concurrent_tasks") == EXPECTED_MAX_CONCURRENT,
        "max_inflight_tasks_is_sixteen": result.get("max_inflight_tasks") == EXPECTED_MAX_INFLIGHT,
    }
    if fresh_status is not None:
        checks["fresh_started_from_clean_target"] = fresh_status in ("not_running", "stopped")
    if stop_after_requested:
        checks["same_instance_stopped_after_verification"] = result.get("stopped_after_verification") is True
    result["checks"] = checks
    result["verification_passed"] = all(checks.values())
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="验收前停止该配置现有 Controller；若出现 replacement/不可达 state 则拒绝继续",
    )
    parser.add_argument(
        "--stop-after",
        action="store_true",
        help="验收后只停止本次观察到的同一 instance_id",
    )
    args = parser.parse_args()
    config = Path(args.config).resolve()

    fresh_status = None
    if args.fresh:
        fresh_status = stop_for_fresh_start(config)
        if fresh_status not in ("not_running", "stopped"):
            result = evaluate(
                {
                    "fresh_stop_status": fresh_status,
                    "stopped_after_verification": False,
                },
                fresh_status=fresh_status,
                stop_after_requested=args.stop_after,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise SystemExit(1)

    result = asyncio.run(verify_bridges(config))
    if fresh_status is not None:
        result["fresh_stop_status"] = fresh_status

    result["stopped_after_verification"] = False
    if args.stop_after:
        try:
            stop_result = ControllerClient.stop_existing(
                config,
                expected_instance_id=result["controller_instance_id"],
                timeout=10,
            )
            result["stop_after_status"] = stop_result.get("status", "unknown")
            result["stopped_after_verification"] = stop_result.get("status") == "stopped"
        except WorkerError as error:
            result["stop_after_status"] = error.code
            result["stop_after_error"] = str(error)

    evaluate(
        result,
        fresh_status=fresh_status,
        stop_after_requested=args.stop_after,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["verification_passed"] else 1)


if __name__ == "__main__":
    main()
