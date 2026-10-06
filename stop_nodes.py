"""Dừng tất cả NetNode đang chạy.

Đọc PID từ .node_pids và gửi tín hiệu terminate.
"""

import os
import signal
import sys


def main():
    pid_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".node_pids")
    if not os.path.exists(pid_file):
        print("No .node_pids file found. Nodes may not be running.")
        return

    with open(pid_file) as f:
        pids = [int(line.strip()) for line in f if line.strip()]

    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"  Sent SIGTERM to PID {pid}")
        except (ProcessLookupError, PermissionError, OSError) as e:
            print(f"  PID {pid}: {e}")

    try:
        os.remove(pid_file)
    except OSError:
        pass

    print(f"Done. Stopped {len(pids)} node(s).")


if __name__ == "__main__":
    main()
