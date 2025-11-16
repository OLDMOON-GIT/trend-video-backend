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

def generate_image_with_imagefx(driver, prompt, format_type='shortform'):
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

    # 종횡비 선택
    select_aspect_ratio(driver, format_type)

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
                # 다시 여러 방법으로 찾기
                recheck = driver.execute_script("""
                    // contenteditable="true" div
                    let elem = document.querySelector('div[contenteditable="true"]');
                    if (elem && elem.offsetParent !== null) {
                        return {found: true, type: 'contenteditable', selector: 'div[contenteditable="true"]'};
                    }

                    // role="textbox"
                    elem = document.querySelector('[role="textbox"]');
                    if (elem && elem.offsetParent !== null && elem.contentEditable === 'true') {
                        return {found: true, type: 'role-textbox', selector: '[role="textbox"]'};
                    }

                    // data-slate-editor="true"
                    elem = document.querySelector('[data-slate-editor="true"]');
                    if (elem && elem.offsetParent !== null) {
                        return {found: true, type: 'slate-editor', selector: '[data-slate-editor="true"]'};
                    }

                    return {found: false};
                """)
                if recheck.get('found'):
                    input_elem = recheck
                    print(f"✅ 활성화된 입력창 발견: {recheck.get('selector')}", flush=True)
                    break
                else:
                    print("   ⚠️ 활성화 후 입력창을 찾지 못함, 계속 검색...", flush=True)
                    # selector가 없으면 계속 검색
                    input_elem = None
                    continue
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
            if (!elem) return false;

            elem.scrollIntoView({behavior: 'instant', block: 'center'});
            elem.click();
            elem.focus();

            // 기존 내용 전체 선택 및 삭제
            if (elem.contentEditable === 'true') {
                // 방법 1: innerHTML 완전 초기화
                elem.innerHTML = '';

                // 방법 2: textContent 초기화
                elem.textContent = '';

                // 방법 3: Selection API로 전체 선택 후 삭제
                const selection = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(elem);
                selection.removeAllRanges();
                selection.addRange(range);
                document.execCommand('delete', false, null);

                // 확실하게 비웠는지 확인
                elem.innerHTML = '';
                elem.textContent = '';

                // 새 텍스트 입력 (여러 방법 시도)
                // 1. execCommand
                document.execCommand('insertText', false, newText);

                // 2. 만약 비어있으면 직접 설정
                if (!elem.textContent || elem.textContent.length === 0) {
                    elem.textContent = newText;
                }

                // 이벤트 발생
                elem.dispatchEvent(new Event('input', { bubbles: true }));
                elem.dispatchEvent(new Event('change', { bubbles: true }));
                elem.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true }));
                elem.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));

                return true;
            } else if (elem.tagName === 'TEXTAREA' || elem.tagName === 'INPUT') {
                elem.value = '';
                elem.value = newText;
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

        # 입력 확인 (실제 내용 검증)
        verify = driver.execute_script("""
            const selector = arguments[0];
            const expectedText = arguments[1];
            const elem = document.querySelector(selector);
            if (elem) {
                const content = elem.textContent || elem.innerText || elem.value || '';
                const cleanContent = content.trim().replace(/\\s+/g, ' ');
                const cleanExpected = expectedText.trim().replace(/\\s+/g, ' ');

                return {
                    length: content.length,
                    preview: content.substring(0, 80),
                    fullText: content,
                    matches: cleanContent.includes(cleanExpected.substring(0, 30))
                };
            }
            return {length: 0, preview: '', fullText: '', matches: false};
        """, input_elem.get('selector'), prompt)

        print(f"📋 입력 후 확인:", flush=True)
        print(f"   길이: {verify.get('length')}자", flush=True)
        print(f"   내용: {verify.get('preview')}...", flush=True)

        if verify.get('matches'):
            print(f"✅ 입력 검증 성공 - 올바른 내용 확인", flush=True)
        else:
            print(f"⚠️ 입력 검증 실패 - 예상과 다른 내용:", flush=True)
            print(f"   기대: {prompt[:50]}...", flush=True)
            print(f"   실제: {verify.get('fullText')[:100]}...", flush=True)
            print(f"⚠️ ActionChains로 재시도...", flush=True)

            # ActionChains로 재시도
            try:
                elem = driver.find_element(By.CSS_SELECTOR, input_elem.get('selector'))
                elem.click()
                time.sleep(0.5)

                # Ctrl+A로 전체 선택 후 삭제
                actions = ActionChains(driver)
                actions.key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).perform()
                time.sleep(0.2)
                actions = ActionChains(driver)
                actions.send_keys(Keys.DELETE).perform()
                time.sleep(0.2)

                # 새 내용 입력
                actions = ActionChains(driver)
                actions.send_keys(prompt).perform()
                print(f"✅ ActionChains로 재입력 완료", flush=True)
                time.sleep(1)

                # 다시 확인
                verify2 = driver.execute_script("""
                    const selector = arguments[0];
                    const elem = document.querySelector(selector);
                    if (elem) {
                        const content = elem.textContent || elem.innerText || elem.value || '';
                        return {
                            length: content.length,
                            preview: content.substring(0, 80)
                        };
                    }
                    return {length: 0, preview: ''};
                """, input_elem.get('selector'))
                print(f"📋 재입력 후: {verify2.get('length')}자 - {verify2.get('preview')}...", flush=True)
            except Exception as e:
                print(f"⚠️ ActionChains 재시도 실패: {e}", flush=True)

        # 입력 후 충분히 대기 (내용이 반영될 시간)
        print("⏳ 입력 내용 반영 대기 중...", flush=True)
        time.sleep(3)

        # 최종 확인: 입력창에 올바른 내용이 있는지 재확인
        final_check = driver.execute_script("""
            const selector = arguments[0];
            const expectedText = arguments[1];
            const elem = document.querySelector(selector);
            if (elem) {
                const content = elem.textContent || elem.innerText || elem.value || '';
                const cleanContent = content.trim().replace(/\\s+/g, ' ');
                const cleanExpected = expectedText.trim().replace(/\\s+/g, ' ');

                return {
                    hasContent: content.length > 0,
                    contentPreview: content.substring(0, 100),
                    matches: cleanContent.includes(cleanExpected.substring(0, 20))
                };
            }
            return {hasContent: false, contentPreview: '', matches: false};
        """, input_elem.get('selector'), prompt)

        print(f"📋 최종 확인:", flush=True)
        print(f"   내용 있음: {final_check.get('hasContent')}", flush=True)
        print(f"   매칭 여부: {final_check.get('matches')}", flush=True)
        print(f"   내용: {final_check.get('contentPreview')}...", flush=True)

        if not final_check.get('matches'):
            print("⚠️ 경고: 입력 내용이 예상과 다릅니다. 생성하면 엉뚱한 이미지가 나올 수 있습니다!", flush=True)
            print(f"   기대: {prompt[:50]}...", flush=True)

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

            // 오류 메시지 감지
            const errorMessages = [
                '여기에 표시할 정보가 없습니다',
                'No information to display',
                'Something went wrong',
                'Try again',
                'Sign in',
                '로그인',
                'quota',
                'limit exceeded',
                'not available',
                'Error'
            ];
            const hasError = errorMessages.some(msg => text.includes(msg));
            const errorText = hasError ? text.substring(0, 200) : '';

            return {
                hasLargeImage: largeImgs.length > 0,
                largeCount: largeImgs.length,
                totalCount: imgs.length,
                generating: text.includes('Generating') || text.includes('생성 중') || text.includes('Loading'),
                hasError: hasError,
                errorText: errorText,
                sampleImages: allImgs.slice(0, 3)
            };
        """)

        if result['hasLargeImage']:
            print(f"✅ 이미지 생성 완료! ({i+1}초) - 큰 이미지 {result['largeCount']}개 발견", flush=True)
            image_generated = True
            break

        # 오류 감지 - 15초 이상 대기 후 오류 메시지가 있으면 즉시 실패
        if i > 15 and result.get('hasError'):
            print(f"❌ ImageFX 오류 감지!", flush=True)
            print(f"   오류 내용: {result.get('errorText')}", flush=True)
            # 스크린샷
            try:
                import tempfile
                error_screenshot = os.path.join(tempfile.gettempdir(), 'imagefx_error.png')
                driver.save_screenshot(error_screenshot)
                print(f"📸 오류 스크린샷: {error_screenshot}", flush=True)
            except:
                pass
            raise Exception(f"❌ ImageFX 오류: {result.get('errorText')[:100]}")

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
    """Whisk에 이미지 업로드 (피사체 영역)"""
    print("\n" + "="*80, flush=True)
    print("2️⃣ Whisk - 피사체 이미지 업로드", flush=True)
    print("="*80, flush=True)

    driver.get('https://labs.google/fx/ko/tools/whisk/project')
    print("⏳ Whisk 페이지 로딩...", flush=True)
    time.sleep(5)

    abs_path = os.path.abspath(image_path)
    print(f"🔍 파일 업로드 시도: {os.path.basename(abs_path)}", flush=True)

    # 방법 1: 왼쪽 첫 번째 피사체 영역 찾아서 클릭
    print("🔍 피사체 영역 찾는 중...", flush=True)
    subject_clicked = driver.execute_script("""
        // 왼쪽 사이드바의 버튼들 찾기
        const buttons = Array.from(document.querySelectorAll('button'));

        // 방법 1: person 아이콘이 있는 버튼 찾기
        let subjectBtn = buttons.find(btn => {
            const text = btn.textContent || '';
            const html = btn.innerHTML || '';
            // person, account_circle, face 등의 아이콘 텍스트
            return text.includes('person') ||
                   text.includes('account') ||
                   html.includes('person') ||
                   html.includes('M12 12c2.21');  // person icon SVG path
        });

        // 방법 2: 첫 번째 점선 테두리 박스 찾기
        if (!subjectBtn) {
            const dashedBoxes = Array.from(document.querySelectorAll('[style*="dashed"], [class*="dashed"]'));
            if (dashedBoxes.length > 0) {
                const firstBox = dashedBoxes[0];
                const clickable = firstBox.querySelector('button') || firstBox;
                if (clickable) {
                    clickable.click();
                    return {success: true, method: 'dashed-box'};
                }
            }
        }

        // 방법 3: add_photo_alternate가 있는 첫 번째 버튼
        if (!subjectBtn) {
            subjectBtn = buttons.find(btn => {
                const text = btn.textContent || '';
                return text.includes('add_photo_alternate');
            });
        }

        if (subjectBtn) {
            subjectBtn.click();
            return {success: true, method: 'button-click'};
        }

        return {success: false};
    """)

    if subject_clicked.get('success'):
        print(f"✅ 피사체 영역 클릭: {subject_clicked.get('method')}", flush=True)
        time.sleep(2)
    else:
        print("⚠️ 피사체 영역을 찾지 못함, 직접 file input 검색", flush=True)

    # 방법 2: 페이지의 file input 찾아서 파일 할당
    print("🔍 file input 찾는 중...", flush=True)

    # 먼저 기존 file input 확인
    file_input_found = driver.execute_script("""
        const inputs = document.querySelectorAll('input[type="file"]');
        return inputs.length;
    """)

    print(f"   발견된 file input: {file_input_found}개", flush=True)

    # file input이 있으면 그것 사용, 없으면 생성
    if file_input_found > 0:
        # 첫 번째 file input 사용
        file_input = driver.find_element(By.CSS_SELECTOR, 'input[type="file"]')
        print("✅ 기존 file input 발견", flush=True)
    else:
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
        file_input = driver.find_element(By.ID, 'auto-upload-input')
        print("✅ file input 생성 완료", flush=True)

    time.sleep(1)

    # 파일 할당
    print(f"📤 파일 할당 중...", flush=True)
    file_input.send_keys(abs_path)
    time.sleep(2)
    print("✅ 파일 할당 완료", flush=True)

    # change 이벤트 발생
    driver.execute_script("""
        const input = document.querySelector('input[type="file"]');
        if (input) {
            input.dispatchEvent(new Event('change', { bubbles: true }));
            input.dispatchEvent(new Event('input', { bubbles: true }));
        }
    """)

    print("✅ change 이벤트 발생 완료", flush=True)
    time.sleep(3)

    # 업로드 확인
    uploaded = driver.execute_script("""
        // 업로드된 이미지 확인
        const imgs = Array.from(document.querySelectorAll('img'));
        const uploadedImg = imgs.find(img => {
            const src = img.src || '';
            // blob URL이나 새로운 이미지가 있는지 확인
            return src.startsWith('blob:') || src.includes('googleusercontent');
        });

        return {
            hasImage: !!uploadedImg,
            imageCount: imgs.length
        };
    """)

    if uploaded.get('hasImage'):
        print(f"✅ 이미지 업로드 확인 완료!", flush=True)
    else:
        print(f"⚠️ 이미지 업로드 확인 필요 (총 이미지: {uploaded.get('imageCount')}개)", flush=True)

    time.sleep(2)

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

        # 생성 버튼 찾아서 클릭 (JavaScript로 다양한 방법 시도)
        print("🔍 생성 버튼 찾는 중...", flush=True)
        generate_button_found = driver.execute_script("""
            // 방법 1: 화살표 아이콘 버튼 찾기 (→, arrow_forward)
            let buttons = Array.from(document.querySelectorAll('button'));

            // 1-1. arrow_forward 텍스트가 있는 버튼
            let arrowBtn = buttons.find(btn => {
                const text = btn.textContent || '';
                return text.includes('arrow_forward') ||
                       text.includes('→') ||
                       text.includes('chevron_right') ||
                       text.includes('east');
            });

            if (arrowBtn && arrowBtn.offsetParent !== null) {
                arrowBtn.click();
                return {success: true, method: 'arrow-icon'};
            }

            // 1-2. SVG 화살표 아이콘이 있는 버튼
            arrowBtn = buttons.find(btn => {
                const svg = btn.querySelector('svg');
                if (!svg) return false;
                const path = svg.querySelector('path');
                if (!path) return false;
                const d = path.getAttribute('d') || '';
                // 화살표 SVG path 패턴 (M12 4l-1.41 1.41L16.17 11H4v2h12.17...)
                return d.includes('M12') || d.includes('M10') || d.includes('arrow');
            });

            if (arrowBtn && arrowBtn.offsetParent !== null) {
                arrowBtn.click();
                return {success: true, method: 'arrow-svg'};
            }

            // 방법 2: Remix, Generate 등의 텍스트 버튼
            const textButtons = ['Remix', 'Generate', 'Create', '생성', 'Go', 'remix'];
            for (const text of textButtons) {
                const btn = buttons.find(b => {
                    const btnText = b.textContent.toLowerCase();
                    return btnText.includes(text.toLowerCase());
                });
                if (btn && btn.offsetParent !== null) {
                    btn.click();
                    return {success: true, method: 'text-' + text};
                }
            }

            // 방법 3: submit 타입 버튼
            const submitBtn = buttons.find(btn => btn.type === 'submit' && btn.offsetParent !== null);
            if (submitBtn) {
                submitBtn.click();
                return {success: true, method: 'submit'};
            }

            // 방법 4: 가장 오른쪽에 있는 큰 버튼 (보통 생성 버튼이 오른쪽에 위치)
            const visibleButtons = buttons.filter(btn => {
                if (btn.offsetParent === null) return false;
                if (btn.offsetWidth < 30 || btn.offsetHeight < 30) return false;
                return true;
            });

            if (visibleButtons.length > 0) {
                // x 좌표가 가장 큰 (오른쪽) 버튼 찾기
                visibleButtons.sort((a, b) => {
                    const rectA = a.getBoundingClientRect();
                    const rectB = b.getBoundingClientRect();
                    return rectB.right - rectA.right;
                });

                const rightmostBtn = visibleButtons[0];
                rightmostBtn.click();
                return {success: true, method: 'rightmost-button'};
            }

            return {success: false};
        """)

        if generate_button_found.get('success'):
            print(f"✅ 생성 버튼 클릭 완료 ({generate_button_found.get('method')})", flush=True)
            time.sleep(2)
        else:
            print("⚠️ 생성 버튼을 찾지 못했습니다", flush=True)


        return True

    except Exception as e:
        print(f"❌ 입력 오류: {e}", flush=True)
        return False

def select_aspect_ratio(driver, format_type='shortform'):
    """종횡비 선택 (9:16 또는 16:9)"""
    # 숏폼/SORA2: 9:16, 롱폼: 16:9
    aspect_ratio = '9:16' if format_type in ['shortform', 'sora2'] else '16:9'
    print(f"\n📐 종횡비 선택: {aspect_ratio} ({format_type})", flush=True)

    try:
        # 종횡비 버튼/드롭다운 찾아서 클릭
        result = driver.execute_script("""
            const targetRatio = arguments[0];  // "9:16" or "16:9"

            // 방법 1: 버튼 텍스트로 찾기
            const buttons = Array.from(document.querySelectorAll('button, div[role="button"]'));
            for (const btn of buttons) {
                const text = btn.textContent || '';
                if (text.includes(targetRatio) || text.includes('9 : 16') || text.includes('16 : 9')) {
                    if (text.includes(targetRatio.replace(':', ' : '))) {
                        btn.click();
                        return {success: true, method: 'button-text', found: text};
                    }
                }
            }

            // 방법 2: 종횡비 아이콘 찾기 (aspect_ratio, crop, dimensions 등)
            const ratioButtons = Array.from(document.querySelectorAll('[aria-label*="aspect"], [aria-label*="ratio"], [aria-label*="dimensions"]'));
            if (ratioButtons.length > 0) {
                ratioButtons[0].click();
                return {success: true, method: 'aria-label', needsSelection: true};
            }

            // 방법 3: 설정/옵션 버튼 찾기
            for (const btn of buttons) {
                const text = btn.textContent || '';
                const ariaLabel = btn.getAttribute('aria-label') || '';
                if (text.includes('settings') || text.includes('옵션') || text.includes('더보기') ||
                    ariaLabel.includes('settings') || ariaLabel.includes('options')) {
                    btn.click();
                    return {success: true, method: 'settings', needsSelection: true};
                }
            }

            return {success: false};
        """, aspect_ratio)

        if result.get('success'):
            print(f"✅ 종횡비 선택 완료: {result.get('method')}", flush=True)
            time.sleep(1)

            # 드롭다운/메뉴가 열렸으면 종횡비 선택
            if result.get('needsSelection'):
                select_result = driver.execute_script("""
                    const targetRatio = arguments[0];
                    const items = Array.from(document.querySelectorAll('[role="menuitem"], [role="option"], button, div'));
                    for (const item of items) {
                        const text = item.textContent || '';
                        if (text.includes(targetRatio) || text.includes(targetRatio.replace(':', ' : '))) {
                            item.click();
                            return {success: true, found: text};
                        }
                    }
                    return {success: false};
                """, aspect_ratio)

                if select_result.get('success'):
                    print(f"✅ 종횡비 항목 선택 완료: {select_result.get('found')}", flush=True)
                else:
                    print(f"⚠️ 종횡비 항목을 찾지 못했습니다 (기본값 사용)", flush=True)
        else:
            print(f"⚠️ 종횡비 버튼을 찾지 못했습니다 (기본값 사용)", flush=True)

        time.sleep(1)
    except Exception as e:
        print(f"⚠️ 종횡비 선택 중 오류: {e} (기본값 사용)", flush=True)

def main(scenes_json_file, use_imagefx=False, format_type='shortform'):
    """메인 실행 함수"""
    print("=" * 80, flush=True)
    if use_imagefx:
        print(f"🚀 ImageFX + Whisk 자동화 시작 ({format_type} - {('9:16' if format_type in ['shortform', 'sora2'] else '16:9')})", flush=True)
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
            image_path = generate_image_with_imagefx(driver, first_prompt, format_type)

            # Whisk에 업로드
            upload_image_to_whisk(driver, image_path)

            # Whisk에서도 종횡비 선택
            select_aspect_ratio(driver, format_type)

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

        # 최소 10초는 기다리기 (Whisk 이미지 생성 시간)
        min_wait = 10
        for i in range(120):
            result = driver.execute_script("""
                const text = document.body.innerText;
                const imgs = Array.from(document.querySelectorAll('img'));

                // 실제 생성된 이미지만 감지 (200x200 이상, blob나 http URL)
                const largeImgs = imgs.filter(img => {
                    if (img.offsetWidth < 200 || img.offsetHeight < 200) return false;
                    const src = img.src || '';
                    // data: URL 제외 (아이콘 등)
                    if (src.startsWith('data:')) return false;
                    // blob, http, https만 허용
                    if (!src.startsWith('http') && !src.startsWith('blob:')) return false;
                    return true;
                });

                const allImgs = imgs.map(img => ({
                    src: img.src.substring(0, 50),
                    width: img.offsetWidth,
                    height: img.offsetHeight
                }));

                return {
                    generating: text.includes('Generating') || text.includes('생성 중') || text.includes('Loading') || text.includes('Remix'),
                    imageCount: largeImgs.length,
                    allImagesCount: imgs.length,
                    sampleImages: allImgs.slice(0, 5),
                    largeImageDetails: largeImgs.map(img => ({
                        src: img.src.substring(0, 50),
                        width: img.offsetWidth,
                        height: img.offsetHeight
                    }))
                };
            """)

            # 최소 대기 시간 체크
            if i < min_wait:
                if i % 5 == 0:
                    print(f"   초기 대기 중... ({i}초)", flush=True)
                time.sleep(1)
                continue

            # 생성 완료 조건: 생성 중 아니고 + 씬 개수만큼 이미지가 있음
            expected_count = len(scenes)
            if not result['generating'] and result['imageCount'] >= expected_count:
                print(f"✅ 생성 완료! ({i+1}초) - 이미지 {result['imageCount']}개 발견 (예상: {expected_count}개)", flush=True)
                if result['largeImageDetails']:
                    for idx, img in enumerate(result['largeImageDetails'][:3]):
                        print(f"   [{idx+1}] {img['width']}x{img['height']} - {img['src']}...", flush=True)
                break

            if i % 10 == 0 and i >= min_wait:
                print(f"   대기 중... ({i}초) - 큰 이미지: {result['imageCount']}/{expected_count}개, 전체: {result['allImagesCount']}개", flush=True)
                if result['largeImageDetails']:
                    print(f"   큰 이미지: {result['largeImageDetails']}", flush=True)
            time.sleep(1)

        # 대기 시간 후에도 이미지 확인
        time.sleep(3)

        # === 이미지 다운로드 ===
        print("\n" + "="*80, flush=True)
        print("📥 이미지 다운로드", flush=True)
        print("="*80, flush=True)

        # scenes_json_file 경로에서 폴더 찾기
        json_dir = os.path.dirname(os.path.abspath(scenes_json_file))
        output_folder = os.path.join(json_dir, 'images')
        os.makedirs(output_folder, exist_ok=True)
        print(f"📁 저장 폴더: {output_folder}", flush=True)

        # 페이지의 모든 이미지 찾기 (blob URL 포함)
        images = driver.execute_script("""
            const imgs = Array.from(document.querySelectorAll('img'));
            const filtered = imgs.filter(img => {
                // 크기가 충분히 큰 이미지만
                if (img.offsetWidth < 200 || img.offsetHeight < 200) return false;

                const src = img.src || '';

                // data URL은 제외 (너무 작은 아이콘 등)
                if (src.startsWith('data:')) return false;

                // blob, HTTP, HTTPS URL 허용
                if (!src.startsWith('http') && !src.startsWith('blob:')) return false;

                return true;
            });

            return filtered.map(img => ({
                src: img.src,
                width: img.offsetWidth,
                height: img.offsetHeight,
                alt: img.alt || '',
                isBlob: img.src.startsWith('blob:')
            }));
        """)

        print(f"🔍 발견된 이미지: {len(images)}개", flush=True)

        # 이미지가 없으면 디버그 정보 출력
        if len(images) == 0:
            print("⚠️ 이미지를 찾을 수 없습니다. 모든 이미지 확인 중...", flush=True)
            all_imgs_debug = driver.execute_script("""
                const imgs = Array.from(document.querySelectorAll('img'));
                return imgs.map(img => ({
                    src: img.src.substring(0, 80),
                    width: img.offsetWidth,
                    height: img.offsetHeight,
                    visible: img.offsetParent !== null
                }));
            """)
            for idx, img in enumerate(all_imgs_debug[:10]):
                print(f"   [디버그 {idx+1}] {img['width']}x{img['height']} visible:{img['visible']} - {img['src']}", flush=True)

        # 디버그: 이미지 정보 출력
        for idx, img in enumerate(images[:5]):  # 최대 5개만 출력
            blob_str = " (blob)" if img.get('isBlob') else ""
            print(f"   [{idx+1}] {img['width']}x{img['height']}{blob_str} - {img['src'][:80]}...", flush=True)

        import requests
        import base64
        downloaded = []
        for i, img_data in enumerate(images[:len(scenes)]):
            img_src = img_data['src']
            is_blob = img_data.get('isBlob', False)

            scene = scenes[i]
            scene_number = scene.get('scene_number') or scene.get('scene_id') or f"scene_{str(i).zfill(2)}"
            ext = '.png'  # blob은 대부분 PNG로 저장
            if 'png' in img_src.lower():
                ext = '.png'
            elif 'jpg' in img_src.lower() or 'jpeg' in img_src.lower():
                ext = '.jpg'
            elif 'webp' in img_src.lower():
                ext = '.webp'

            output_path = os.path.join(output_folder, f"{scene_number}{ext}")

            try:
                if is_blob:
                    # blob URL을 canvas로 변환하여 base64로 다운로드
                    print(f"   📥 blob 이미지 다운로드 중: {scene_number}...", flush=True)
                    base64_data = driver.execute_script("""
                        return new Promise((resolve) => {
                            const img = new Image();
                            img.crossOrigin = 'anonymous';
                            img.onload = function() {
                                const canvas = document.createElement('canvas');
                                canvas.width = img.naturalWidth || img.width;
                                canvas.height = img.naturalHeight || img.height;
                                const ctx = canvas.getContext('2d');
                                ctx.drawImage(img, 0, 0);
                                const dataUrl = canvas.toDataURL('image/png');
                                resolve(dataUrl);
                            };
                            img.onerror = function() {
                                resolve(null);
                            };
                            img.src = arguments[0];
                        });
                    """, img_src)

                    if base64_data:
                        # base64 디코딩하여 파일로 저장
                        base64_str = base64_data.split(',')[1]
                        image_bytes = base64.b64decode(base64_str)
                        with open(output_path, 'wb') as f:
                            f.write(image_bytes)
                        downloaded.append(output_path)
                        print(f"   ✅ {scene_number}{ext} (blob)", flush=True)
                    else:
                        print(f"   ❌ {scene_number}: blob 변환 실패", flush=True)
                else:
                    # HTTP/HTTPS URL은 requests로 다운로드
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
    parser.add_argument('--format', choices=['shortform', 'longform', 'sora2'], help='영상 포맷 (종횡비 자동 선택)')

    args = parser.parse_args()

    # 파일명에서 format 자동 감지
    format_type = args.format
    if not format_type:
        filename = os.path.basename(args.scenes_file).lower()
        if 'sora2' in filename or 'shortform' in filename or 'short' in filename:
            format_type = 'shortform'  # 9:16
        elif 'longform' in filename or 'long' in filename:
            format_type = 'longform'  # 16:9
        else:
            format_type = 'shortform'  # 기본값: 9:16

    sys.exit(main(args.scenes_file, use_imagefx=args.use_imagefx, format_type=format_type))
