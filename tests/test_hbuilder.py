"""覆盖 HBuilderX 业务失败却返回 0 的真实回归场景。"""
import importlib.util
import subprocess
from pathlib import Path

spec = importlib.util.spec_from_file_location('hbuilder_adapter', Path(__file__).parents[1] / 'scripts/build-life-archive.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def test_zero_exit_import_failure(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a, 0, '项目不存在，请先导入'.encode()))
    assert adapter.run(['unused']) == 1


def test_preserve_nonzero_exit(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a, 7, b''))
    assert adapter.run(['unused']) == 7
