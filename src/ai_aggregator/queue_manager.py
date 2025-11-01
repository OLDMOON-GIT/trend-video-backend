"""
Simple file-based queue manager for concurrent request handling
서버 환경에서 여러 요청을 순차적으로 처리하기 위한 큐 시스템
"""

import os
import sys
import time
import json
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime

# Windows와 Unix 모두 지원
if sys.platform == 'win32':
    import msvcrt
else:
    import fcntl


class QueueManager:
    """File-based queue manager using file locking"""

    def __init__(self, queue_dir: str = ".queue"):
        self.queue_dir = Path(queue_dir)
        self.queue_dir.mkdir(exist_ok=True)
        self.lock_file = self.queue_dir / "queue.lock"
        self.queue_file = self.queue_dir / "queue.json"
        self.lock_fd = None

    def acquire_lock(self, timeout: int = 300) -> bool:
        """
        Acquire exclusive lock with timeout
        다른 프로세스가 실행중이면 대기
        """
        start_time = time.time()

        while True:
            try:
                # Open lock file
                if sys.platform == 'win32':
                    # Windows: Open file for exclusive access
                    self.lock_fd = open(self.lock_file, 'w')
                    msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    # Unix: Use fcntl
                    self.lock_fd = open(self.lock_file, 'w')
                    fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

                # Successfully acquired lock
                self._write_lock_info()
                return True

            except (IOError, OSError) as e:
                # Lock is held by another process
                if self.lock_fd is not None:
                    try:
                        self.lock_fd.close()
                    except:
                        pass
                    self.lock_fd = None

                # Check timeout
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    print(f"[QUEUE] Timeout after {timeout}s waiting for lock")
                    return False

                # Wait and retry
                if int(elapsed) % 10 == 0 and int(elapsed) > 0:
                    print(f"[QUEUE] Waiting for lock... ({int(elapsed)}s)")

                time.sleep(1)

            except Exception as e:
                print(f"[QUEUE] Error acquiring lock: {e}")
                if self.lock_fd is not None:
                    try:
                        self.lock_fd.close()
                    except:
                        pass
                    self.lock_fd = None
                return False

    def release_lock(self):
        """Release the lock"""
        if self.lock_fd is not None:
            try:
                if sys.platform == 'win32':
                    msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_UN)

                self.lock_fd.close()
                self.lock_fd = None

                # Clean up lock file
                if self.lock_file.exists():
                    try:
                        os.remove(self.lock_file)
                    except:
                        pass

            except Exception as e:
                print(f"[QUEUE] Error releasing lock: {e}")

    def _write_lock_info(self):
        """Write lock information to file"""
        try:
            info = {
                "pid": os.getpid(),
                "timestamp": datetime.now().isoformat(),
            }
            self.lock_fd.write(json.dumps(info))
            self.lock_fd.flush()
        except:
            pass

    def add_to_queue(self, task_id: str, task_data: Dict):
        """Add task to queue"""
        try:
            queue = self._load_queue()
            queue[task_id] = {
                "data": task_data,
                "status": "pending",
                "created_at": datetime.now().isoformat(),
            }
            self._save_queue(queue)
        except Exception as e:
            print(f"[QUEUE] Error adding to queue: {e}")

    def update_task_status(self, task_id: str, status: str):
        """Update task status"""
        try:
            queue = self._load_queue()
            if task_id in queue:
                queue[task_id]["status"] = status
                queue[task_id]["updated_at"] = datetime.now().isoformat()
                self._save_queue(queue)
        except Exception as e:
            print(f"[QUEUE] Error updating task: {e}")

    def remove_from_queue(self, task_id: str):
        """Remove task from queue"""
        try:
            queue = self._load_queue()
            if task_id in queue:
                del queue[task_id]
                self._save_queue(queue)
        except Exception as e:
            print(f"[QUEUE] Error removing from queue: {e}")

    def _load_queue(self) -> Dict:
        """Load queue from file"""
        if self.queue_file.exists():
            try:
                with open(self.queue_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_queue(self, queue: Dict):
        """Save queue to file"""
        with open(self.queue_file, 'w') as f:
            json.dump(queue, f, indent=2)

    def __enter__(self):
        """Context manager entry"""
        if self.acquire_lock():
            return self
        else:
            raise Exception("Could not acquire queue lock")

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.release_lock()
