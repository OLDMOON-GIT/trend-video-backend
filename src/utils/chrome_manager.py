"""
Chrome 자동화 프로필 관리자

모든 자동화 작업(이미지 크롤링, 스크립트 생성 등)에서 동일한 Chrome 프로필과
디버깅 모드를 사용하도록 통일.
"""

import subprocess
import os
import socket
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


class ChromeManager:
    """Chrome 자동화 프로필 관리자"""

    DEBUG_PORT = 9222

    @staticmethod
    def get_profile_path():
        """프로젝트 루트의 .chrome-automation-profile 경로 반환"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # src/utils → src → trend-video-backend (프로젝트 루트)
        project_root = os.path.dirname(os.path.dirname(script_dir))
        profile_path = os.path.join(project_root, '.chrome-automation-profile')

        # 프로필 폴더가 없으면 생성
        if not os.path.exists(profile_path):
            os.makedirs(profile_path)
            print(f"✅ Created Chrome profile: {profile_path}")

        return profile_path

    @staticmethod
    def is_chrome_running():
        """Chrome 디버깅 포트 활성화 여부 확인"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', ChromeManager.DEBUG_PORT))
        sock.close()
        return result == 0

    @staticmethod
    def launch_chrome_debug():
        """Chrome을 디버깅 모드로 실행"""
        if ChromeManager.is_chrome_running():
            print(f"✅ Chrome already running in debug mode (port {ChromeManager.DEBUG_PORT})")
            return

        # Chrome 실행 파일 경로
        chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        if not os.path.exists(chrome_exe):
            chrome_exe = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        if not os.path.exists(chrome_exe):
            raise FileNotFoundError("Chrome executable not found")

        profile_dir = ChromeManager.get_profile_path()

        # Chrome 실행 (디버깅 모드)
        subprocess.Popen(
            [
                chrome_exe,
                f"--remote-debugging-port={ChromeManager.DEBUG_PORT}",
                f"--user-data-dir={profile_dir}"
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        # Chrome 시작 대기
        max_wait = 10
        for i in range(max_wait):
            if ChromeManager.is_chrome_running():
                print(f"🚀 Chrome launched in debug mode (port {ChromeManager.DEBUG_PORT})")
                time.sleep(1)  # 추가 안정화 대기
                return
            time.sleep(1)

        raise TimeoutError(f"Chrome failed to start after {max_wait} seconds")

    @staticmethod
    def connect_to_chrome():
        """실행 중인 Chrome에 Selenium 연결"""
        # ⭐ BTS-0000057: 재시도 로직 추가
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                # Chrome 디버깅 모드 실행 (이미 실행 중이면 스킵)
                ChromeManager.launch_chrome_debug()

                # Selenium 옵션 설정
                service = Service(ChromeDriverManager().install())
                chrome_options = Options()
                chrome_options.add_experimental_option(
                    "debuggerAddress",
                    f"127.0.0.1:{ChromeManager.DEBUG_PORT}"
                )

                # Chrome 연결
                print(f"[ChromeManager] Attempting to connect (attempt {attempt + 1}/{max_retries})...")
                driver = webdriver.Chrome(service=service, options=chrome_options)

                # WebDriver 감지 우회
                driver.execute_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )

                print("✅ Connected to Chrome (automation profile)")
                return driver

            except Exception as e:
                error_msg = str(e)
                print(f"⚠️ [ChromeManager] Connection attempt {attempt + 1} failed: {error_msg}")

                if attempt < max_retries - 1:
                    print(f"[ChromeManager] Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)

                    # Chrome 포트가 응답하지 않으면 프로세스 재시작 시도
                    if "cannot connect to chrome" in error_msg.lower() or "unable to discover open pages" in error_msg.lower():
                        print("[ChromeManager] Attempting to restart Chrome...")
                        # 1. 기존 Chrome 종료
                        ChromeManager.close_chrome()
                        # 2. 포트 강제 해제
                        ChromeManager.kill_chrome_on_port()
                        # 3. 프로필 잠금 파일 정리
                        ChromeManager.clear_profile_locks()
                        time.sleep(1)
                else:
                    # 마지막 시도 실패
                    raise Exception(
                        f"Failed to connect to Chrome after {max_retries} attempts. "
                        f"Last error: {error_msg}\n\n"
                        f"💡 해결 방법:\n"
                        f"1. Chrome이 실행 중인지 확인\n"
                        f"2. az.bat → [2] Chrome 자동화 시작\n"
                        f"3. 또는 수동으로 실행:\n"
                        f'   "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
                        f'--remote-debugging-port=9222 '
                        f'--user-data-dir={ChromeManager.get_profile_path()}'
                    )

    @staticmethod
    def close_chrome():
        """Chrome 프로세스 종료 (필요시)"""
        import psutil

        terminated = False
        for proc in psutil.process_iter(['name', 'cmdline']):
            try:
                if proc.info['name'] == 'chrome.exe':
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if f'--remote-debugging-port={ChromeManager.DEBUG_PORT}' in cmdline:
                        proc.terminate()
                        terminated = True
                        print("🛑 Chrome debug process terminated")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if terminated:
            time.sleep(2)  # 프로세스 종료 대기

    @staticmethod
    def kill_chrome_on_port():
        """9222 포트를 사용 중인 모든 Chrome 프로세스 강제 종료"""
        import psutil

        killed = False
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                if proc.info['name'] and 'chrome' in proc.info['name'].lower():
                    for conn in proc.net_connections(kind='inet'):
                        if conn.laddr and conn.laddr.port == ChromeManager.DEBUG_PORT:
                            print(f"[ChromeManager] Killing Chrome (PID: {proc.pid}) on port {ChromeManager.DEBUG_PORT}")
                            proc.kill()
                            killed = True
                            break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        if killed:
            time.sleep(2)
            print("[ChromeManager] ✅ Chrome processes killed")

        return killed

    @staticmethod
    def clear_profile_locks():
        """Chrome 프로필 잠금 파일 정리"""
        profile_path = ChromeManager.get_profile_path()
        lock_files = ['SingletonLock', 'SingletonSocket', 'SingletonCookie']

        for lock_file in lock_files:
            lock_path = os.path.join(profile_path, lock_file)
            if os.path.exists(lock_path):
                try:
                    os.remove(lock_path)
                    print(f"[ChromeManager] Removed lock file: {lock_file}")
                except Exception as e:
                    print(f"[ChromeManager] Failed to remove {lock_file}: {e}")
