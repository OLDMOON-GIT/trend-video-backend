"""
Image-FX 디버깅: 스크린샷 + 더 긴 대기 + 스크롤
"""
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

def debug_imagefx():
    import os
    import subprocess
    import requests

    service = Service(ChromeDriverManager().install())

    # Chrome 연결
    try:
        response = requests.get("http://127.0.0.1:9222/json/version", timeout=2)
        print("[OK] Chrome connected")
    except:
        print("[INFO] Starting Chrome...")
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        chrome_exe = None
        for path in chrome_paths:
            if os.path.exists(path):
                chrome_exe = path
                break
        if chrome_exe:
            import tempfile
            profile_dir = os.path.join(tempfile.gettempdir(), 'chrome_debug_profile')
            subprocess.Popen([chrome_exe, "--remote-debugging-port=9222", f"--user-data-dir={profile_dir}"])
            time.sleep(8)

    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        # 1. 페이지 열기
        print("\n[1] Opening Image-FX...")
        driver.get('https://labs.google/fx/tools/image-fx')

        # 2. 초기 로딩 대기
        print("[2] Waiting 20 seconds for page load...")
        time.sleep(20)

        # 3. 스크린샷 1
        screenshot_path = os.path.join(os.path.dirname(__file__), 'imagefx_screenshot1.png')
        driver.save_screenshot(screenshot_path)
        print(f"[3] Screenshot saved: {screenshot_path}")

        # 4. 페이지 스크롤 (입력창이 아래에 있을 수 있음)
        print("[4] Scrolling page...")
        driver.execute_script("window.scrollTo(0, 500);")
        time.sleep(2)

        # 5. 스크린샷 2
        screenshot_path2 = os.path.join(os.path.dirname(__file__), 'imagefx_screenshot2.png')
        driver.save_screenshot(screenshot_path2)
        print(f"[5] Screenshot after scroll: {screenshot_path2}")

        # 6. 모든 텍스트 내용이 있는 div 찾기
        print("\n[6] Finding ALL divs with text content...")
        result = driver.execute_script("""
            const divs = Array.from(document.querySelectorAll('div'));
            const candidates = [];

            for (let div of divs) {
                // 텍스트가 있고, 크기가 적당한 것만
                const text = div.textContent.trim();
                if (text.length > 0 && text.length < 500 &&
                    div.offsetHeight > 20 && div.offsetHeight < 300 &&
                    div.offsetWidth > 100) {

                    candidates.push({
                        tag: div.tagName,
                        className: div.className,
                        id: div.id,
                        text: text.substring(0, 100),
                        contentEditable: div.contentEditable,
                        isContentEditable: div.isContentEditable,
                        offsetHeight: div.offsetHeight,
                        offsetWidth: div.offsetWidth
                    });
                }
            }

            // 처음 20개만 반환
            return candidates.slice(0, 20);
        """)

        print(f"\n[7] Found {len(result)} candidate divs:")
        for i, elem in enumerate(result):
            print(f"\n  [{i+1}]")
            print(f"    Class: {elem['className'][:80]}")
            print(f"    ContentEditable: {elem['contentEditable']}")
            print(f"    Size: {elem['offsetWidth']}x{elem['offsetHeight']}")
            print(f"    Text: {elem['text'][:60]}")

        # 8. "prompt", "input", "text" 등의 키워드가 있는 div 찾기
        print("\n[8] Searching for prompt/input related elements...")
        prompt_elements = driver.execute_script("""
            const keywords = ['prompt', 'input', 'text', 'generate', 'create'];
            const matches = [];

            const allElements = document.querySelectorAll('*');
            for (let elem of allElements) {
                const className = elem.className.toLowerCase();
                const id = elem.id.toLowerCase();
                const placeholder = (elem.placeholder || '').toLowerCase();

                for (let keyword of keywords) {
                    if (className.includes(keyword) || id.includes(keyword) || placeholder.includes(keyword)) {
                        if (elem.offsetHeight > 20) {
                            matches.push({
                                tag: elem.tagName,
                                className: elem.className.substring(0, 80),
                                id: elem.id,
                                placeholder: elem.placeholder || '',
                                type: elem.type || '',
                                contentEditable: elem.contentEditable
                            });
                            break;
                        }
                    }
                }
            }

            return matches.slice(0, 10);
        """)

        print(f"\n[9] Found {len(prompt_elements)} elements with keywords:")
        for i, elem in enumerate(prompt_elements):
            print(f"\n  [{i+1}]")
            print(f"    Tag: {elem['tag']}")
            print(f"    Class: {elem['className']}")
            print(f"    ID: {elem['id']}")
            print(f"    Placeholder: {elem['placeholder']}")
            print(f"    ContentEditable: {elem['contentEditable']}")

        print("\n[10] Debug complete!")
        print(f"Check screenshots:")
        print(f"  - {screenshot_path}")
        print(f"  - {screenshot_path2}")

    finally:
        # driver 유지
        pass

if __name__ == '__main__':
    debug_imagefx()
