"""验证边界、证据和实际进程行为，不依赖真实模型回复措辞。"""
import json
import sys
import threading
from pathlib import Path
import pytest
from agy_worker.artifacts import Artifacts
from agy_worker.common import WorkerError,safe_path
from agy_worker.logs import extract
from agy_worker.models import Permissions,WorkerRequest
from agy_worker.processes import run_process


@pytest.mark.parametrize("path",["../secret","C:/secret","a:stream","//server/share","a/../b","a./b"])
def test_path_escape(tmp_path,path):
    with pytest.raises(WorkerError):
        safe_path(tmp_path,path,exists=False)


def test_permissions_explicit():
    assert not Permissions().code_write
    with pytest.raises(ValueError):
        Permissions(code_write=True)
    with pytest.raises(ValueError):
        Permissions(browser=True)
    with pytest.raises(ValueError):
        Permissions(unknown=True)


def test_artifact_range_and_integrity(tmp_path):
    path=tmp_path/'log.txt'
    path.write_text('a\nb\nc\n',encoding='utf-8')
    store=Artifacts(tmp_path); store.add('log',path)
    result=store.read('log','text',2,1)
    assert result['text']=='b' and result['next_start_line']==3
    path.write_text('changed',encoding='utf-8')
    with pytest.raises(WorkerError): store.read('log')


def test_extract_duplicate_evidence(tmp_path):
    path=tmp_path/'raw.txt'
    path.write_text('> Task :app:compileDebugKotlin\ne: Role.kt:128:17 Unresolved reference: Card\ne: Role.kt:128:17 Unresolved reference: Card\nw: warning example\n',encoding='utf-8')
    result=extract(path,tmp_path/'clean.txt')
    assert result['errors'][0]['count']==2
    assert result['errors'][0]['line']==128
    assert result['errors'][0]['evidence']['start_line']==2
    assert len(result['warnings'])==1


def test_cancel_real_process_tree(tmp_path):
    cancel=threading.Event()
    timer=threading.Timer(.6,cancel.set);timer.start()
    result=run_process([sys.executable,'-c','import time; time.sleep(30)'],tmp_path,tmp_path/'out',tmp_path/'err',cancel,10)
    assert result['termination_reason']=='cancelled'
    assert result['duration_ms']<5000


def test_timeout_process(tmp_path):
    result=run_process([sys.executable,'-c','import time; time.sleep(30)'],tmp_path,tmp_path/'out',tmp_path/'err',threading.Event(),.3)
    assert result['termination_reason']=='timed_out'


def test_python_syntax_error_location(tmp_path):
    path=tmp_path/'raw.txt'
    path.write_text('  File "sample.py", line 1\n    def add(a,b)\n                ^\nSyntaxError: expected colon\n',encoding='utf-8')
    result=extract(path,tmp_path/'clean.txt')
    assert result['errors'][0]['file']=='sample.py'
    assert result['errors'][0]['line']==1
    assert result['errors'][0]['message']=='SyntaxError: expected colon'


def test_cancel_stops_descendants(tmp_path):
    marker=tmp_path/'should-not-exist.txt'
    child=f"import time; from pathlib import Path; time.sleep(2); Path({str(marker)!r}).write_text('bad')"
    parent=f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(20)"
    cancel=threading.Event()
    timer=threading.Timer(.7,cancel.set);timer.start()
    result=run_process([sys.executable,'-c',parent],tmp_path,tmp_path/'out',tmp_path/'err',cancel,10)
    import time
    time.sleep(2)
    assert result['termination_reason']=='cancelled' and not marker.exists()
