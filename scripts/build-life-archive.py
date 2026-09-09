"""导入隔离副本并验证 HBuilderX Android 资源导出；不修改应用源码。"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = Path(r'D:\HBuilderX\HBuilderX\cli.exe')
NODE = Path(r'D:\Program Files\nodejs\node.exe')


def run(argv):
    process = subprocess.run([str(x) for x in argv], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    output = process.stdout.decode('utf-8', errors='replace')
    print(output, flush=True)
    # HBuilderX 某些业务错误返回 0，不能只依赖进程退出码。
    failures = ('不存在，请先导入', '编译失败', '导出失败', '此功能需要先登录', 'Please Login in!')
    return process.returncode or (1 if any(text in output for text in failures) else 0)


def main():
    workspace = Path.cwd().resolve()
    if workspace.parent != (ROOT / 'data/sessions').resolve():
        raise RuntimeError('只允许在 Worker 会话副本内导出')
    code = run([CLI, 'project', 'open', '--path', workspace])
    if code:
        return code
    started = time.time()
    try:
        code = run([NODE, 'scripts/build-app-android.mjs', '--type', 'appResource'])
        if code:
            return code
        manifests = list(workspace.glob('unpackage/resources/*/www/manifest.json'))
        if not any(path.stat().st_mtime >= started - 2 for path in manifests):
            print('ERROR: 未发现本轮生成的 Android 资源 manifest.json，不能确认导出成功。', flush=True)
            return 1
        print('Android 资源导出验证成功：' + ', '.join(str(p.parent) for p in manifests), flush=True)
        return 0
    finally:
        # 只关闭本轮导入的副本，不关闭用户原项目或共享 HBuilderX 进程。
        run([CLI, 'project', 'close', '--path', workspace])


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
