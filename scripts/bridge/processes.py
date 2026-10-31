"""Small process runner; no shell interpolation, one process tree at a time."""
import ctypes
import os
import subprocess
import time
from pathlib import Path


class WindowsJob:
    """Kill all worker descendants if the coordinator exits, including on a crash."""
    def __init__(self):
        self.handle = None
        if os.name != 'nt':
            return
        from ctypes import wintypes as w
        class Basic(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                        ('flags', w.DWORD), ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t),
                        ('active', w.DWORD), ('affinity', ctypes.c_size_t),
                        ('priority', w.DWORD), ('scheduling', w.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ('ro', 'wo', 'oo', 'rb', 'wb', 'ob')]
        class Extended(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', IO), ('process_memory', ctypes.c_size_t),
                        ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t),
                        ('peak_job', ctypes.c_size_t)]
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        self.k.CreateJobObjectW.restype = w.HANDLE
        self.k.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        self.k.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        self.k.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.k.CloseHandle.argtypes = [w.HANDLE]
        self.handle = self.k.CreateJobObjectW(None, None)
        info = Extended()
        info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not self.k.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise OSError(ctypes.get_last_error(), 'Cannot create worker job object')

    def attach(self, proc):
        if self.handle and not self.k.AssignProcessToJobObject(self.handle, int(proc._handle)):
            proc.kill()
            proc.wait()
            raise OSError(ctypes.get_last_error(), 'Cannot contain worker process tree')

    def close(self):
        if self.handle:
            self.k.CloseHandle(self.handle)
            self.handle = None


def run(command, cwd, output, *, input_text=None, timeout=900, cancelled=lambda: False, env=None):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    child_env = os.environ.copy()
    # Do not inherit the launching desktop chat's permissions, IPC endpoints or identity.
    for key in list(child_env):
        if key.startswith('CODEX_') and key != 'CODEX_HOME':
            child_env.pop(key)
    child_env.update(env or {})
    child_env.pop('CLAUDECODE', None)
    child_env['PYTHONIOENCODING'] = 'utf-8'
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    job = WindowsJob()
    try:
        with output.open('wb') as log:
            proc = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, env=child_env,
                                    creationflags=flags, start_new_session=os.name != 'nt')
            job.attach(proc)
            if input_text is not None:
                try:
                    proc.stdin.write(input_text.encode('utf-8'))
                    proc.stdin.close()
                except BrokenPipeError:
                    pass
            deadline = time.monotonic() + timeout
            while proc.poll() is None:
                if cancelled() or time.monotonic() >= deadline or output.stat().st_size > 25 * 1024 * 1024:
                    reason = 'Cancelled' if cancelled() else 'Worker time or output limit reached'
                    if os.name == 'nt':
                        job.close()
                    else:
                        import signal
                        os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=15)
                    raise RuntimeError(reason)
                time.sleep(0.25)
            return proc.returncode
    finally:
        job.close()
