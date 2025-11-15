"""
이미지 크롤링 자동화 스크립트
Whisk에 자동으로 프롬프트를 입력합니다.
"""

import sys
import time
import json
import pyperclip
import io

# Windows 인코딩 문제 해결
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

def setup_chrome_driver():
    """Chrome 드라이버 설정 - 실행 중인 Chrome에 연결"""
    import os
    import subprocess
    import requests

    service = Service(ChromeDriverManager().install())

    # 1단계: 실행 중인 Chrome의 디버깅 포트에 연결 시도
    print("🔍 실행 중인 Chrome 찾는 중...")

    try:
        # Chrome이 9222 포트에서 실행 중인지 확인
        response = requests.get("http://127.0.0.1:9222/json/version", timeout=2)
        if response.status_code == 200:
            print("✅ 실행 중인 Chrome 발견! (디버깅 포트 활성화)")

            chrome_options = Options()
            chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

            driver = webdriver.Chrome(service=service, options=chrome_options)
            print("✅ 기존 Chrome에 연결 완료 (로그인 세션 유지)")

            # 자동화 감지 우회
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver

    except (requests.exceptions.RequestException, Exception):
        pass

    # 2단계: Chrome이 디버깅 모드로 실행되지 않음 → 자동으로 시작
    print("⚠️ Chrome이 디버깅 모드로 실행되지 않았습니다.")
    print("🚀 Chrome을 디버깅 모드로 자동 실행합니다...")

    # Chrome 실행 경로 찾기
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe")
    ]

    chrome_exe = None
    for path in chrome_paths:
        if os.path.exists(path):
            chrome_exe = path
            break

    if not chrome_exe:
        raise Exception("❌ Chrome 실행 파일을 찾을 수 없습니다.")

    # 별도 프로필 디렉토리 사용 (충돌 방지)
    import tempfile
    profile_dir = os.path.join(tempfile.gettempdir(), 'chrome_debug_profile')

    # Chrome을 디버깅 모드로 실행
    subprocess.Popen([
        chrome_exe,
        "--remote-debugging-port=9222",
        f"--user-data-dir={profile_dir}"
    ])

    print("⏳ Chrome 시작 대기 중...")
    time.sleep(8)  # Chrome이 완전히 시작될 때까지 대기

    # Chrome이 실제로 9222 포트에서 응답할 때까지 재시도
    max_retries = 10
    for i in range(max_retries):
        try:
            response = requests.get("http://127.0.0.1:9222/json/version", timeout=1)
            if response.status_code == 200:
                print(f"✅ Chrome 디버깅 포트 응답 확인!")
                break
        except:
            pass

        if i < max_retries - 1:
            print(f"⏳ 재시도 {i+1}/{max_retries}...")
            time.sleep(2)
        else:
            raise Exception("❌ Chrome 디버깅 포트 연결 실패")

    # 다시 연결 시도
    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

    driver = webdriver.Chrome(service=service, options=chrome_options)
    print("✅ Chrome 연결 완료!")

    # 자동화 감지 우회
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    return driver

def input_prompt_to_whisk(driver, prompt, wait_time=WebDriverWait, is_first=False):
    """Whisk 입력창에 프롬프트 입력 (클립보드 + Ctrl+V 방식)"""
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.common.action_chains import ActionChains

    try:
        # 클립보드에 프롬프트 복사
        pyperclip.copy(prompt)
        print(f"📋 클립보드에 복사: {prompt[:50]}...")
        time.sleep(0.3)

        # 입력창 찾기 및 클릭
        wait = WebDriverWait(driver, 10)
        input_box = None

        # 여러 선택자 시도
        selectors = [
            'textarea',
            '[contenteditable="true"]',
            'div[role="textbox"]',
            'input[type="text"]'
        ]

        for selector in selectors:
            try:
                input_box = wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                print(f"✅ 입력창 발견: {selector}")
                break
            except:
                continue

        if not input_box:
            # 입력창을 못 찾으면 body를 클릭
            print("⚠️ 입력창을 찾지 못함, 페이지 클릭 시도")
            body = driver.find_element(By.TAG_NAME, 'body')
            body.click()
        else:
            # 입력창 클릭
            input_box.click()
            time.sleep(0.3)

        # Ctrl+A로 전체 선택
        actions = ActionChains(driver)
        actions.key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).perform()
        print(f"✅ Ctrl+A 전체 선택 완료")
        time.sleep(0.3)

        # Ctrl+V로 붙여넣기
        actions = ActionChains(driver)
        actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
        print(f"✅ Ctrl+V 붙여넣기 완료")
        time.sleep(0.5)

        # 엔터 키 입력
        actions = ActionChains(driver)
        actions.send_keys(Keys.RETURN).perform()
        print("⏎ 엔터 입력 완료")

        return True

    except Exception as e:
        print(f"❌ 입력 오류: {e}")
        print(f"📋 클립보드에 이미 복사됨, 수동으로 Ctrl+V 하세요")
        return False

def main(scenes_json_file):
    """메인 실행 함수"""
    print("=" * 80)
    print("🚀 이미지 크롤링 자동화 시작")
    print("=" * 80)

    # JSON 파일 읽기
    try:
        with open(scenes_json_file, 'r', encoding='utf-8') as f:
            scenes = json.load(f)
    except Exception as e:
        print(f"❌ JSON 파일 읽기 실패: {e}")
        return 1

    if not scenes or len(scenes) == 0:
        print("❌ 씬 데이터가 없습니다.")
        return 1

    print(f"📝 총 {len(scenes)}개 씬 처리 예정\n")

    driver = None
    try:
        driver = setup_chrome_driver()

        # Whisk 한 탭에서 모든 씬 처리
        print(f"\n{'='*80}")
        print(f"📌 Whisk 시작 - 한 탭에서 모든 프롬프트 처리")
        print(f"{'='*80}")
        driver.get('https://labs.google/fx/ko/tools/whisk/project')
        time.sleep(3)

        # 모든 씬을 순차적으로 처리
        for i in range(len(scenes)):
            scene = scenes[i]
            scene_number = scene.get('scene_number') or scene.get('scene_id') or f"scene_{str(i).zfill(2)}"
            prompt = scene.get('image_prompt') or scene.get('sora_prompt') or ''

            if not prompt:
                print(f"⏭️ {scene_number} - 프롬프트 없음, 건너뜀")
                continue

            # 타이밍 제어
            if i >= 3:  # scene_03부터
                delay = 15
                print(f"\n⏳ {scene_number} - {delay}초 대기 중...")
                time.sleep(delay)
            elif i == 2:  # scene_02는 짧은 대기
                delay = 2
                print(f"\n⏳ {scene_number} - {delay}초 대기 중...")
                time.sleep(delay)
            elif i == 1:  # scene_01은 약간의 대기
                time.sleep(0.5)
            # scene_00은 즉시 실행

            print(f"\n{'-'*80}")
            print(f"📌 {scene_number} 입력 중...")
            print(f"{'-'*80}")

            # 프롬프트 입력
            success = input_prompt_to_whisk(driver, prompt, is_first=(i == 0))

            if success:
                # 다음 입력 전 대기
                time.sleep(2)
            else:
                print(f"⚠️ {scene_number} 입력 실패, 계속 진행...")
                continue

        print(f"\n{'='*80}")
        print("✅ 모든 씬 처리 완료!")
        print(f"{'='*80}")

        # 브라우저는 사용자가 직접 닫도록 유지
        input("\n엔터를 누르면 브라우저가 종료됩니다...")

        return 0

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        if driver:
            driver.quit()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("사용법: python image_crawler.py <scenes.json>")
        sys.exit(1)

    scenes_file = sys.argv[1]
    sys.exit(main(scenes_file))
