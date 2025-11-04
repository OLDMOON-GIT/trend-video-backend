"""
프로세스 제어 유틸리티

Frontend에서 전송한 STOP 신호를 감지하고 자식 프로세스를 정리합니다.
"""

import os
import sys
import signal
from pathlib import Path
from typing import Optional

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("⚠️ psutil not available. Process cleanup will be limited.")


class ProcessController:
    """프로세스 제어 클래스"""

    def __init__(self, output_dir: Path):
        """
        Args:
            output_dir: 작업 디렉토리 (STOP 파일이 생성될 위치)
        """
        self.output_dir = Path(output_dir)
        self.stop_file = self.output_dir / 'STOP'
        self.should_stop = False

        # Signal handler 등록
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        print(f"📍 프로세스 컨트롤러 초기화: {self.output_dir}")
        print(f"📍 STOP 파일 경로: {self.stop_file}")

    def _signal_handler(self, signum, frame):
        """시그널 핸들러"""
        print(f"\n🛑 시그널 받음: {signum}")
        self.should_stop = True
        self.cleanup_and_exit()

    def check_stop_signal(self) -> bool:
        """STOP 파일 존재 여부 확인"""
        if self.should_stop:
            return True

        if self.stop_file.exists():
            print(f"🛑 STOP 신호 파일 감지: {self.stop_file}")
            self.should_stop = True
            return True

        return False

    def cleanup_and_exit(self, exit_code: int = 0):
        """자식 프로세스 정리 후 종료"""
        print("🧹 자식 프로세스 정리 시작...")

        if PSUTIL_AVAILABLE:
            try:
                current_process = psutil.Process(os.getpid())
                children = current_process.children(recursive=True)

                if children:
                    print(f"   찾은 자식 프로세스: {len(children)}개")

                    # 1단계: SIGTERM으로 정상 종료 요청
                    for child in children:
                        try:
                            print(f"   프로세스 종료 요청: PID {child.pid} ({child.name()})")
                            child.terminate()
                        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                            print(f"   ⚠️ 프로세스 종료 실패: {e}")

                    # 2초 대기
                    gone, alive = psutil.wait_procs(children, timeout=2)

                    # 2단계: 남아있는 프로세스 강제 종료
                    for child in alive:
                        try:
                            print(f"   프로세스 강제 종료: PID {child.pid} ({child.name()})")
                            child.kill()
                        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                            print(f"   ⚠️ 프로세스 강제 종료 실패: {e}")

                    print(f"✅ 자식 프로세스 정리 완료: {len(gone)} 종료, {len(alive)} 강제 종료")
                else:
                    print("   자식 프로세스 없음")

            except Exception as e:
                print(f"⚠️ 프로세스 정리 중 오류: {e}")
        else:
            print("⚠️ psutil 없음. 자식 프로세스 정리 건너뜀")

        # STOP 파일 삭제
        try:
            if self.stop_file.exists():
                self.stop_file.unlink()
                print(f"🗑️ STOP 파일 삭제: {self.stop_file}")
        except Exception as e:
            print(f"⚠️ STOP 파일 삭제 실패: {e}")

        print(f"👋 프로세스 종료 (코드: {exit_code})")
        sys.exit(exit_code)


def should_stop(output_dir: Path) -> bool:
    """
    간단한 STOP 신호 체크 함수 (클래스 없이 사용)

    Args:
        output_dir: 작업 디렉토리

    Returns:
        bool: STOP 신호 존재 여부
    """
    stop_file = Path(output_dir) / 'STOP'
    return stop_file.exists()
