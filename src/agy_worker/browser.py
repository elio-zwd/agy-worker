"""复用已有 Chrome DevTools MCP 程序，使用单独的浏览器实例。"""
import asyncio
import concurrent.futures
import json
import threading
from mcp.client import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp import types
from .common import WorkerError


class Browser:
    def __init__(self, config, log_path):
        self.config = config
        self.log_path = log_path
        self.ready = concurrent.futures.Future()
        self.thread = threading.Thread(target=self._thread, daemon=True)
        self.thread.start()
        self.ready.result(45)

    def _thread(self):
        try:
            asyncio.run(self._serve())
        except BaseException as error:
            if not self.ready.done():
                self.ready.set_exception(error)

    async def _serve(self):
        self.loop = asyncio.get_running_loop()
        self.queue = asyncio.Queue()
        options = StdioServerParameters(command=self.config["command"], args=self.config["args"])
        async def roots(context):
            # 截图只可写入当前任务证据目录，不向浏览器开放项目或整个磁盘。
            return types.ListRootsResult(roots=[types.Root(uri=self.log_path.parent.resolve().as_uri(), name="task-evidence")])
        with open(self.log_path, "w", encoding="utf-8") as errlog:
            async with stdio_client(options, errlog=errlog) as (reader, writer):
                async with ClientSession(reader, writer, list_roots_callback=roots) as client:
                    await client.initialize()
                    self.tools = {t.name: t.input_schema for t in (await client.list_tools()).tools}
                    self.ready.set_result(True)
                    while True:
                        request = await self.queue.get()
                        if request is None:
                            return
                        name, arguments, future = request
                        try:
                            result = await client.call_tool(name, arguments, read_timeout_seconds=40)
                            future.set_result(result.model_dump(mode="json", exclude_none=True, by_alias=True))
                        except Exception as error:
                            future.set_exception(error)

    def call(self, name, arguments):
        if not self.thread.is_alive():
            raise WorkerError("runtime_error", "浏览器执行器已停止")
        future = concurrent.futures.Future()
        self.loop.call_soon_threadsafe(self.queue.put_nowait, (name, arguments, future))
        return future.result(45)

    def close(self):
        if self.thread.is_alive():
            self.loop.call_soon_threadsafe(self.queue.put_nowait, None)
            self.thread.join(50)
