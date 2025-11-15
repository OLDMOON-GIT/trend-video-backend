"""
Image-FX DOM 구조 덤프
"""
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

def dump_imagefx_dom():
    """Image-FX 페이지의 DOM 구조 덤프"""
    import os
    import subprocess
    import requests

    service = Service(ChromeDriverManager().install())

    # Chrome 디버깅 포트 확인
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

    # 디버깅 포트로 연결
    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        # Image-FX 페이지로 이동
        print("Image-FX 페이지 접속 중...")
        driver.get('https://labs.google/fx/tools/image-fx')
        time.sleep(10)

        # DOM 정보 수집
        result = driver.execute_script("""
            const info = {};

            // 1. 모든 contenteditable 요소
            const editables = [];
            document.querySelectorAll('*').forEach(elem => {
                if (elem.isContentEditable) {
                    editables.push({
                        tag: elem.tagName,
                        classes: elem.className,
                        id: elem.id,
                        contentEditable: elem.contentEditable,
                        text: elem.textContent.substring(0, 50),
                        outerHTML: elem.outerHTML.substring(0, 200)
                    });
                }
            });
            info.editables = editables;

            // 2. textarea 요소
            const textareas = [];
            document.querySelectorAll('textarea').forEach(elem => {
                textareas.push({
                    tag: elem.tagName,
                    classes: elem.className,
                    id: elem.id,
                    outerHTML: elem.outerHTML.substring(0, 200)
                });
            });
            info.textareas = textareas;

            // 3. sc-로 시작하는 클래스 (styled-components)
            const scElements = [];
            document.querySelectorAll('[class*="sc-"]').forEach(elem => {
                if (elem.offsetHeight > 20) {  // 보이는 요소만
                    scElements.push({
                        tag: elem.tagName,
                        classes: elem.className,
                        id: elem.id,
                        isContentEditable: elem.isContentEditable,
                        text: elem.textContent.substring(0, 50),
                        outerHTML: elem.outerHTML.substring(0, 300)
                    });
                }
            });
            info.scElements = scElements.slice(0, 10);  // 처음 10개만

            // 4. input 요소
            const inputs = [];
            document.querySelectorAll('input').forEach(elem => {
                inputs.push({
                    tag: elem.tagName,
                    type: elem.type,
                    classes: elem.className,
                    id: elem.id,
                    outerHTML: elem.outerHTML.substring(0, 200)
                });
            });
            info.inputs = inputs;

            // 5. iframe
            info.iframeCount = document.querySelectorAll('iframe').length;

            return info;
        """)

        print("\n" + "="*80)
        print("DOM Analysis Result")
        print("="*80)

        print(f"\n[ContentEditable Elements]: {len(result['editables'])}")
        for i, elem in enumerate(result['editables']):
            print(f"\n[{i+1}]")
            print(f"  Tag: {elem['tag']}")
            print(f"  Classes: {elem['classes']}")
            print(f"  ID: {elem['id']}")
            print(f"  Text: {elem['text']}")
            print(f"  HTML: {elem['outerHTML']}")

        print(f"\n[Textarea Elements]: {len(result['textareas'])}")
        for i, elem in enumerate(result['textareas']):
            print(f"\n[{i+1}]")
            print(f"  Classes: {elem['classes']}")
            print(f"  ID: {elem['id']}")
            print(f"  HTML: {elem['outerHTML']}")

        print(f"\n[SC- Class Elements (first 10)]: {len(result['scElements'])}")
        for i, elem in enumerate(result['scElements']):
            print(f"\n[{i+1}]")
            print(f"  Tag: {elem['tag']}")
            print(f"  Classes: {elem['classes']}")
            print(f"  ContentEditable: {elem['isContentEditable']}")
            print(f"  Text: {elem['text']}")
            print(f"  HTML: {elem['outerHTML']}")

        print(f"\n[Input Elements]: {len(result['inputs'])}")
        for i, elem in enumerate(result['inputs']):
            print(f"\n[{i+1}]")
            print(f"  Type: {elem['type']}")
            print(f"  Classes: {elem['classes']}")
            print(f"  ID: {elem['id']}")
            print(f"  HTML: {elem['outerHTML']}")

        print(f"\n[Iframes]: {result['iframeCount']}")

        print("\n" + "="*80)

    finally:
        # driver는 종료하지 않음
        pass

if __name__ == '__main__':
    dump_imagefx_dom()
