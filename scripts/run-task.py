"""通过 stdio MCP 运行请求文件，用于部署验收和独立诊断。"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from mcp.client import ClientSession
from mcp.client.stdio import StdioServerParameters,stdio_client

ROOT=Path(__file__).resolve().parents[1]


async def run(args):
    request=json.loads(Path(args.request).read_text('utf-8-sig'))
    environment={key:value for key,value in os.environ.items() if key.lower().endswith('_proxy')}
    config=Path(args.config).resolve() if args.config else ROOT/'config/runtime.toml'
    options=StdioServerParameters(command=sys.executable,args=['-m','agy_worker.server','--config',str(config)],env=environment)
    async with stdio_client(options) as (reader,writer):
        async with ClientSession(reader,writer) as client:
            await client.initialize()
            tool='agy_continue' if 'session_id' in request else 'agy_worker'
            response=await client.call_tool(tool,request)
            state=json.loads(response.content[0].text)
            if 'task_id' not in state:
                print(json.dumps(state,ensure_ascii=False,indent=2));return 1
            print('任务已提交：'+state['task_id'],flush=True)
            while state['status'] not in ('succeeded','failed','cancelled','timed_out','interrupted'):
                response=await client.call_tool('agy_status',{'task_id':state['task_id'],'after_revision':state['revision'],'wait_ms':25000},read_timeout_seconds=30)
                state=json.loads(response.content[0].text)
            if args.output:
                Path(args.output).write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(state,ensure_ascii=False,indent=2),flush=True)
            return 0 if state['status']=='succeeded' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('request');parser.add_argument('--output')
    parser.add_argument('--config',help='使用指定 Runtime 配置，默认使用正式配置')
    raise SystemExit(asyncio.run(run(parser.parse_args())))
