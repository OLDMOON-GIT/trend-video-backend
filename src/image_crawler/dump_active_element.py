"""
Image-FX 활성 요소(입력창) 덤프
사용법: 이 스크립트를 실행한 후 Image-FX 입력창을 클릭하세요.
10초 후 자동으로 활성 요소 정보를 출력합니다.
"""
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

def dump_active_element():
    """활성 요소 덤프"""
    import os
    import subprocess
    import requests

    service = Service(ChromeDriverManager().install())

    # Chrome 디버깅 포트 연결
    try:
        response = requests.get("http://127.0.0.1:9222/json/version", timeout=2)
        print("[OK] Chrome debugging port active")
    except:
        print("[INFO] Starting Chrome in debug mode...")
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
        # Image-FX 페이지로 이동
        print("Navigating to Image-FX page...")
        driver.get('https://labs.google/fx/tools/image-fx')
        time.sleep(10)

        print("\n" + "="*80)
        print("IMPORTANT: Click on the Image-FX input field NOW!")
        print("Waiting 10 seconds for you to click the input...")
        print("="*80 + "\n")

        # 10초 카운트다운
        for i in range(10, 0, -1):
            print(f"  {i}...")
            time.sleep(1)

        print("\nCapturing active element...")

        # 활성 요소 정보 수집
        result = driver.execute_script("""
            const info = {};
            const elem = document.activeElement;

            if (elem) {
                info.tag = elem.tagName;
                info.id = elem.id;
                info.className = elem.className;
                info.contentEditable = elem.contentEditable;
                info.isContentEditable = elem.isContentEditable;
                info.type = elem.type || 'N/A';
                info.outerHTML = elem.outerHTML.substring(0, 500);
                info.textContent = elem.textContent.substring(0, 100);

                // 속성들
                info.attributes = {};
                for (let attr of elem.attributes) {
                    info.attributes[attr.name] = attr.value;
                }

                // 부모 요소
                if (elem.parentElement) {
                    info.parent = {
                        tag: elem.parentElement.tagName,
                        className: elem.parentElement.className,
                        outerHTML: elem.parentElement.outerHTML.substring(0, 300)
                    };
                }

                // CSS 선택자 생성
                let path = [];
                let current = elem;
                while (current && current.tagName) {
                    let selector = current.tagName.toLowerCase();
                    if (current.id) {
                        selector += '#' + current.id;
                        path.unshift(selector);
                        break;
                    } else if (current.className) {
                        selector += '.' + current.className.split(' ').join('.');
                    }
                    path.unshift(selector);
                    current = current.parentElement;
                }
                info.cssPath = path.join(' > ');
            }

            return info;
        """)

        print("\n" + "="*80)
        print("ACTIVE ELEMENT INFORMATION")
        print("="*80)

        if result:
            print(f"\nTag: {result['tag']}")
            print(f"ID: {result['id']}")
            print(f"Class: {result['className']}")
            print(f"ContentEditable: {result['contentEditable']}")
            print(f"IsContentEditable: {result['isContentEditable']}")
            print(f"Type: {result['type']}")
            print(f"Text: {result['textContent']}")
            print(f"\nHTML (first 500 chars):")
            print(result['outerHTML'])

            print(f"\nAll Attributes:")
            for key, value in result['attributes'].items():
                print(f"  {key} = {value}")

            if 'parent' in result:
                print(f"\nParent Element:")
                print(f"  Tag: {result['parent']['tag']}")
                print(f"  Class: {result['parent']['className']}")
                print(f"  HTML: {result['parent']['outerHTML']}")

            print(f"\nCSS Selector Path:")
            print(f"  {result['cssPath']}")

            print("\n" + "="*80)
            print("RECOMMENDED SELECTOR:")
            # 가장 간단한 선택자 추천
            if result['id']:
                print(f"  By ID: #{result['id']}")
            elif result['className']:
                first_class = result['className'].split()[0]
                print(f"  By Class: .{first_class}")
            print("="*80)

        else:
            print("\nNo active element found!")

    finally:
        # driver 유지
        pass

if __name__ == '__main__':
    dump_active_element()
