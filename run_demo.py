import logging
import sys
import socket
import os
import time
import threading


def _free_port(port: int) -> None:
    """如果端口被占用，尝试释放（仅 Windows）"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", port)) != 0:
            return
    import subprocess
    try:
        result = subprocess.check_output(
            f"netstat -ano | findstr :{port}", shell=True, text=True
        )
        for line in result.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5 and f":{port}" in parts[1]:
                pid = parts[-1]
                subprocess.call(f"taskkill /PID {pid} /F", shell=True)
                print(f"[启动] 已释放端口 {port}（PID {pid}）")
                break
    except Exception as e:
        print(f"[启动] 释放端口 {port} 失败: {e}，请手动关闭占用进程")


class _TeeStream:
    """同时写到原始流和日志文件，每行自动加时间戳"""
    def __init__(self, original, log_file):
        self._orig = original
        self._file = log_file
        self._lock = threading.Lock()
        self._buf = ""

    def write(self, data):
        self._orig.write(data)
        self._orig.flush()
        with self._lock:
            self._buf += data
            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                ts = time.strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}"
                self._file.write(f"[{ts}] {line}\n")
                self._file.flush()

    def flush(self):
        self._orig.flush()
        self._file.flush()

    def fileno(self):
        return self._orig.fileno()

    def isatty(self):
        return False


from app.server import run

if __name__ == "__main__":
    log_path = os.path.join(os.path.dirname(__file__), "debug_timing.log")
    _log_file = open(log_path, "w", encoding="utf-8")
    _log_file.write(f"=== InsightEye debug log started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")

    sys.stdout = _TeeStream(sys.__stdout__, _log_file)
    sys.stderr = _TeeStream(sys.__stderr__, _log_file)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    from app import config
    _free_port(config.REALTIME_WS_PORT)
    print(f"[启动] 日志同步写入: {log_path}")
    run(port=8000)
