"""
이미지 크롤링 자동화 스크립트
Whisk 또는 ImageFX + Whisk 조합으로 이미지를 생성합니다.
"""

import sys
import time
import json
import pyperclip
import io
import os
import glob
import argparse

# Windows 인코딩 문제 해결
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True, write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True, write_through=True)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

def setup_chrome_driver():
    """Chrome 드라이버 설정 - 실행 중인 Chrome에 연결"""
    import subprocess
    import requests

    service = Service(ChromeDriverManager().install())

    # 1단계: 실행 중인 Chrome의 디버깅 포트에 연결 시도
    print("🔍 실행 중인 Chrome 찾는 중...", flush=True)

    try:
        # Chrome이 9222 포트에서 실행 중인지 확인
        response = requests.get("http://127.0.0.1:9222/json/version", timeout=2)
        if response.status_code == 200:
            print("✅ 실행 중인 Chrome 발견! (디버깅 포트 활성화)", flush=True)

            chrome_options = Options()
            chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

            driver = webdriver.Chrome(service=service, options=chrome_options)
            print("✅ 기존 Chrome에 연결 완료 (로그인 세션 유지)", flush=True)

            # 자동화 감지 우회
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver

    except (requests.exceptions.RequestException, Exception):
        pass

    # 2단계: Chrome이 디버깅 모드로 실행되지 않음 → 자동으로 시작
    print("⚠️ Chrome이 디버깅 모드로 실행되지 않았습니다.", flush=True)
    print("🚀 Chrome을 디버깅 모드로 자동 실행합니다...", flush=True)

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

    print("⏳ Chrome 시작 대기 중...", flush=True)
    time.sleep(8)  # Chrome이 완전히 시작될 때까지 대기

    # Chrome이 실제로 9222 포트에서 응답할 때까지 재시도
    max_retries = 10
    for i in range(max_retries):
        try:
            import requests
            response = requests.get("http://127.0.0.1:9222/json/version", timeout=1)
            if response.status_code == 200:
                print(f"✅ Chrome 디버깅 포트 응답 확인!", flush=True)
                break
        except:
            pass

        if i < max_retries - 1:
            print(f"⏳ 재시도 {i+1}/{max_retries}...", flush=True)
            time.sleep(2)
        else:
            raise Exception("❌ Chrome 디버깅 포트 연결 실패")

    # 다시 연결 시도
    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

    driver = webdriver.Chrome(service=service, options=chrome_options)
    print("✅ Chrome 연결 완료!", flush=True)

    # 자동화 감지 우회
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    return driver

def generate_image_with_imagefx(driver, prompt):
    """ImageFX로 이미지 생성 및 다운로드"""
    print("\n" + "="*80, flush=True)
    print("1️⃣ ImageFX - 첫 이미지 생성", flush=True)
    print("="*80, flush=True)
    print(f"📝 프롬프트 길이: {len(prompt)}자", flush=True)
    print(f"📝 프롬프트 내용: {prompt}", flush=True)
    print("="*80, flush=True)

    driver.get('https://labs.google/fx/tools/image-fx')
    print("⏳ ImageFX 페이지 로딩...", flush=True)

    # 페이지 로드 대기
    for i in range(30):
        if driver.execute_script("return document.readyState") == "complete":
            print(f"✅ 로드 완료 ({i+1}초)", flush=True)
            break
        time.sleep(1)
    time.sleep(5)

    # 디버그: 페이지 상태 상세 확인
    page_info = driver.execute_script("""
        const editables = Array.from(document.querySelectorAll('[contenteditable]'));
        return {
            url: window.location.href,
            title: document.title,
            bodyText: document.body.innerText.substring(0, 200),
            hasContentEditableTrue: !!document.querySelector('[contenteditable="true"]'),
            hasTextarea: !!document.querySelector('textarea'),
            editablesCount: editables.length,
            editables: editables.map(e => ({
                tag: e.tagName,
                attr: e.getAttribute('contenteditable'),
                visible: e.offsetParent !== null,
                classes: e.className
            }))
        };
    """)
    print(f"📋 ImageFX 상세 정보:", flush=True)
    print(f"   URL: {page_info['url']}", flush=True)
    print(f"   제목: {page_info['title']}", flush=True)
    print(f"   contenteditable='true': {page_info['hasContentEditableTrue']}", flush=True)
    print(f"   편집 가능 요소 수: {page_info['editablesCount']}", flush=True)
    if page_info['editablesCount'] > 0:
        print(f"   편집 가능 요소들:", flush=True)
        for idx, elem in enumerate(page_info['editables'][:3]):
            print(f"      [{idx+1}] {elem}", flush=True)

    # 스크린샷 저장
    try:
        import tempfile
        screenshot_path = os.path.join(tempfile.gettempdir(), 'imagefx_debug.png')
        driver.save_screenshot(screenshot_path)
        print(f"📸 스크린샷: {screenshot_path}", flush=True)
    except:
        pass

    # 페이지 중앙 클릭하여 입력창 활성화 시도
    print("🖱️ 페이지 클릭하여 입력창 활성화 시도...", flush=True)
    driver.execute_script("""
        // 페이지 중앙 클릭
        const width = window.innerWidth;
        const height = window.innerHeight;
        const centerX = width / 2;
        const centerY = height / 2;

        // 중앙 요소 찾아서 클릭
        const elem = document.elementFromPoint(centerX, centerY);
        if (elem) {
            elem.click();
        }
    """)
    time.sleep(2)

    # 입력창 기다리기 (더 robust한 방법)
    print("🔍 입력창 찾는 중...", flush=True)
    input_elem = None
    for i in range(30):
        # 여러 방법으로 입력창 찾기
        found = driver.execute_script("""
            // 방법 1: contenteditable="true" div 정확히 찾기
            let elem = document.querySelector('div[contenteditable="true"]');
            if (elem && elem.offsetParent !== null) {
                return {found: true, type: 'contenteditable', selector: 'div[contenteditable="true"]'};
            }

            // 방법 2: textarea 찾기
            elem = document.querySelector('textarea');
            if (elem && elem.offsetParent !== null) {
                return {found: true, type: 'textarea', selector: 'textarea'};
            }

            // 방법 3: role="textbox" 찾기
            elem = document.querySelector('[role="textbox"]');
            if (elem && elem.offsetParent !== null && elem.contentEditable === 'true') {
                return {found: true, type: 'role-textbox', selector: '[role="textbox"]'};
            }

            // 방법 4: data-placeholder가 있는 div 찾기
            elem = document.querySelector('div[data-placeholder]');
            if (elem && elem.offsetParent !== null) {
                return {found: true, type: 'data-placeholder', selector: 'div[data-placeholder]'};
            }

            // 방법 5: 클릭 가능한 큰 input-like 요소 찾기
            const divs = Array.from(document.querySelectorAll('div'));
            for (const d of divs) {
                if (d.offsetWidth > 300 && d.offsetHeight > 40 && d.offsetHeight < 200) {
                    // 입력창처럼 보이는 큰 div
                    const text = d.innerText || d.textContent || '';
                    if (text.length > 10 && text.length < 500) {
                        // 클릭해서 활성화
                        d.click();
                        return {found: true, type: 'clickable-div', selector: null, needsActivation: true};
                    }
                }
            }

            return {found: false};
        """)

        if found.get('found'):
            print(f"✅ 입력창 발견: {found.get('type')} - {found.get('selector')} ({i+1}초)", flush=True)
            input_elem = found

            # needsActivation인 경우 잠시 대기 후 다시 확인
            if found.get('needsActivation'):
                print("⏳ 입력창 활성화 대기 중...", flush=True)
                time.sleep(2)
                # 다시 contenteditable 찾기
                recheck = driver.execute_script("""
                    let elem = document.querySelector('div[contenteditable="true"]');
                    if (elem && elem.offsetParent !== null) {
                        return {found: true, type: 'contenteditable', selector: 'div[contenteditable="true"]'};
                    }
                    return {found: false};
                """)
                if recheck.get('found'):
                    input_elem = recheck
                    print(f"✅ 활성화된 입력창 발견: {recheck.get('selector')}", flush=True)
            break

        if i % 5 == 0 and i > 0:
            print(f"   대기 중... ({i}초)", flush=True)
            # 디버그: 페이지 상태 확인
            debug_info = driver.execute_script("""
                return {
                    readyState: document.readyState,
                    hasContentEditable: !!document.querySelector('[contenteditable]'),
                    hasTextarea: !!document.querySelector('textarea'),
                    bodyText: document.body.innerText.substring(0, 100)
                };
            """)
            print(f"   [디버그] {debug_info}", flush=True)
        time.sleep(1)

    if not input_elem:
        raise Exception("입력창을 찾을 수 없습니다")

    # 텍스트 입력 (Selenium send_keys 직접 사용)
    print(f"⌨️ 프롬프트 입력 중...", flush=True)
    print(f"   내용: {prompt[:50]}...", flush=True)

    input_success = False
    try:
        selector = input_elem.get('selector')
        if not selector:
            raise Exception("selector가 없습니다")

        # 입력창 정보 확인
        elem_info = driver.execute_script("""
            const selector = arguments[0];
            const elem = document.querySelector(selector);
            if (elem) {
                return {
                    tagName: elem.tagName,
                    contentEditable: elem.contentEditable,
                    type: elem.type,
                    value: elem.value,
                    textContent: (elem.textContent || '').substring(0, 100),
                    innerHTML: (elem.innerHTML || '').substring(0, 100)
                };
            }
            return null;
        """, selector)
        print(f"📋 입력창 정보: {elem_info}", flush=True)

        # JavaScript로 입력창 클릭, 기존 내용 삭제, 새 내용 입력
        result = driver.execute_script("""
            const selector = arguments[0];
            const newText = arguments[1];
            const elem = document.querySelector(selector);
            if (elem) {
                elem.scrollIntoView({behavior: 'instant', block: 'center'});
                elem.click();
                elem.focus();

                // 기존 내용 전체 선택 및 삭제
                if (elem.contentEditable === 'true') {
                    elem.innerHTML = '';
                    elem.textContent = newText;
                } else if (elem.tagName === 'TEXTAREA' || elem.tagName === 'INPUT') {
                    elem.value = newText;
                } else {
                    elem.textContent = newText;
                }

                // 이벤트 발생
                elem.dispatchEvent(new Event('input', { bubbles: true }));
                elem.dispatchEvent(new Event('change', { bubbles: true }));

                return true;
            }
            return false;
        """, selector, prompt)

        if result:
            print("✅ JavaScript로 입력 완료", flush=True)
            input_success = True
        else:
            print("⚠️ JavaScript 입력 실패, ActionChains 시도...", flush=True)
            # 대체 방법: ActionChains
            actions = ActionChains(driver)
            actions.send_keys(Keys.CONTROL, 'a')  # 입력창 내 텍스트만 선택
            actions.send_keys(Keys.DELETE)
            actions.send_keys(prompt)
            actions.perform()
            print("✅ ActionChains로 입력 완료", flush=True)
            input_success = True

        time.sleep(1)

        # 입력 확인
        verify = driver.execute_script("""
            const selector = arguments[0];
            const elem = document.querySelector(selector);
            if (elem) {
                const content = elem.textContent || elem.innerText || elem.value || '';
                return {
                    length: content.length,
                    preview: content.substring(0, 50)
                };
            }
            return {length: 0, preview: ''};
        """, input_elem.get('selector'))

        if verify.get('length') > 0:
            print(f"✅ 입력 확인: {verify.get('length')}자 - {verify.get('preview')}...", flush=True)
        else:
            print("⚠️ 입력 확인 실패 - 내용이 비어있지만 계속 진행", flush=True)

        # 입력창 옆 생성 버튼 찾아서 클릭
        print("🔍 생성 버튼 찾는 중...", flush=True)
        generate_clicked = driver.execute_script("""
            // 방법 1: 입력창 근처의 버튼 찾기
            const inputDiv = document.querySelector('div[contenteditable="true"]');
            if (inputDiv) {
                // 부모나 형제 요소에서 버튼 찾기
                let parent = inputDiv.parentElement;
                for (let i = 0; i < 5; i++) {
                    if (!parent) break;
                    const buttons = parent.querySelectorAll('button');
                    for (const btn of buttons) {
                        if (btn.offsetParent !== null && btn.offsetHeight > 20 && btn.offsetHeight < 100) {
                            console.log('Found button near input:', btn);
                            btn.click();
                            return {success: true, method: 'near-input'};
                        }
                    }
                    parent = parent.parentElement;
                }
            }

            // 방법 2: 텍스트로 버튼 찾기
            const buttonTexts = ['Generate', 'Create', '생성', 'make', 'Go', '만들기'];
            for (const text of buttonTexts) {
                const buttons = Array.from(document.querySelectorAll('button'));
                for (const btn of buttons) {
                    const btnText = (btn.innerText || btn.textContent || '').toLowerCase();
                    if (btnText.includes(text.toLowerCase())) {
                        if (btn.offsetParent !== null) {
                            console.log('Found button by text:', btn);
                            btn.click();
                            return {success: true, method: 'by-text-' + text};
                        }
                    }
                }
            }

            // 방법 3: submit 타입 버튼 찾기
            const submitBtns = document.querySelectorAll('button[type="submit"]');
            for (const btn of submitBtns) {
                if (btn.offsetParent !== null) {
                    console.log('Found submit button:', btn);
                    btn.click();
                    return {success: true, method: 'submit-button'};
                }
            }

            return {success: false};
        """)

        if generate_clicked and generate_clicked.get('success'):
            print(f"✅ 생성 버튼 클릭 완료 ({generate_clicked.get('method')})", flush=True)
        else:
            print("⚠️ 생성 버튼 못 찾음 - Enter 시도", flush=True)
            # Enter 입력
            actions = ActionChains(driver)
            actions.send_keys(Keys.RETURN)
            actions.perform()
            print("✅ Enter 입력", flush=True)

        time.sleep(2)

    except Exception as e:
        print(f"❌ 입력 실패: {e}", flush=True)
        raise Exception(f"프롬프트 입력 실패: {e}")

    time.sleep(3)

    # 이미지 생성 대기
    print("⏳ 이미지 생성 대기 중... (최대 120초)", flush=True)
    image_generated = False
    for i in range(120):
        result = driver.execute_script("""
            const imgs = Array.from(document.querySelectorAll('img'));
            const allImgs = imgs.map(img => ({
                src: (img.src || '').substring(0, 50),
                width: img.offsetWidth,
                height: img.offsetHeight
            }));
            const largeImgs = imgs.filter(img => img.offsetWidth > 200 && img.offsetHeight > 200);
            const text = document.body.innerText;
            return {
                hasLargeImage: largeImgs.length > 0,
                largeCount: largeImgs.length,
                totalCount: imgs.length,
                generating: text.includes('Generating') || text.includes('생성 중') || text.includes('Loading'),
                sampleImages: allImgs.slice(0, 3)
            };
        """)

        if result['hasLargeImage']:
            print(f"✅ 이미지 생성 완료! ({i+1}초) - 큰 이미지 {result['largeCount']}개 발견", flush=True)
            image_generated = True
            break

        if i % 15 == 0 and i > 0:
            print(f"   대기 중... ({i}초) - 큰 이미지: {result['largeCount']}개, 전체: {result['totalCount']}개, 생성 중: {result['generating']}", flush=True)
            if i == 15:
                print(f"   샘플 이미지: {result['sampleImages']}", flush=True)
                # 중간 스크린샷
                try:
                    import tempfile
                    mid_screenshot = os.path.join(tempfile.gettempdir(), f'imagefx_gen_{i}s.png')
                    driver.save_screenshot(mid_screenshot)
                    print(f"   📸 중간 스크린샷: {mid_screenshot}", flush=True)
                except:
                    pass

        time.sleep(1)

    if not image_generated:
        # 최종 스크린샷
        try:
            import tempfile
            final_screenshot = os.path.join(tempfile.gettempdir(), 'imagefx_gen_failed.png')
            driver.save_screenshot(final_screenshot)
            print(f"📸 실패 스크린샷: {final_screenshot}", flush=True)
        except:
            pass
        raise Exception("❌ 이미지 생성 실패 - 120초 내에 이미지가 생성되지 않았습니다")

    time.sleep(3)

    # 최근 다운로드 파일 찾기 (다운로드 전 스냅샷)
    download_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
    image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp')
    files_before = []
    for ext in image_extensions:
        files_before.extend(glob.glob(os.path.join(download_dir, f'*{ext}')))
        files_before.extend(glob.glob(os.path.join(download_dir, f'*{ext.upper()}')))
    files_before = [f for f in files_before if not f.endswith('.crdownload') and not f.endswith('.tmp')]

    # 다운로드 시도 (여러 방법)
    print("\n📥 이미지 다운로드 시도 중...", flush=True)
    download_success = False

    # 방법 1: 다양한 선택자로 다운로드 버튼 찾기
    try:
        btn_info = driver.execute_script("""
            // 선택자 리스트
            const selectors = [
                'button[aria-label*="Download"]',
                'button[aria-label*="다운로드"]',
                '[aria-label*="Download"]',
                '[aria-label*="download"]',
                'button[title*="Download"]',
                'button[title*="다운로드"]'
            ];

            for (const sel of selectors) {
                const btn = document.querySelector(sel);
                if (btn && btn.offsetParent !== null) {
                    btn.click();
                    return {success: true, method: 'selector', selector: sel};
                }
            }

            // 텍스트로 버튼 찾기
            const buttons = Array.from(document.querySelectorAll('button'));
            const downloadBtn = buttons.find(btn => {
                const text = btn.textContent.toLowerCase();
                return text.includes('download') || text.includes('다운로드');
            });

            if (downloadBtn && downloadBtn.offsetParent !== null) {
                downloadBtn.click();
                return {success: true, method: 'text'};
            }

            // 아이콘으로 버튼 찾기 (svg with download icon)
            const svgButtons = buttons.filter(btn => {
                const svg = btn.querySelector('svg');
                return svg && (
                    svg.innerHTML.includes('download') ||
                    btn.getAttribute('aria-label')?.includes('download') ||
                    btn.getAttribute('aria-label')?.includes('Download')
                );
            });

            if (svgButtons.length > 0 && svgButtons[0].offsetParent !== null) {
                svgButtons[0].click();
                return {success: true, method: 'svg'};
            }

            return {success: false};
        """)

        if btn_info.get('success'):
            print(f"✅ 다운로드 버튼 클릭: {btn_info.get('method')} - {btn_info.get('selector', 'N/A')}", flush=True)
            download_success = True
    except Exception as e:
        print(f"⚠️ 다운로드 버튼 클릭 실패: {e}", flush=True)

    # 방법 2: 이미지에 우클릭 → 다운로드
    if not download_success:
        try:
            print("📥 이미지 우클릭으로 다운로드 시도...", flush=True)
            img_download = driver.execute_script("""
                const imgs = Array.from(document.querySelectorAll('img'));
                const largeImgs = imgs.filter(img => img.offsetWidth > 300 && img.offsetHeight > 300);
                if (largeImgs.length > 0) {
                    // 이미지 URL 가져오기
                    const imgUrl = largeImgs[0].src;
                    if (imgUrl && imgUrl.startsWith('http')) {
                        // 이미지 다운로드 링크 생성
                        const a = document.createElement('a');
                        a.href = imgUrl;
                        a.download = 'imagefx_generated.png';
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        return {success: true, url: imgUrl};
                    }
                }
                return {success: false};
            """)

            if img_download.get('success'):
                print(f"✅ 이미지 URL 직접 다운로드: {img_download.get('url', '')[:50]}...", flush=True)
                download_success = True
        except Exception as e:
            print(f"⚠️ 이미지 직접 다운로드 실패: {e}", flush=True)

    if not download_success:
        raise Exception("❌ 다운로드 버튼을 찾을 수 없습니다 - 이미지 다운로드 실패")

    print("⏳ 다운로드 완료 대기...", flush=True)
    time.sleep(5)

    # 다운로드 후 새 파일 찾기
    files_after = []
    for ext in image_extensions:
        files_after.extend(glob.glob(os.path.join(download_dir, f'*{ext}')))
        files_after.extend(glob.glob(os.path.join(download_dir, f'*{ext.upper()}')))
    files_after = [f for f in files_after if not f.endswith('.crdownload') and not f.endswith('.tmp')]

    new_files = [f for f in files_after if f not in files_before]

    if new_files:
        latest_file = max(new_files, key=os.path.getctime)
        print(f"✅ 이미지 다운로드 확인: {os.path.basename(latest_file)}", flush=True)
        return latest_file
    else:
        raise Exception("❌ 다운로드된 이미지 파일을 찾을 수 없습니다 - Downloads 폴더에 새 파일이 없습니다")

def upload_image_to_whisk(driver, image_path):
    """Whisk에 이미지 업로드"""
    print("\n" + "="*80, flush=True)
    print("2️⃣ Whisk - 인물 이미지 업로드", flush=True)
    print("="*80, flush=True)

    driver.get('https://labs.google/fx/ko/tools/whisk/project')
    print("⏳ Whisk 페이지 로딩...", flush=True)
    time.sleep(5)

    abs_path = os.path.abspath(image_path)
    print(f"🔍 파일 업로드 시도: {os.path.basename(abs_path)}", flush=True)

    # 숨겨진 file input 생성
    driver.execute_script("""
        const input = document.createElement('input');
        input.type = 'file';
        input.id = 'auto-upload-input';
        input.accept = 'image/*';
        input.style.position = 'absolute';
        input.style.left = '-9999px';
        document.body.appendChild(input);
    """)

    print("✅ file input 생성 완료", flush=True)
    time.sleep(1)

    # 파일 할당
    file_input = driver.find_element(By.ID, 'auto-upload-input')
    print(f"📤 파일 할당 중...", flush=True)
    file_input.send_keys(abs_path)
    time.sleep(2)
    print("✅ 파일 할당 완료", flush=True)

    # 업로드 처리
    upload_result = driver.execute_script("""
        const input = document.getElementById('auto-upload-input');
        if (!input || !input.files || input.files.length === 0) {
            return {success: false, error: '파일이 할당되지 않음'};
        }

        const file = input.files[0];

        // change 이벤트 발생
        input.dispatchEvent(new Event('change', { bubbles: true }));

        // add_photo_alternate 버튼 찾기
        const findUploadButton = () => {
            const all = document.querySelectorAll('*');
            for (let elem of all) {
                const text = elem.textContent || '';
                if (elem.tagName === 'BUTTON' && text.includes('add_photo_alternate')) {
                    return elem;
                }
            }
            return null;
        };

        const btn = findUploadButton();
        if (btn) {
            const clickEvent = new MouseEvent('click', {
                bubbles: true,
                cancelable: true
            });
            btn.dispatchEvent(clickEvent);
        }

        return {
            success: true,
            fileName: file.name,
            fileSize: file.size
        };
    """)

    if not upload_result.get('success'):
        raise Exception(f"업로드 실패: {upload_result.get('error')}")

    print(f"✅ 파일 업로드 성공!", flush=True)
    print(f"   파일명: {upload_result.get('fileName')}", flush=True)
    print(f"   파일 크기: {upload_result.get('fileSize')} bytes", flush=True)
    time.sleep(3)

def input_prompt_to_whisk(driver, prompt, wait_time=WebDriverWait, is_first=False):
    """Whisk 입력창에 프롬프트 입력 (클립보드 + Ctrl+V 방식)"""
    try:
        # 클립보드에 프롬프트 복사
        pyperclip.copy(prompt)
        print(f"📋 클립보드에 복사: {prompt[:50]}...", flush=True)
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
                print(f"✅ 입력창 발견: {selector}", flush=True)
                break
            except:
                continue

        if not input_box:
            # 입력창을 못 찾으면 body를 클릭
            print("⚠️ 입력창을 찾지 못함, 페이지 클릭 시도", flush=True)
            body = driver.find_element(By.TAG_NAME, 'body')
            body.click()
        else:
            # 입력창 클릭
            input_box.click()
            time.sleep(0.3)

        # Ctrl+V로 붙여넣기만 수행
        actions = ActionChains(driver)
        actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
        print(f"✅ Ctrl+V 붙여넣기 완료", flush=True)
        time.sleep(0.5)

        # 엔터 키 입력
        actions = ActionChains(driver)
        actions.send_keys(Keys.RETURN).perform()
        print("⏎ 엔터 입력 완료", flush=True)
        time.sleep(1)

        # 생성 버튼 찾아서 클릭 (여러 가능한 텍스트/selector 시도)
        generate_button_found = False
        button_texts = ['Generate', 'Create', '생성', 'Remix', 'Go']
        button_selectors = [
            'button[type="submit"]',
            'button[aria-label*="generate"]',
            'button[aria-label*="create"]',
            'button:has-text("Generate")',
            '.generate-button',
            '[data-test-id="generate-button"]'
        ]

        # 텍스트로 버튼 찾기
        for text in button_texts:
            try:
                buttons = driver.find_elements(By.XPATH, f"//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{text.lower()}')]")
                for btn in buttons:
                    if btn.is_displayed() and btn.is_enabled():
                        btn.click()
                        print(f"✅ '{text}' 버튼 클릭 완료", flush=True)
                        generate_button_found = True
                        break
                if generate_button_found:
                    break
            except:
                continue

        # selector로 버튼 찾기 (텍스트로 못 찾았을 경우)
        if not generate_button_found:
            for selector in button_selectors:
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, selector)
                    if btn.is_displayed() and btn.is_enabled():
                        btn.click()
                        print(f"✅ 생성 버튼 클릭 완료 ({selector})", flush=True)
                        generate_button_found = True
                        break
                except:
                    continue

        if not generate_button_found:
            print("⚠️ 생성 버튼을 찾지 못함 - 엔터로 처리됨", flush=True)

        return True

    except Exception as e:
        print(f"❌ 입력 오류: {e}", flush=True)
        return False

def main(scenes_json_file, use_imagefx=False):
    """메인 실행 함수"""
    print("=" * 80, flush=True)
    if use_imagefx:
        print("🚀 ImageFX + Whisk 자동화 시작", flush=True)
    else:
        print("🚀 Whisk 자동화 시작", flush=True)
    print("=" * 80, flush=True)

    # JSON 파일 읽기
    try:
        with open(scenes_json_file, 'r', encoding='utf-8') as f:
            scenes = json.load(f)
    except Exception as e:
        print(f"❌ JSON 파일 읽기 실패: {e}", flush=True)
        return 1

    if not scenes or len(scenes) == 0:
        print("❌ 씬 데이터가 없습니다.", flush=True)
        return 1

    print(f"📝 총 {len(scenes)}개 씬 처리 예정\n", flush=True)

    driver = None
    try:
        driver = setup_chrome_driver()

        # ImageFX 사용 시 첫 이미지 생성 및 업로드
        if use_imagefx:
            # 첫 번째 씬 정보 확인
            first_scene = scenes[0]
            print(f"\n📋 첫 번째 씬 데이터:", flush=True)
            print(f"   scene_number: {first_scene.get('scene_number')}", flush=True)
            print(f"   scene_id: {first_scene.get('scene_id')}", flush=True)
            print(f"   has image_prompt: {bool(first_scene.get('image_prompt'))}", flush=True)
            print(f"   has sora_prompt: {bool(first_scene.get('sora_prompt'))}", flush=True)

            first_prompt = first_scene.get('image_prompt') or first_scene.get('sora_prompt') or ''

            if not first_prompt:
                print(f"❌ 첫 번째 씬에 프롬프트가 없습니다", flush=True)
                print(f"   씬 데이터: {first_scene}", flush=True)
                raise Exception("첫 번째 씬에 프롬프트가 없습니다")

            # 어떤 필드에서 읽었는지 로그
            prompt_source = 'image_prompt' if first_scene.get('image_prompt') else 'sora_prompt'
            print(f"✅ 프롬프트 읽기 성공 (출처: {prompt_source})", flush=True)
            print(f"   내용: {first_prompt[:100]}{'...' if len(first_prompt) > 100 else ''}\n", flush=True)

            # ImageFX로 첫 이미지 생성
            image_path = generate_image_with_imagefx(driver, first_prompt)

            # Whisk에 업로드
            upload_image_to_whisk(driver, image_path)

        else:
            # Whisk만 사용
            print(f"\n{'='*80}", flush=True)
            print(f"📌 Whisk 시작", flush=True)
            print(f"{'='*80}", flush=True)
            driver.get('https://labs.google/fx/ko/tools/whisk/project')
            time.sleep(3)

        # Whisk 프롬프트 입력
        print("\n" + "="*80, flush=True)
        print("3️⃣ Whisk - 프롬프트 입력", flush=True)
        print("="*80, flush=True)

        # 모든 씬을 순차적으로 처리
        for i in range(len(scenes)):
            scene = scenes[i]
            scene_number = scene.get('scene_number') or scene.get('scene_id') or f"scene_{str(i).zfill(2)}"

            # 프롬프트 읽기 (디버그 로그 포함)
            has_image_prompt = bool(scene.get('image_prompt'))
            has_sora_prompt = bool(scene.get('sora_prompt'))
            prompt = scene.get('image_prompt') or scene.get('sora_prompt') or ''

            if not prompt:
                print(f"⏭️ {scene_number} - 프롬프트 없음 (image_prompt: {has_image_prompt}, sora_prompt: {has_sora_prompt})", flush=True)
                continue

            # 프롬프트 출처 로그
            prompt_source = 'image_prompt' if scene.get('image_prompt') else 'sora_prompt'
            print(f"📝 {scene_number} - 프롬프트 출처: {prompt_source}", flush=True)
            print(f"   내용: {prompt[:80]}{'...' if len(prompt) > 80 else ''}", flush=True)

            # 타이밍 제어
            if i >= 3:  # scene_03부터
                delay = 15
                print(f"\n⏳ {scene_number} - {delay}초 대기 중...", flush=True)
                time.sleep(delay)
            elif i == 2:  # scene_02는 짧은 대기
                delay = 2
                print(f"\n⏳ {scene_number} - {delay}초 대기 중...", flush=True)
                time.sleep(delay)
            elif i == 1:  # scene_01은 약간의 대기
                time.sleep(0.5)
            # scene_00은 즉시 실행 (ImageFX 사용 시 이미 업로드됨)

            print(f"\n{'-'*80}", flush=True)
            print(f"📌 {scene_number} 입력 중...", flush=True)
            print(f"{'-'*80}", flush=True)

            # 프롬프트 입력
            success = input_prompt_to_whisk(driver, prompt, is_first=(i == 0))

            if success:
                # 다음 입력 전 대기
                time.sleep(2)
            else:
                print(f"⚠️ {scene_number} 입력 실패, 계속 진행...", flush=True)
                continue

        print(f"\n{'='*80}", flush=True)
        print("✅ 모든 프롬프트 입력 완료!", flush=True)
        print(f"{'='*80}", flush=True)

        # === 이미지 생성 대기 ===
        print("\n" + "="*80, flush=True)
        print("🕐 이미지 생성 대기", flush=True)
        print("="*80, flush=True)

        print("⏳ 이미지 생성 중... (최대 120초)", flush=True)

        # 디버그: 초기 페이지 상태 확인
        page_info = driver.execute_script("""
            return {
                url: window.location.href,
                title: document.title,
                bodyText: document.body.innerText.substring(0, 200)
            };
        """)
        print(f"📋 페이지 정보:", flush=True)
        print(f"   URL: {page_info['url']}", flush=True)
        print(f"   제목: {page_info['title']}", flush=True)
        print(f"   본문 일부: {page_info['bodyText'][:100]}...", flush=True)

        # 스크린샷 저장
        try:
            screenshot_path = os.path.join(os.path.dirname(os.path.abspath(scenes_json_file)), 'whisk_debug.png')
            driver.save_screenshot(screenshot_path)
            print(f"📸 스크린샷 저장: {screenshot_path}", flush=True)
        except Exception as e:
            print(f"⚠️ 스크린샷 저장 실패: {e}", flush=True)

        for i in range(120):
            result = driver.execute_script("""
                const text = document.body.innerText;
                const imgs = Array.from(document.querySelectorAll('img'));
                const largeImgs = imgs.filter(img => img.offsetWidth > 100 && img.offsetHeight > 100);
                const allImgs = imgs.map(img => ({
                    src: img.src.substring(0, 50),
                    width: img.offsetWidth,
                    height: img.offsetHeight
                }));
                return {
                    generating: text.includes('Generating') || text.includes('생성 중') || text.includes('Loading'),
                    imageCount: largeImgs.length,
                    allImagesCount: imgs.length,
                    sampleImages: allImgs.slice(0, 3)
                };
            """)

            if not result['generating'] and result['imageCount'] > 0:
                print(f"✅ 생성 완료! ({i+1}초) - 이미지 {result['imageCount']}개 발견", flush=True)
                break

            if i % 10 == 0 and i > 0:
                print(f"   대기 중... ({i}초) - 큰 이미지: {result['imageCount']}개, 전체: {result['allImagesCount']}개", flush=True)
                if i == 10 and result['allImagesCount'] > 0:
                    print(f"   샘플 이미지: {result['sampleImages']}", flush=True)
            time.sleep(1)

        time.sleep(5)

        # === 이미지 다운로드 ===
        print("\n" + "="*80, flush=True)
        print("📥 이미지 다운로드", flush=True)
        print("="*80, flush=True)

        # scenes_json_file 경로에서 폴더 찾기
        json_dir = os.path.dirname(os.path.abspath(scenes_json_file))
        output_folder = os.path.join(json_dir, 'images')
        os.makedirs(output_folder, exist_ok=True)
        print(f"📁 저장 폴더: {output_folder}", flush=True)

        # 페이지의 모든 이미지 찾기 (더 넓은 범위로)
        images = driver.execute_script("""
            const imgs = Array.from(document.querySelectorAll('img'));
            const filtered = imgs.filter(img => {
                // 크기가 충분히 큰 이미지만
                if (img.offsetWidth < 100 || img.offsetHeight < 100) return false;

                // base64나 blob URL 제외
                const src = img.src || '';
                if (src.startsWith('data:') || src.startsWith('blob:')) return false;

                // HTTP/HTTPS URL만
                if (!src.startsWith('http')) return false;

                return true;
            });

            return filtered.map(img => ({
                src: img.src,
                width: img.offsetWidth,
                height: img.offsetHeight,
                alt: img.alt || ''
            }));
        """)

        print(f"🔍 발견된 이미지: {len(images)}개", flush=True)

        # 디버그: 이미지 정보 출력
        for idx, img in enumerate(images[:5]):  # 최대 5개만 출력
            print(f"   [{idx+1}] {img['width']}x{img['height']} - {img['src'][:80]}...", flush=True)

        import requests
        downloaded = []
        for i, img_data in enumerate(images[:len(scenes)]):
            img_src = img_data['src']
            if not img_src.startswith('http'):
                continue

            scene = scenes[i]
            scene_number = scene.get('scene_number') or scene.get('scene_id') or f"scene_{str(i).zfill(2)}"
            ext = '.jpg'
            if 'png' in img_src.lower():
                ext = '.png'
            elif 'webp' in img_src.lower():
                ext = '.webp'

            output_path = os.path.join(output_folder, f"{scene_number}{ext}")

            try:
                response = requests.get(img_src, timeout=30)
                if response.status_code == 200:
                    with open(output_path, 'wb') as f:
                        f.write(response.content)
                    downloaded.append(output_path)
                    print(f"   ✅ {scene_number}{ext}", flush=True)
            except Exception as e:
                print(f"   ❌ {scene_number}: {e}", flush=True)

        print(f"\n✅ 다운로드 완료: {len(downloaded)}/{len(scenes)}", flush=True)
        print(f"📁 저장 위치: {output_folder}", flush=True)

        print(f"\n{'='*80}", flush=True)
        print("🎉 전체 워크플로우 완료!", flush=True)
        print(f"{'='*80}", flush=True)

        return 0

    except Exception as e:
        print(f"❌ 오류 발생: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # 브라우저는 열어둠 (사용자가 수동으로 다운로드 필요)
        print("\n⚠️ 브라우저를 열어둡니다. Whisk에서 이미지를 수동으로 다운로드하세요.", flush=True)
        if driver:
            # driver를 닫지 않음
            pass

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='이미지 크롤링 자동화')
    parser.add_argument('scenes_file', help='씬 데이터 JSON 파일')
    parser.add_argument('--use-imagefx', action='store_true', help='ImageFX로 첫 이미지 생성')

    args = parser.parse_args()

    sys.exit(main(args.scenes_file, use_imagefx=args.use_imagefx))
