"""Khởi chạy 3 NetNode trong 3 tiến trình riêng biệt.

Dùng trên Windows: python run_nodes.py
Dừng: Ctrl+C hoặc python stop_nodes.py
"""

import subprocess
import sys
import os
import signal
import time

NODES = [
    ("Node-1", 5001),
    ("Node-2", 5002),
    ("Node-3", 5003),
]

PYTHON = sys.executable
SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_node.py")


def main():
    procs = []
    print("Starting TRUSTMEBRO network (3 nodes)...\n")

    for node_id, port in NODES:
        cmd = [PYTHON, SCRIPT, "--node-id", node_id, "--port", str(port)]
        proc = subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        procs.append((node_id, port, proc))
        print(f"  Started {node_id} on port {port} (PID {proc.pid})")

    print(f"\nAll 3 nodes started. Press Ctrl+C to stop all.\n")

    # Ghi PID ra file để stop_nodes.py dùng
    pid_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".node_pids")
    with open(pid_file, "w") as f:
        for node_id, port, proc in procs:
            f.write(f"{proc.pid}\n")

    try:
        while True:
            # Kiểm tra tiến trình con còn sống không
            for node_id, port, proc in procs:
                if proc.poll() is not None:
                    print(f"  ⚠️ {node_id} (PID {proc.pid}) đã dừng (code {proc.returncode})")
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nStopping all nodes...")
        for node_id, port, proc in procs:
            try:
                if os.name == "nt":
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    proc.terminate()
            except OSError:
                pass
        for node_id, port, proc in procs:
            proc.wait(timeout=5)
            print(f"  Stopped {node_id} (PID {proc.pid})")

        # Xóa PID file
        try:
            os.remove(pid_file)
        except OSError:
            pass
        print("All nodes stopped.")


if __name__ == "__main__":
    main()
