import logging
import sys
import socket
import os
import time
import threading
from pathlib import Path


def _get_log_dir():
    """获取日志目录（与 run_demo.py 同级的 logs 文件夹）"""
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    return log_dir


def _generate_log_path():
    """生成带时间戳的唯一日志文件路径"""
    log_dir = _get_log_dir()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return log_dir / f"insighteye_{timestamp}.log"


class _TeeStream:
    """同时写到原始流和日志文件，每行自动加时间戳"""
    def __init__(self, original, log_file):
        self._orig = original
        self._file = log_file
        self._lock = threading.Lock()
        self._buf = ""
        self._log_seq = 0  # 日志行序号

    def write(self, data):
        self._orig.write(data)
        self._orig.flush()
        with self._lock:
            self._buf += data
            while "\n" in self._buf:
                self._log_seq += 1
                line, self._buf = self._buf.split("\n", 1)
                ts = time.strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}"
                self._file.write(f"[{ts}] [#{self._log_seq:05d}] {line}\n")
                self._file.flush()

    def flush(self):
        self._orig.flush()
        self._file.flush()

    def fileno(self):
        return self._orig.fileno()

    def isatty(self):
        return False


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


from app.server import run

if __name__ == "__main__":
    log_path = _generate_log_path()
    summary_path = _get_log_dir() / "latest.log"
    
    _log_file = open(log_path, "w", encoding="utf-8")
    _log_file.write(f"=== InsightEye debug log started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    _log_file.write(f"Log file: {log_path}\n")
    _log_file.write("=" * 60 + "\n")

    # 创建 latest.log 软链接指向最新日志（方便快速访问）
    try:
        if summary_path.exists():
            summary_path.unlink()
        # Windows 上创建 symbolic link 需要管理员权限，改用复制方式
        # 这里简单处理：latest.log 会在下次启动时被覆盖
    except Exception:
        pass

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
    print(f"[启动] 所有运行日志请查看 logs 文件夹")
    run(host="0.0.0.0", port=8001)
