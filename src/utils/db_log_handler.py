"""
Database logging handler for Python logging module.
Saves logs to contents_logs table in SQLite database.
(v3: job_logs → contents_logs 통합)
"""
import logging
import sqlite3
from datetime import datetime
import os
from pathlib import Path


class DatabaseLogHandler(logging.Handler):
    """
    Custom logging handler that saves logs to SQLite database.
    """

    def __init__(self, db_path: str, job_id: str):
        """
        Initialize the database log handler.

        Args:
            db_path: Path to SQLite database file
            job_id: Job ID to associate logs with
        """
        super().__init__()
        self.db_path = db_path
        self.job_id = job_id
        self.connection = None
        self.cursor = None

        # DB 연결 초기화
        self._init_connection()

    def _init_connection(self):
        """Initialize database connection."""
        try:
            self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self.cursor = self.connection.cursor()

            # contents_logs 테이블이 없으면 생성 (v3: job_logs → contents_logs 통합)
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS contents_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_id TEXT NOT NULL,
                    log_message TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            ''')
            self.connection.commit()
        except Exception as e:
            print(f"Failed to initialize DB connection: {e}")

    def emit(self, record):
        """
        Emit a log record to the database.

        Args:
            record: LogRecord instance
        """
        try:
            # 로그 메시지 포맷팅
            log_message = self.format(record)

            # DB에 저장 (v3: job_logs → contents_logs)
            if self.connection and self.cursor:
                self.cursor.execute(
                    'INSERT INTO contents_logs (content_id, log_message) VALUES (?, ?)',
                    (self.job_id, log_message)
                )
                self.connection.commit()
        except Exception as e:
            # 로그 저장 실패는 조용히 처리 (로그 무한 루프 방지)
            print(f"Failed to save log to database: {e}")

    def close(self):
        """Close database connection."""
        try:
            if self.connection:
                self.connection.close()
        except Exception as e:
            print(f"Failed to close DB connection: {e}")

        super().close()


def setup_db_logging(job_id: str, logger_name: str = None, level=logging.INFO) -> logging.Logger:
    """
    Setup database logging for a job.

    Args:
        job_id: Job ID to associate logs with
        logger_name: Name of the logger (default: root logger)
        level: Logging level

    Returns:
        Logger instance with DB handler attached
    """
    # DB 경로 찾기 (프로젝트 루트에서 2단계 위)
    backend_root = Path(__file__).parent.parent.parent
    frontend_root = backend_root.parent / 'trend-video-frontend'
    db_path = frontend_root / 'data' / 'database.sqlite'

    if not db_path.exists():
        print(f"Warning: Database not found at {db_path}")
        db_path = backend_root.parent / 'data' / 'database.sqlite'

    # Logger 가져오기
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)

    # 기존 DB 핸들러 제거 (중복 방지)
    for handler in logger.handlers[:]:
        if isinstance(handler, DatabaseLogHandler):
            handler.close()
            logger.removeHandler(handler)

    # DB 핸들러 추가
    db_handler = DatabaseLogHandler(str(db_path), job_id)
    db_handler.setLevel(level)

    # 포맷터 설정 (타임스탬프, 레벨, 메시지)
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    db_handler.setFormatter(formatter)

    logger.addHandler(db_handler)

    return logger


# 편의 함수: job_id를 환경변수에서 가져와서 자동 설정
def auto_setup_db_logging(logger_name: str = None, level=logging.INFO) -> logging.Logger:
    """
    Automatically setup DB logging using JOB_ID from environment.

    Args:
        logger_name: Name of the logger (default: root logger)
        level: Logging level

    Returns:
        Logger instance with DB handler attached
    """
    job_id = os.environ.get('JOB_ID')
    if not job_id:
        print("Warning: JOB_ID environment variable not set. DB logging disabled.")
        return logging.getLogger(logger_name)

    return setup_db_logging(job_id, logger_name, level)
