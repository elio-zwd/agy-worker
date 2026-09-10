"""本机安装管理入口；与 AGY 可调用的任务工具分离。"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tomllib
from datetime import datetime
from pathlib import Path
import tomlkit
from .common import WorkerError, atomic_json, digest
from .controller_client import ControllerClient
from .controller_protocol import PROTOCOL_VERSION
from .models import (WorkerRequest,ContinueRequest,StatusRequest,CancelRequest,
                     ArtifactRequest,CapabilitiesRequest)
from .security import inspect_data_dir_acl

ROOT=Path(__file__).resolve().parents[2]
CODEX_ROUTING_BEGIN="<AGY_WORKER_ROUTING>"
CODEX_ROUTING_END="</AGY_WORKER_ROUTING>"
CODEX_ROUTING_BLOCK=(
    f"{CODEX_ROUTING_BEGIN}\n"
    "当用户要求‘让 AGY/agy’执行已支持的编译、测试、日志、浏览器、图片或 Android UI 任务时，必须走 `agy_worker` MCP；"
    "不得直接用 shell/terminal 调用 `agy`、`agy.exe`、`agy -p`，正常任务也不要先跑 `agy --help` 探测。"
    "MCP 不可用时明确报告，不得静默回退。仅安装、更新、诊断 AGY CLI 本身或 agy-worker 维护脚本明确需要时，才可直接调用 CLI。\n"
    f"{CODEX_ROUTING_END}"
)


def _install_codex_routing(current):
    """在既有 developer_instructions 末尾追加唯一的 Worker 路由块。"""
    if current is None:
        return CODEX_ROUTING_BLOCK
    text=str(current)
    begin_count=text.count(CODEX_ROUTING_BEGIN)
    end_count=text.count(CODEX_ROUTING_END)
    if begin_count or end_count:
        if begin_count==1 and end_count==1 and (
            text==CODEX_ROUTING_BLOCK or text.endswith("\n\n"+CODEX_ROUTING_BLOCK)
        ):
            return text
        raise ValueError("Codex developer_instructions 中存在冲突或损坏的 AGY Worker 路由指令标记，拒绝覆盖")
    return text+"\n\n"+CODEX_ROUTING_BLOCK


def _remove_codex_routing(current):
    """卸载时只删除本安装追加在末尾的路由块，保留用户原有指令。"""
    if current is None:
        return None
    text=str(current)
    if text==CODEX_ROUTING_BLOCK:
        return None
    suffix="\n\n"+CODEX_ROUTING_BLOCK
    if text.endswith(suffix):
        return text[:-len(suffix)]
    if CODEX_ROUTING_BEGIN in text or CODEX_ROUTING_END in text:
        raise ValueError("Codex developer_instructions 中存在冲突或损坏的 AGY Worker 路由指令标记，拒绝覆盖")
    return text


def register(remove=False):
    codex_home=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))
    path=codex_home/'config.toml'
    text=path.read_text('utf-8') if path.exists() else ''
    document=tomlkit.parse(text)
    servers=document.setdefault('mcp_servers',tomlkit.table())
    name='agy_worker'
    current_instructions=document.get('developer_instructions')
    if remove:
        current=servers.get(name)
        if current and Path(str(current.get('command',''))).resolve()!=Path(sys.executable).resolve():
            raise ValueError('已有同名 MCP 不属于本安装，拒绝移除')
        next_instructions=_remove_codex_routing(current_instructions)
        servers.pop(name,None)
        if next_instructions is None:
            if current_instructions is not None:
                document.pop('developer_instructions',None)
        elif current_instructions is not None and next_instructions!=str(current_instructions):
            document['developer_instructions']=next_instructions
    else:
        if name in servers and str(servers[name].get('command',''))!=str(Path(sys.executable)):
            raise ValueError('已有不同路径的同名 MCP，拒绝覆盖')
        next_instructions=_install_codex_routing(current_instructions)
        document['developer_instructions']=next_instructions
        servers[name]={'command':str(Path(sys.executable)),
          'args':['-m','agy_worker.server','--config',str(ROOT/'config/runtime.toml')],
          'startup_timeout_sec':20,'tool_timeout_sec':60,
          'env_vars':['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy','wss_proxy'],
          'enabled_tools':['agy_capabilities','agy_worker','agy_continue','agy_status','agy_cancel','agy_artifact_read']}
    if text:
        backup=ROOT/'work/backups'/('codex-config-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.toml')
        backup.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,backup)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.agy-worker.tmp')
    temporary.write_text(tomlkit.dumps(document),encoding='utf-8')
    os.replace(temporary,path)
    print('已移除本 Worker MCP 注册' if remove else '已注册 Codex MCP agy_worker')


def doctor():
    config=tomllib.loads((ROOT/'config/runtime.toml').read_text('utf-8'))
    executable=Path(config['agy']['executable'])
    help_result=subprocess.run([str(executable),'--help'],capture_output=True,text=True,encoding='utf-8',timeout=20)
    help_text=help_result.stdout+help_result.stderr
    flags=['--conversation','--output-format','--new-project','--add-dir','--print-timeout']
    controller_data_acl=inspect_data_dir_acl(Path(config['data_dir']))
    report={'python':sys.version.split()[0],'platform':sys.platform,'agy_path':str(executable),'agy_sha256':digest(executable),
      'required_flags':{flag:flag in help_text for flag in flags},
      'browser_program_exists':Path(config['browser']['args'][0]).is_file(),
      'enabled_kinds':config['enabled_kinds'],
      'permission_enforcement':'hook_and_broker','os_isolation':False,
      'source_write_enabled':False,'arbitrary_shell_enabled':False,
      'controller_protocol_version':PROTOCOL_VERSION,
      'controller_data_acl':controller_data_acl}
    atomic_json(ROOT/'work/doctor.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if help_result.returncode or not all(report['required_flags'].values()) or not report['browser_program_exists']:
        raise SystemExit(1)


def schemas():
    for name,model in [('agy_capabilities',CapabilitiesRequest),('agy_worker',WorkerRequest),('agy_continue',ContinueRequest),('agy_status',StatusRequest),('agy_cancel',CancelRequest),('agy_artifact_read',ArtifactRequest)]:
        atomic_json(ROOT/'schemas'/(name+'.json'),model.model_json_schema(by_alias=True))


def stop(config_path=None):
    target=Path(config_path).resolve() if config_path else ROOT/'config/runtime.toml'
    try:
        result=ControllerClient.stop_existing(target)
        print(json.dumps(result,ensure_ascii=False))
    except WorkerError as error:
        if error.code=='controller_unavailable':
            print('Controller 当前未运行')
            return
        raise


def main():
    parser=argparse.ArgumentParser()
    subparsers=parser.add_subparsers(dest='command',required=True)
    for name in ('doctor','register','unregister','schemas'):
        subparsers.add_parser(name)
    stop_parser=subparsers.add_parser('stop')
    stop_parser.add_argument('--config')
    args=parser.parse_args()
    if args.command=='stop':
        stop(args.config)
        return
    {'doctor':doctor,'register':register,'unregister':lambda:register(True),'schemas':schemas}[args.command]()


if __name__=='__main__':
    main()
