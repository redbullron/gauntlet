"""Owned process trees. No shell evaluation or process-name/PID adoption."""
import os
import signal
import subprocess
import time
from pathlib import Path


class Stopped(RuntimeError):
    pass


def environment(worker=False):
    result = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if (upper.startswith(('CODEX_', 'GAUNTLET_', 'CLAUDE_CODE_', 'ANTHROPIC_', 'OPENAI_'))
                or upper in ('CLAUDECODE', 'CLAUDE_CONFIG_DIR')
                or any(word in upper for word in ('API_KEY', 'AUTH_TOKEN', 'ACCESS_TOKEN', 'SECRET_KEY'))):
            continue
        result[key] = value
    result.update(PYTHONIOENCODING='utf-8', GIT_CONFIG_NOSYSTEM='1',
                  GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0')
    if worker:
        result['GAUNTLET_SPAWN_WORKER'] = '1'
    return result


class Job:
    def __init__(self):
        self.handle = None
        if os.name != 'nt':
            return
        import ctypes as c
        from ctypes import wintypes as w
        class Basic(c.Structure):
            _fields_ = [('PerProcessUserTimeLimit', c.c_int64), ('PerJobUserTimeLimit', c.c_int64),
                        ('LimitFlags', w.DWORD), ('MinimumWorkingSetSize', c.c_size_t),
                        ('MaximumWorkingSetSize', c.c_size_t), ('ActiveProcessLimit', w.DWORD),
                        ('Affinity', c.c_size_t), ('PriorityClass', w.DWORD), ('SchedulingClass', w.DWORD)]
        class IO(c.Structure):
            _fields_ = [(name, c.c_uint64) for name in ('ReadOperationCount', 'WriteOperationCount',
                        'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]
        class Extended(c.Structure):
            _fields_ = [('BasicLimitInformation', Basic), ('IoInfo', IO), ('ProcessMemoryLimit', c.c_size_t),
                        ('JobMemoryLimit', c.c_size_t), ('PeakProcessMemoryUsed', c.c_size_t),
                        ('PeakJobMemoryUsed', c.c_size_t)]
        self.c = c
        self.kernel = c.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = w.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
        self.kernel.SetInformationJobObject.restype = w.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = w.BOOL
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        self.kernel.CloseHandle.restype = w.BOOL
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise c.WinError(c.get_last_error())
        limits = Extended()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, c.byref(limits), c.sizeof(limits)):
            error = c.WinError(c.get_last_error())
            self.close()
            raise error

    def attach_and_resume(self, process):
        if os.name != 'nt':
            return
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise self.c.WinError(self.c.get_last_error())
        resume = self.c.WinDLL('ntdll').NtResumeProcess
        resume.argtypes = [self.c.c_void_p]
        resume.restype = self.c.c_long
        status = resume(int(process._handle))
        if status != 0:
            raise OSError(f'NtResumeProcess failed: {status}')

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def run(command, cwd, output, *, input_path=None, timeout=900, cancelled=lambda: False, worker=False):
    if cancelled():
        raise Stopped('cancelled')
    if timeout <= 0:
        raise Stopped('limit_reached')
    process = None
    job = Job()
    started = time.monotonic()
    max_output = 25 * 1024 * 1024
    try:
        with open(input_path or os.devnull, 'rb') as source, open(output, 'wb') as log:
            process = subprocess.Popen(command, cwd=cwd, stdin=source, stdout=log,
                                       stderr=subprocess.STDOUT, env=environment(worker), shell=False,
                                       creationflags=(subprocess.CREATE_NO_WINDOW | 0x4) if os.name == 'nt' else 0,
                                       start_new_session=os.name != 'nt')
            job.attach_and_resume(process)
            while process.poll() is None:
                if cancelled():
                    raise Stopped('cancelled')
                if time.monotonic() - started >= timeout:
                    raise Stopped('limit_reached')
                if Path(output).stat().st_size > max_output:
                    raise Stopped('output_limit')
                time.sleep(0.1)
            if Path(output).stat().st_size > max_output:
                raise Stopped('output_limit')
            return process.returncode
    finally:
        job.close()
        if process is not None:
            if os.name != 'nt':
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif process.poll() is None:
                process.kill()
            process.wait(timeout=10)
