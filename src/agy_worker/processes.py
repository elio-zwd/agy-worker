"""Windows 任务进程先入 Job 再运行，取消仅影响本任务进程树。"""
import os
import subprocess
import time
from pathlib import Path
import win32api
import win32con
import win32event
import win32file
import win32job
import win32process
import pywintypes
from .common import WorkerError


def run_process(argv, cwd, stdout: Path, stderr: Path, cancel, timeout, *, env=None,
                max_bytes=536870912, progress=None):
    stdout.parent.mkdir(parents=True, exist_ok=True)
    sa = pywintypes.SECURITY_ATTRIBUTES()
    sa.bInheritHandle = True
    handles, process, thread, job = [], None, None, None
    started = time.monotonic()
    reason = None
    try:
        for path, access, disposition in [(stdout, win32con.GENERIC_WRITE, win32con.CREATE_ALWAYS),
                                           (stderr, win32con.GENERIC_WRITE, win32con.CREATE_ALWAYS),
                                           ("NUL", win32con.GENERIC_READ, win32con.OPEN_EXISTING)]:
            handles.append(win32file.CreateFile(str(path), access, win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE,
                                               sa, disposition, 0, None))
        startup = win32process.STARTUPINFO()
        startup.dwFlags = win32con.STARTF_USESTDHANDLES | win32con.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        startup.hStdOutput, startup.hStdError, startup.hStdInput = handles
        job = win32job.CreateJobObject(None, "")
        limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
        limits["BasicLimitInformation"]["LimitFlags"] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)
        process, thread, pid, _ = win32process.CreateProcess(
            str(argv[0]), subprocess.list2cmdline([str(a) for a in argv]), None, None, True,
            win32con.CREATE_SUSPENDED | win32con.CREATE_NO_WINDOW | win32con.CREATE_UNICODE_ENVIRONMENT,
            env or dict(os.environ), str(cwd), startup)
        win32job.AssignProcessToJobObject(job, process)
        win32process.ResumeThread(thread)
        while win32event.WaitForSingleObject(process, 100) == win32con.WAIT_TIMEOUT:
            if progress:
                progress(stdout, pid)
            if cancel.is_set():
                reason = "cancelled"
            elif time.monotonic() - started > timeout:
                reason = "timed_out"
            elif sum(p.stat().st_size for p in (stdout, stderr)) > max_bytes:
                reason = "quota_exceeded"
            if reason:
                win32job.TerminateJobObject(job, 130)
                win32event.WaitForSingleObject(process, 5000)
                break
        if progress:
            progress(stdout, pid)
        return {"pid": pid, "exit_code": win32process.GetExitCodeProcess(process),
                "duration_ms": int((time.monotonic()-started)*1000), "termination_reason": reason}
    finally:
        # 启动或绑定失败也必须停止已创建但尚未运行的进程。
        if process and win32process.GetExitCodeProcess(process) == win32con.STILL_ACTIVE:
            win32process.TerminateProcess(process, 130)
        for handle in [job, thread, process, *handles]:
            if handle:
                handle.Close()
