# -*- coding: utf-8 -*-
print("--- SCRIPT EXECUTION STARTED ---", flush=True)
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
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
import re

def detect_policy_violation(driver):
    """
    페이지에서 Google 정책 위반 메시지를 감지합니다.

    Returns:
        dict: {
            'violation_detected': bool,
            'message': str or None,
            'type': str or None ('policy', 'safety', 'content', etc.)
        }
    """
    try:
        result = driver.execute_script("""
            // 🔴 1단계: 에러/경고 UI 요소 찾기 (오탐 방지 핵심!)
            // 실제 정책 위반 메시지는 특정 UI 컴포넌트 안에만 표시됨
            const errorSelectors = [
                '[role="alert"]',
                '[role="status"]',
                '.error-message',
                '.warning-message',
                '.policy-violation',
                'div[class*="error"]',
                'div[class*="warning"]',
                'div[class*="alert"]',
                'span[class*="error"]',
                'p[class*="error"]'
            ];

            let errorElements = [];
            for (const selector of errorSelectors) {
                const elements = Array.from(document.querySelectorAll(selector));
                errorElements = errorElements.concat(elements);
            }

            // 추가: 에러 메시지 같은 텍스트 길이를 가진 요소들도 검사
            // (Whisk는 동적으로 생성되는 에러 메시지용 div 사용)
            const allDivs = Array.from(document.querySelectorAll('div, span, p'));
            for (const elem of allDivs) {
                const text = elem.textContent || '';
                // 길이가 30~300자 정도의 텍스트만 에러 메시지 후보로 간주
                if (text.length > 30 && text.length < 300) {
                    errorElements.push(elem);
                }
            }

            // 🔴 2단계: 에러 요소 내부에서만 정책 위반 패턴 검색
            const specificViolationPatterns = [
                // 한글 Google 정책 위반 메시지 (구체적인 문구)
                '유명인.*동영상.*생성.*google.*정책',
                '유명인.*google.*정책.*위반',
                'google.*정책.*위반.*유명인',

                // 영문 Google 정책 위반 메시지
                'celebrity.*video.*google.*policy',
                'violates.*google.*policy.*celebrity',
                'google.*policy.*violation.*celebrity'
            ];

            let violationDetected = false;
            let errorMessage = '';
            let matchedPatterns = [];

            // 에러 요소들 중에서만 패턴 검색
            for (const elem of errorElements) {
                const text = elem.textContent || '';
                const lowerText = text.toLowerCase();

                for (const pattern of specificViolationPatterns) {
                    const regex = new RegExp(pattern, 'i');
                    if (regex.test(lowerText)) {
                        violationDetected = true;
                        matchedPatterns.push(pattern);
                        errorMessage = text.trim();
                        break;  // 첫 매칭에서 종료
                    }
                }

                if (violationDetected) {
                    break;  // 정책 위반 발견 시 즉시 종료
                }
            }

            if (violationDetected) {
                return {
                    violation_detected: true,
                    matched_keywords: matchedPatterns,
                    message: errorMessage || '정책 위반 메시지 감지됨',
                    match_count: matchedPatterns.length
                };
            }

            return {
                violation_detected: false,
                matched_keywords: [],
                message: null,
                match_count: 0
            };
        """)

        return result
    except Exception as e:
        print(f"⚠️ 정책 위반 감지 실패: {e}", flush=True)
        return {
            'violation_detected': False,
            'message': None,
            'match_count': 0
        }

def sanitize_prompt_for_google(prompt, aggressive=False):
    """
    Google 이미지 정책 위반을 방지하기 위해 프롬프트를 안전하게 변환합니다.

    Google/Whisk/ImageFX 정책에서 금지하는 내용:
    - 폭력, 성인 콘텐츠, 혐오 발언
    - 실제 인물, 브랜드, 로고
    - 위험한 활동
    - 저작권 침해

    Args:
        prompt: 원본 프롬프트
        aggressive: True이면 더 강력한 필터링 적용
    """
    if not prompt or not isinstance(prompt, str):
        return prompt

    sanitized = prompt

    # 금지된 키워드 필터링 (대소문자 구분 없음)
    blocked_keywords = [
        # 브랜드/로고
        r'\b(nike|adidas|apple|samsung|sony|disney|marvel|coca-cola|pepsi|mcdonald|starbucks|amazon|google|microsoft)\b',
        # 실제 인물
        r'\b(celebrity|famous\s+person|politician|president|actor|actress|singer|athlete)\b',
        # 폭력적 표현
        r'\b(blood|gore|weapon|gun|knife|fight|combat|violence|war|explosion)\b',
        # 성인/선정적 표현
        r'\b(sexy|nude|naked|intimate|romantic|bedroom|bathroom)\b',
        # 위험한 활동
        r'\b(drunk|alcohol|smoking|drug|dangerous|reckless)\b',
    ]

    for pattern in blocked_keywords:
        sanitized = re.sub(pattern, '', sanitized, flags=re.IGNORECASE)

    # 특정 유해 단어 제거
    harmful_words = {
        'violent': 'dynamic',
        'aggressive': 'energetic',
        'sexy': 'elegant',
        'hot': 'warm',
        'kill': 'stop',
        'destroy': 'change',
        'attack': 'approach',
        'fight': 'interact',
        'blood': 'red liquid',
        'weapon': 'tool',
        'gun': 'device',
    }

    for harmful, safe in harmful_words.items():
        sanitized = re.sub(rf'\b{harmful}\b', safe, sanitized, flags=re.IGNORECASE)

    # 브랜드/로고 멘션 제거
    brand_replacements = {
        r'nike\s+': 'athletic ',
        r'adidas\s+': 'sports ',
        r'iphone': 'smartphone',
        r'samsung\s+galaxy': 'modern smartphone',
        r'macbook': 'laptop computer',
        r'coca-cola': 'soft drink',
        r'pepsi': 'carbonated beverage',
    }

    for brand_pattern, generic in brand_replacements.items():
        sanitized = re.sub(brand_pattern, generic, sanitized, flags=re.IGNORECASE)

    # Aggressive 모드: 안전 프리픽스 추가
    if aggressive:
        safe_prefix = "professional, safe for work, family-friendly, "
        if not any(keyword in sanitized.lower() for keyword in ['safe', 'professional', 'family-friendly']):
            sanitized = safe_prefix + sanitized

    # 중복 공백 제거
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()

    # 길이 제한
    max_length = 450
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rsplit(' ', 1)[0] + '...'

    # 변경사항이 있으면 로그 출력
    if sanitized != prompt:
        print(f"🔒 프롬프트 안전화 적용됨 (aggressive={aggressive})", flush=True)
        print(f"   원본: {prompt[:80]}{'...' if len(prompt) > 80 else ''}", flush=True)
        print(f"   안전: {sanitized[:80]}{'...' if len(sanitized) > 80 else ''}", flush=True)

    return sanitized

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
        r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
        os.path.expanduser(r"~\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe")
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

    driver.get('https://labs.google/fx/ko/tools/image-fx')
    print("⏳ ImageFX 페이지 로딩...", flush=True)

    # 페이지 완전 로드 대기 (네트워크 안정화 포함)
    for i in range(30):
        if driver.execute_script("return document.readyState") == "complete":
            print(f"✅ 로드 완료 ({i+1}초)", flush=True)
            break
        time.sleep(1)

    # 추가 대기: JavaScript 초기화 완료 대기
    print("⏳ Slate 에디터 초기화 대기...", flush=True)
    time.sleep(5)

    # 네트워크 안정화 대기 (이미지 로딩 등)
    driver.execute_script("""
        return new Promise((resolve) => {
            if (document.readyState === 'complete') {
                setTimeout(resolve, 2000);
            } else {
                window.addEventListener('load', () => setTimeout(resolve, 2000));
            }
        });
    """)
    print("✅ 페이지 완전 초기화 완료", flush=True)

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

    # 입력창을 찾는 대신, 클립보드를 이용한 직접 입력 시도
    try:
        print("📋 프롬프트를 클립보드에 복사하고 붙여넣기 시도...", flush=True)
        pyperclip.copy(prompt)
        time.sleep(0.5)

        # 페이지 중앙 클릭하여 포커스
        driver.execute_script("document.body.click();")
        time.sleep(0.5)

        # Ctrl+V 붙여넣기
        actions = ActionChains(driver)
        actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
        time.sleep(1)
        print("✅ Ctrl+V 붙여넣기 완료", flush=True)

        # 엔터 키 입력하여 생성 시작
        actions = ActionChains(driver)
        actions.send_keys(Keys.RETURN).perform()
        print("⏎ 엔터 입력 완료", flush=True)
        
        time.sleep(1)

        # 생성 버튼 찾아서 클릭 (추가된 안정성 로직)
        print("🔍 생성 버튼 찾는 중...", flush=True)
        generate_clicked = driver.execute_script("""
            const buttonTexts = ['Generate', 'Create', '생성', 'make', 'Go', '만들기', 'Remix'];
            for (const text of buttonTexts) {
                const buttons = Array.from(document.querySelectorAll('button'));
                for (const btn of buttons) {
                    const btnText = (btn.innerText || btn.textContent || '').trim().toLowerCase();
                    if (btnText === text.toLowerCase()) {
                        if (btn.offsetParent !== null && !btn.disabled) {
                            console.log('Found button by text:', btn);
                            btn.click();
                            return {success: true, method: 'by-text-' + text};
                        }
                    }
                }
            }
            return {success: false};
        """)

        if generate_clicked and generate_clicked.get('success'):
            print(f"✅ 생성 버튼 클릭 완료 ({generate_clicked.get('method')})", flush=True)
        else:
            print("⚠️ 생성 버튼을 찾지 못했습니다. Enter 입력으로 계속 진행합니다.", flush=True)

    except Exception as e:
        print(f"❌ 클립보드 입력 실패: {e}", flush=True)
        raise Exception(f"프롬프트 입력 실패: {e}")

    time.sleep(3)

    # 이미지 생성 대기
    print("⏳ 이미지 생성 대기 중... (최대 120초)", flush=True)
    image_generated = False
    for i in range(120):
        result = driver.execute_script("""
            const imgs = Array.from(document.querySelectorAll('img'));
            const largeImgs = imgs.filter(img => img.offsetWidth > 100 && img.offsetHeight > 100);
            const allImgs = imgs.map(img => ({
                src: (img.src || '').substring(0, 50),
                width: img.offsetWidth,
                height: img.offsetHeight
            }));
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
                    mid_screenshot = os.path.join(tempfile.gettempdir(), 'imagefx_gen_' + str(i) + 's.png')
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
        files_before.extend(glob.glob(os.path.join(download_dir, '*' + ext)))
        files_before.extend(glob.glob(os.path.join(download_dir, '*' + ext.upper())))
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
        files_after.extend(glob.glob(os.path.join(download_dir, '*' + ext)))
        files_after.extend(glob.glob(os.path.join(download_dir, '*' + ext.upper())))
    files_after = [f for f in files_after if not f.endswith('.crdownload') and not f.endswith('.tmp')]

    new_files = [f for f in files_after if f not in files_before]

    if new_files:
        latest_file = max(new_files, key=os.path.getctime)
        print(f"✅ 이미지 다운로드 확인: {os.path.basename(latest_file)}", flush=True)
        return latest_file
    else:
        raise Exception("❌ 다운로드된 이미지 파일을 찾을 수 없습니다 - Downloads 폴더에 새 파일이 없습니다")

def upload_image_to_whisk(driver, image_path, aspect_ratio=None):
    """Whisk에 이미지 업로드 (피사체 영역)"""
    print("\n" + "="*80, flush=True)
    print("2️⃣ Whisk - 피사체 이미지 업로드", flush=True)
    print("="*80, flush=True)

    driver.get('https://labs.google/fx/ko/tools/whisk/project')
    print("⏳ Whisk 페이지 로딩...", flush=True)
    time.sleep(5)

    # 비율 선택 (16:9 또는 9:16)
    if aspect_ratio:
        print(f"📐 비율 선택 시도: {aspect_ratio}", flush=True)

        # Step 1: 비율 선택 드롭다운/버튼 먼저 열기
        menu_open_result = driver.execute_script("""
            const allElements = Array.from(document.querySelectorAll('button, div[role="button"], div[role="combobox"]'));

            // "비율", "aspect", "ratio" 등의 텍스트를 포함하는 요소 찾기
            const ratioSelectorElements = allElements.filter(elem => {
                const text = (elem.textContent || '').toLowerCase();
                const ariaLabel = (elem.getAttribute('aria-label') || '').toLowerCase();
                return text.includes('비율') ||
                       text.includes('aspect') ||
                       text.includes('ratio') ||
                       ariaLabel.includes('비율') ||
                       ariaLabel.includes('aspect') ||
                       ariaLabel.includes('ratio');
            });

            // 드롭다운 열기
            if (ratioSelectorElements.length > 0) {
                ratioSelectorElements[0].click();
                return {
                    opened: true,
                    element: ratioSelectorElements[0].tagName,
                    text: ratioSelectorElements[0].textContent.substring(0, 50)
                };
            }

            return {opened: false, totalElements: allElements.length};
        """)

        if menu_open_result.get('opened'):
            print(f"✅ 비율 선택 메뉴 열림", flush=True)
            print(f"   요소: {menu_open_result.get('element')}", flush=True)
            time.sleep(1)  # 메뉴가 열릴 때까지 대기
        else:
            print(f"⚠️ 비율 선택 메뉴를 찾지 못함", flush=True)

        # Step 2: 원하는 비율 옵션 선택
        # JavaScript로 버튼 찾기
        ratio_button_info = driver.execute_script("""
            const targetRatio = arguments[0];

            // button 요소만 찾기
            const allButtons = Array.from(document.querySelectorAll('button'));

            // 정확히 targetRatio 텍스트만 가진 버튼 찾기
            const ratioButtons = allButtons.filter(button => {
                const text = button.textContent.trim();
                return text === targetRatio;
            });

            if (ratioButtons.length > 0) {
                const targetButton = ratioButtons[0];

                // 버튼에 고유 ID 추가 (Selenium으로 찾기 위해)
                targetButton.setAttribute('data-ratio-target', 'true');

                return {
                    found: true,
                    text: targetButton.textContent.trim(),
                    className: targetButton.className
                };
            }

            return {found: false};
        """, aspect_ratio)

        if ratio_button_info.get('found'):
            # Selenium WebElement를 찾아서 실제 클릭
            from selenium.webdriver.common.by import By
            try:
                ratio_button = driver.find_element(By.CSS_SELECTOR, 'button[data-ratio-target="true"]')
                ratio_button.click()  # Selenium의 실제 클릭
                time.sleep(0.5)

                aspect_ratio_result = {
                    'success': True,
                    'element': 'BUTTON',
                    'text': ratio_button_info['text'],
                    'className': ratio_button_info['className']
                }

                # 속성 제거
                driver.execute_script("document.querySelector('button[data-ratio-target]').removeAttribute('data-ratio-target');")
            except Exception as e:
                print(f"⚠️ Selenium 클릭 실패: {e}", flush=True)
                aspect_ratio_result = {'success': False}
        else:
            aspect_ratio_result = {'success': False}

        if aspect_ratio_result.get('success'):
            print(f"✅ 비율 선택 성공: {aspect_ratio}", flush=True)
            print(f"   요소: {aspect_ratio_result.get('element')}", flush=True)
            if aspect_ratio_result.get('role'):
                print(f"   역할: {aspect_ratio_result.get('role')}", flush=True)
            if aspect_ratio_result.get('text'):
                print(f"   텍스트: {aspect_ratio_result.get('text')}", flush=True)
            time.sleep(2)  # 비율 선택 후 대기
        else:
            print(f"⚠️ 비율 버튼을 찾지 못함: {aspect_ratio}", flush=True)
            print(f"   페이지 요소 개수: {aspect_ratio_result.get('totalElements', 0)}", flush=True)

    abs_path = os.path.abspath(image_path)
    print(f"🔍 파일 업로드 시도: {os.path.basename(abs_path)}", flush=True)

    # 방법 1: 왼쪽 사이드바 피사체 영역 찾기 (한글 텍스트로 식별)
    print("🔍 피사체 업로드 영역 찾는 중...", flush=True)

    # 피사체 영역을 정확하게 찾아서 클릭
    subject_clicked = driver.execute_script("""
        // Method 1: Find area containing upload or generation text
        const allElements = Array.from(document.querySelectorAll('div, button'));

        // Subject-related keywords
        const subjectKeywords = ['이미지를 업로드', '이미지를 생성', '파일 공유', '피사체'];
        let targetElement = null;

        for (const elem of allElements) {
            const text = elem.textContent || '';
            const hasKeyword = subjectKeywords.some(keyword => text.includes(keyword));

            if (hasKeyword) {
                const rect = elem.getBoundingClientRect();
                // Left sidebar area (x < 250px) with appropriate size
                if (rect.left < 250 && rect.width > 50 && rect.height > 50) {
                    targetElement = elem;

                    // Click button if exists inside
                    const innerButton = elem.querySelector('button');
                    if (innerButton && innerButton.offsetParent !== null) {
                        innerButton.click();
                        return {
                            success: true,
                            method: 'korean-text-inner-button',
                            text: text.substring(0, 50),
                            rect: {left: rect.left, top: rect.top, width: rect.width, height: rect.height}
                        };
                    }

                    // 버튼 없으면 해당 요소 직접 클릭
                    elem.click();
                    return {
                        success: true,
                        method: 'korean-text-element',
                        text: text.substring(0, 50),
                        rect: {left: rect.left, top: rect.top, width: rect.width, height: rect.height}
                    };
                }
            }
        }

        // 방법 2: 점선 박스 찾기 (fallback)
        const dashedDivs = Array.from(document.querySelectorAll('div, button')).filter(elem => {
            const style = window.getComputedStyle(elem);
            const rect = elem.getBoundingClientRect();
            // border-style에 dashed가 포함되고, 왼쪽 사이드바 영역 (x < 250px)이며, 너무 작지 않은 요소
            return (style.borderStyle === 'dashed' || style.borderStyle.includes('dashed')) &&
                   rect.left < 250 && rect.width > 50 && rect.height > 50;
        });

        if (dashedDivs.length > 0) {
            const firstDashed = dashedDivs[0];
            const rect = firstDashed.getBoundingClientRect();

            // 내부 버튼 찾기
            const innerButton = firstDashed.querySelector('button');
            if (innerButton && innerButton.offsetParent !== null) {
                innerButton.click();
                return {
                    success: true,
                    method: 'dashed-box-inner-button',
                    rect: {left: rect.left, top: rect.top, width: rect.width, height: rect.height}
                };
            }

            firstDashed.click();
            return {
                success: true,
                method: 'dashed-box-click',
                rect: {left: rect.left, top: rect.top, width: rect.width, height: rect.height}
            };
        }

        return {success: false, method: 'none'};
    """)

    if subject_clicked.get('success'):
        print(f"✅ 피사체 영역 클릭 성공: {subject_clicked.get('method')}", flush=True)
        if subject_clicked.get('text'):
            print(f"   텍스트: {subject_clicked.get('text')}", flush=True)
        if subject_clicked.get('rect'):
            print(f"   위치: {subject_clicked.get('rect')}", flush=True)
    else:
        print("⚠️ 피사체 영역을 찾지 못했습니다", flush=True)
        # 디버그: 왼쪽 사이드바 구조 출력
        debug_info = driver.execute_script("""
            const leftElements = Array.from(document.querySelectorAll('div, button')).filter(e => {
                const rect = e.getBoundingClientRect();
                return rect.left < 250 && rect.top > 80 && rect.top < 500;
            }).slice(0, 10);

            return leftElements.map(e => ({
                tag: e.tagName,
                text: (e.textContent || '').substring(0, 50),
                rect: {left: e.getBoundingClientRect().left, top: e.getBoundingClientRect().top}
            }));
        """)
        print(f"   왼쪽 사이드바 요소들: {debug_info}", flush=True)

    # 클릭 후 대기
    time.sleep(3)

    # 방법 2: file input 찾기 (최대 10초 대기)
    print("🔍 file input 찾는 중...", flush=True)

    file_input = None
    for attempt in range(10):
        try:
            # 모든 file input 찾기
            file_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')

            if file_inputs:
                # 가장 최근에 추가된 것 사용
                file_input = file_inputs[-1]
                print(f"✅ file input 발견 (시도 {attempt + 1}): 총 {len(file_inputs)}개", flush=True)
                break
        except:
            pass

        if attempt < 9:
            time.sleep(1)

    # file input을 못 찾으면 직접 JavaScript로 찾고 트리거
    if not file_input:
        print("⚠️ file input을 찾지 못함, JavaScript로 직접 처리", flush=True)

        # 파일 경로를 JavaScript로 전달하여 직접 처리
        upload_result = driver.execute_script("""
            const filePath = arguments[0];

            // 1. 기존 file input 찾기
            let fileInput = document.querySelector('input[type="file"]');

            // 2. 없으면 생성
            if (!fileInput) {
                fileInput = document.createElement('input');
                fileInput.type = 'file';
                fileInput.accept = 'image/*';
                fileInput.style.position = 'fixed';
                fileInput.style.top = '0';
                fileInput.style.left = '0';
                fileInput.style.opacity = '0.01';  // 완전히 투명하면 안 됨
                fileInput.style.width = '10px';
                fileInput.style.height = '10px';
                fileInput.style.zIndex = '99999';
                document.body.appendChild(fileInput);
            }

            return {
                found: !!fileInput,
                visible: fileInput.offsetParent !== null,
                id: fileInput.id || 'no-id'
            };
        """, abs_path)

        print(f"   JavaScript 결과: {upload_result}", flush=True)

        # 다시 file input 찾기
        try:
            file_input = driver.find_element(By.CSS_SELECTOR, 'input[type="file"]')
            print("✅ JavaScript로 file input 생성/발견", flush=True)
        except Exception as e:
            print(f"❌ file input을 찾을 수 없음: {e}", flush=True)
            raise Exception("file input을 찾거나 생성할 수 없습니다")

    # 파일 할당
    print(f"📤 파일 할당 중: {abs_path}", flush=True)
    try:
        file_input.send_keys(abs_path)
        time.sleep(2)
        print("✅ 파일 할당 완료", flush=True)
    except Exception as e:
        print(f"❌ 파일 할당 실패: {e}", flush=True)
        raise

    # change 이벤트 발생 및 확인
    driver.execute_script("""
        const inputs = Array.from(document.querySelectorAll('input[type="file"]'));
        console.log('File inputs found:', inputs.length);
        inputs.forEach((input, idx) => {
            console.log(`Input ${idx}:`, input.files?.length || 0, 'files');
            input.dispatchEvent(new Event('change', { bubbles: true }));
            input.dispatchEvent(new Event('input', { bubbles: true }));
        });
    """)

    print("✅ change 이벤트 발생 완료", flush=True)
    time.sleep(3)

    # 업로드 확인 (최대 10초 대기)
    upload_success = False
    for i in range(10):
        uploaded = driver.execute_script("""
            // 업로드된 이미지 확인
            const imgs = Array.from(document.querySelectorAll('img'));

            // 피사체 영역의 이미지 찾기
            const subjectImg = imgs.find(img => {
                const src = img.src || '';
                // blob URL이나 새로운 이미지
                if (!src.startsWith('blob:') && !src.includes('googleusercontent')) {
                    return false;
                }

                // 크기가 충분히 큰 이미지 (썸네일이 아닌)
                if (img.offsetWidth < 50 || img.offsetHeight < 50) {
                    return false;
                }

                return true;
            });

            return {
                hasImage: !!subjectImg,
                imageCount: imgs.length,
                imageSrc: subjectImg ? subjectImg.src.substring(0, 80) : '',
                imageSize: subjectImg ? `${subjectImg.offsetWidth}x${subjectImg.offsetHeight}` : ''
            };
        """)

        if uploaded.get('hasImage'):
            print(f"✅ 이미지 업로드 확인 완료!", flush=True)
            print(f"   이미지: {uploaded.get('imageSrc')}...", flush=True)
            print(f"   크기: {uploaded.get('imageSize')}", flush=True)
            upload_success = True
            break
        else:
            if i == 0:
                print(f"⏳ 업로드 확인 중... (총 이미지: {uploaded.get('imageCount')}개)", flush=True)
            time.sleep(1)

    if not upload_success:
        print(f"❌ 업로드 확인 실패 - 피사체 영역에 이미지가 표시되지 않았습니다", flush=True)
        # 디버그 스크린샷
        try:
            debug_path = abs_path.replace('.jpg', '_upload_debug.png').replace('.png', '_upload_debug.png')
            driver.save_screenshot(debug_path)
            print(f"📸 디버그 스크린샷: {debug_path}", flush=True)
        except:
            pass
        raise Exception("❌ Whisk 피사체 영역에 이미지 업로드 실패")

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

            # 기존 텍스트 전체 선택 및 삭제 (중요: 이전 프롬프트 제거)
            actions = ActionChains(driver)
            actions.key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).perform()
            time.sleep(0.2)
            actions.send_keys(Keys.DELETE).perform()
            time.sleep(0.2)
            print(f"🗑️ 기존 입력 내용 삭제 완료", flush=True)

        # Ctrl+V로 붙여넣기 수행
        actions = ActionChains(driver)
        actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
        print(f"✅ Ctrl+V 붙여넣기 완료", flush=True)
        time.sleep(0.8)

        # 엔터 키 입력 (생성 시작)
        actions = ActionChains(driver)
        actions.send_keys(Keys.RETURN).perform()
        print("⏎ 엔터 입력 완료 (생성 시작)", flush=True)
        time.sleep(1)
        # 엔터만으로 생성이 시작되므로 버튼 클릭은 하지 않음 (중복 실행 방지)
        return True

    except Exception as e:
        print(f"❌ 입력 오류: {e}", flush=True)
        return False

def download_images(driver, images, output_folder, scenes):
    """주어진 이미지 리스트를 지정된 폴더에 다운로드합니다."""
    print("\n" + "="*80, flush=True)
    print("📥 이미지 다운로드 시작...", flush=True)
    print("="*80, flush=True)
    print(f"📁 저장 폴더: {output_folder}", flush=True)
    print(f"🔍 다운로드 대상 이미지: {len(images)}개", flush=True)

    if not images:
        print("⚠️ 다운로드할 이미지가 없습니다.", flush=True)
        return 0

    # 디버그: 이미지 정보 상세 출력
    for idx, img in enumerate(images):
        print(f"   - 이미지 [{idx+1}]: {img['width']}x{img['height']}, src: {img['src'][:120]}...", flush=True)

    import requests
    import base64
    downloaded_count = 0
    for i, img_data in enumerate(images[:len(scenes)]):
        img_src = img_data['src']
        scene = scenes[i]
        scene_number = scene.get('scene_number') or scene.get('scene_id') or f"scene_{str(i).zfill(2)}"
        
        print(f"   [+] {scene_number} 다운로드 처리 시작... (src: {img_src[:60]}...)", flush=True)
        
        try:
            if img_data.get('isBlob'):
                print("     - Blob URL 감지. JavaScript로 base64 데이터 추출 시도.", flush=True)
                base64_data = driver.execute_script("""
                    const url = arguments[0];
                    return new Promise((resolve, reject) => {
                        fetch(url)
                            .then(res => res.blob())
                            .then(blob => {
                                const reader = new FileReader();
                                reader.onloadend = () => resolve(reader.result);
                                reader.onerror = reject;
                                reader.readAsDataURL(blob);
                            });
                    });
                """, img_src)

                if base64_data and base64_data.startswith('data:image'):
                    header, base64_str = base64_data.split(',', 1)
                    ext = '.' + header.split(';')[0].split('/')[-1] if 'image' in header else '.png'
                    output_path = os.path.join(output_folder, f"{scene_number}{ext}")
                    
                    image_bytes = base64.b64decode(base64_str)
                    with open(output_path, 'wb') as f:
                        f.write(image_bytes)
                    print(f"     ✅ 성공 (blob): {os.path.basename(output_path)}", flush=True)
                    downloaded_count += 1
                else:
                    print(f"     ❌ 실패: blob URL을 base64로 변환하지 못했습니다.", flush=True)
            
            elif img_src.startswith('http'):
                print("     - HTTP/HTTPS URL 감지. requests로 다운로드 시도.", flush=True)
                ext = '.jpg'
                if 'png' in img_src.lower(): ext = '.png'
                elif 'webp' in img_src.lower(): ext = '.webp'
                output_path = os.path.join(output_folder, f"{scene_number}{ext}")

                response = requests.get(img_src, timeout=30, headers={'Referer': 'https://labs.google/'})
                if response.status_code == 200:
                    with open(output_path, 'wb') as f:
                        f.write(response.content)
                    print(f"     ✅ 성공 (http): {os.path.basename(output_path)}", flush=True)
                    downloaded_count += 1
                else:
                    print(f"     ❌ 실패: HTTP 상태 코드 {response.status_code}", flush=True)
            else:
                print(f"     ⚠️ 알 수 없는 URL 형식: {img_src[:60]}...", flush=True)

        except Exception as e:
            print(f"     ❌ 예외 발생: {e}", flush=True)
            import traceback
            traceback.print_exc()

    print(f"\n✅ 다운로드 완료: 총 {downloaded_count}/{len(scenes)}개 파일 저장됨.", flush=True)
    return downloaded_count

def main(scenes_json_file, use_imagefx=False, output_dir=None):
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
            data = json.load(f)

        # scenes가 배열이면 그대로, 객체면 scenes 키에서 추출
        if isinstance(data, list):
            scenes = data
            aspect_ratio = None  # 배열 형식에는 metadata 없음
            product_thumbnail = None  # 배열 형식에는 product_info 없음
        elif isinstance(data, dict) and 'scenes' in data:
            scenes = data['scenes']
            # metadata에서 aspect_ratio 추출
            metadata = data.get('metadata', {})
            aspect_ratio = metadata.get('aspect_ratio')
            format_type = metadata.get('format')

            # product_info에서 썸네일 추출 (상품 영상인 경우)
            product_info = data.get('product_info', {})
            product_thumbnail = product_info.get('thumbnail', '')

            # format 필드에서 비율 결정
            # 원칙: metadata.aspect_ratio가 있으면 그것을 우선, 없으면 format 기반으로 결정
            # longform만 16:9, 나머지는 모두 9:16
            if not aspect_ratio:  # ✅ metadata에서 aspect_ratio가 없을 때만 format으로 결정
                if format_type:
                    # 1. longform이거나 format에 '16:9'가 명시되어 있으면 16:9
                    if format_type == 'longform' or '16:9' in str(format_type):
                        aspect_ratio = '16:9'
                    # 2. 나머지는 모두 9:16 (shortform, product, sora2 등)
                    else:
                        aspect_ratio = '9:16'
                else:
                    aspect_ratio = '9:16'  # 기본값
            # ✅ aspect_ratio가 이미 metadata에서 설정되었으면, 그대로 사용

            print(f"📐 비디오 형식: {format_type or 'unknown'}, 비율: {aspect_ratio or 'default'}", flush=True)
            if product_thumbnail:
                print(f"🛒 상품 썸네일: {product_thumbnail[:80]}...", flush=True)
        else:
            print(f"❌ JSON 형식 오류: scenes 배열을 찾을 수 없습니다", flush=True)
            print(f"   JSON 키들: {list(data.keys()) if isinstance(data, dict) else 'list'}", flush=True)
            return 1
    except Exception as e:
        print(f"❌ JSON 파일 읽기 실패: {e}", flush=True)
        return 1

    if not scenes or len(scenes) == 0:
        print("❌ 씬 데이터가 없습니다.", flush=True)
        return 1

    print(f"📝 총 {len(scenes)}개 씬 처리 예정\n", flush=True)

    # 출력 폴더 결정 (per-scene collection에서 사용하기 위해 미리 정의)
    if output_dir:
        output_folder = os.path.abspath(output_dir)
    else:
        output_folder = os.path.dirname(os.path.abspath(scenes_json_file))

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

            # Whisk에 업로드 (aspect_ratio 전달)
            upload_image_to_whisk(driver, image_path, aspect_ratio)

        else:
            # Whisk만 사용
            print(f"\n{'='*80}", flush=True)
            print(f"📌 Whisk 시작", flush=True)
            print(f"{ '='*80}", flush=True)
            driver.get('https://labs.google/fx/ko/tools/whisk/project')
            time.sleep(3)

            # 비율 선택 (Whisk만 사용할 때)
            if aspect_ratio:
                print(f"📐 비율 선택 시도: {aspect_ratio}", flush=True)

                # Step 1: 비율 선택 드롭다운/버튼 먼저 열기
                menu_open_result = driver.execute_script("""
                    const allElements = Array.from(document.querySelectorAll('button, div[role="button"], div[role="combobox"]'));

                    // "비율", "aspect", "ratio" 등의 텍스트를 포함하는 요소 찾기
                    const ratioSelectorElements = allElements.filter(elem => {
                        const text = (elem.textContent || '').toLowerCase();
                        const ariaLabel = (elem.getAttribute('aria-label') || '').toLowerCase();
                        return text.includes('비율') ||
                               text.includes('aspect') ||
                               text.includes('ratio') ||
                               ariaLabel.includes('비율') ||
                               ariaLabel.includes('aspect') ||
                               ariaLabel.includes('ratio');
                    });

                    // 드롭다운 열기
                    if (ratioSelectorElements.length > 0) {
                        ratioSelectorElements[0].click();
                        return {
                            opened: true,
                            element: ratioSelectorElements[0].tagName,
                            text: ratioSelectorElements[0].textContent.substring(0, 50)
                        };
                    }

                    return {opened: false, totalElements: allElements.length};
                """)

                if menu_open_result.get('opened'):
                    print(f"✅ 비율 선택 메뉴 열림", flush=True)
                    print(f"   요소: {menu_open_result.get('element')}", flush=True)
                    time.sleep(1)  # 메뉴가 열릴 때까지 대기
                else:
                    print(f"⚠️ 비율 선택 메뉴를 찾지 못함", flush=True)

                # Step 2: 원하는 비율 옵션 선택 (Selenium click 사용)
                # JavaScript로 버튼 찾기
                ratio_button_info = driver.execute_script("""
                    const targetRatio = arguments[0];

                    // button 요소만 찾기 (더 정확함)
                    const allButtons = Array.from(document.querySelectorAll('button'));

                    // 정확히 targetRatio 텍스트만 가진 버튼 찾기
                    const ratioButtons = allButtons.filter(button => {
                        const text = button.textContent.trim();
                        return text === targetRatio;
                    });

                    if (ratioButtons.length > 0) {
                        const targetButton = ratioButtons[0];

                        // 버튼에 고유 ID 추가 (Selenium으로 찾기 위해)
                        targetButton.setAttribute('data-ratio-target', 'true');

                        return {
                            found: true,
                            text: targetButton.textContent.trim(),
                            className: targetButton.className
                        };
                    }

                    return {found: false};
                """, aspect_ratio)

                if ratio_button_info.get('found'):
                    # Selenium WebElement를 찾아서 실제 클릭 (더 확실함)
                    from selenium.webdriver.common.by import By
                    try:
                        ratio_button = driver.find_element(By.CSS_SELECTOR, 'button[data-ratio-target="true"]')
                        ratio_button.click()  # Selenium의 실제 클릭
                        time.sleep(0.5)  # 클릭 후 대기

                        aspect_ratio_result = {
                            'success': True,
                            'element': 'BUTTON',
                            'text': ratio_button_info['text'],
                            'className': ratio_button_info['className']
                        }

                        # 속성 제거
                        driver.execute_script("document.querySelector('button[data-ratio-target]').removeAttribute('data-ratio-target');")
                    except Exception as e:
                        print(f"⚠️ Selenium 클릭 실패: {e}", flush=True)
                        aspect_ratio_result = {'success': False}
                else:
                    aspect_ratio_result = {'success': False}

                if aspect_ratio_result.get('success'):
                    print(f"✅ 비율 선택 성공: {aspect_ratio}", flush=True)
                    print(f"   요소: {aspect_ratio_result.get('element')}", flush=True)
                    if aspect_ratio_result.get('role'):
                        print(f"   역할: {aspect_ratio_result.get('role')}", flush=True)
                    if aspect_ratio_result.get('text'):
                        print(f"   텍스트: {aspect_ratio_result.get('text')}", flush=True)
                    time.sleep(2)  # 비율 선택 후 대기
                else:
                    print(f"⚠️ 비율 버튼을 찾지 못함: {aspect_ratio}", flush=True)
                    print(f"   페이지 요소 개수: {aspect_ratio_result.get('totalElements', 0)}", flush=True)

        # 상품 썸네일이 있으면 Whisk에 먼저 업로드
        product_thumbnail_path = None
        if product_thumbnail:
            print("\n" + "="*80, flush=True)
            print("🛒 상품 썸네일 다운로드 및 업로드", flush=True)
            print("="*80, flush=True)

            try:
                import requests
                import tempfile

                # 임시 파일에 썸네일 다운로드
                response = requests.get(product_thumbnail, timeout=30)
                if response.status_code == 200:
                    # 확장자 결정
                    ext = '.jpg'
                    if 'png' in product_thumbnail.lower():
                        ext = '.png'
                    elif 'webp' in product_thumbnail.lower():
                        ext = '.webp'

                    # 임시 파일 저장
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                    temp_file.write(response.content)
                    temp_file.close()
                    product_thumbnail_path = temp_file.name

                    print(f"✅ 썸네일 다운로드 완료: {os.path.basename(product_thumbnail_path)}", flush=True)

                    # Whisk에 썸네일 업로드
                    upload_image_to_whisk(driver, product_thumbnail_path, aspect_ratio)
                    print(f"✅ 상품 썸네일 Whisk 업로드 완료", flush=True)
                else:
                    print(f"⚠️ 썸네일 다운로드 실패: HTTP {response.status_code}", flush=True)
            except Exception as e:
                print(f"⚠️ 썸네일 처리 실패: {e}", flush=True)

        # Whisk 프롬프트 입력
        print("\n" + "="*80, flush=True)
        print("3️⃣ Whisk - 프롬프트 입력", flush=True)
        print("="*80, flush=True)

        # 중복 방지용: 이미 다운로드한 이미지 src 추적 (Whisk variation 중복 방지)
        downloaded_image_srcs = set()

        # 모든 씬을 순차적으로 처리
        for i in range(len(scenes)):
            scene = scenes[i]
            scene_number = scene.get('scene_number') or scene.get('scene_id') or f"scene_{str(i).zfill(2)}"

            # 프롬프트 읽기 (디버그 로그 포함)
            prompt = scene.get('image_prompt') or scene.get('sora_prompt') or ''

            if not prompt:
                print(f"⏭️ {scene_number} - 프롬프트 없음", flush=True)
                continue

            # 디버그: 원본 프롬프트 일부 출력 (중복 확인용)
            print(f"\n🔍 {scene_number} 프롬프트 확인:", flush=True)
            print(f"   첫 100자: {prompt[:100]}...", flush=True)
            print(f"   마지막 50자: ...{prompt[-50:]}", flush=True)

            max_retries = 3  # 정책 위반 재시도 포함하여 3회로 증가
            safe_prompt = prompt  # 첫 시도는 원본 사용
            aggressive_sanitize = False

            for attempt in range(max_retries):
                print(f"\n{'-'*80}", flush=True)
                print(f"📌 {scene_number} 입력 중 (시도 {attempt + 1}/{max_retries})...", flush=True)
                print(f"{'-'*80}", flush=True)

                # 2번째 시도부터 점진적으로 강한 필터링 적용
                if attempt == 1:
                    print(f"🔄 프롬프트 안전화 적용 (기본 모드)", flush=True)
                    safe_prompt = sanitize_prompt_for_google(prompt, aggressive=False)
                elif attempt == 2:
                    print(f"🔄 프롬프트 안전화 적용 (강화 모드)", flush=True)
                    safe_prompt = sanitize_prompt_for_google(prompt, aggressive=True)

                prompt_source = 'image_prompt' if scene.get('image_prompt') else 'sora_prompt'
                print(f"   프롬프트 출처: {prompt_source}", flush=True)
                print(f"   내용: {safe_prompt[:80]}{'...' if len(safe_prompt) > 80 else ''}", flush=True)

                # 프롬프트 입력
                success = input_prompt_to_whisk(driver, safe_prompt, is_first=(i == 0 and attempt == 0))

                if not success:
                    print(f"⚠️ {scene_number} 입력 실패", flush=True)
                    if attempt < max_retries - 1:
                        print(f"   {max_retries - attempt - 1}회 재시도 남음", flush=True)
                        time.sleep(3)
                        continue
                    else:
                        print(f"   ❌ 최대 재시도 횟수 초과, 다음 씬으로 이동", flush=True)
                        break

                # 입력 성공 후 정책 위반 검사 (2초 대기 후)
                time.sleep(2)
                print(f"🔍 정책 위반 여부 확인 중...", flush=True)
                violation_check = detect_policy_violation(driver)

                if violation_check.get('violation_detected'):
                    print(f"⚠️ Google 정책 위반 감지!", flush=True)
                    print(f"   매칭 키워드: {violation_check.get('matched_keywords', [])}", flush=True)
                    if violation_check.get('message'):
                        print(f"   메시지: {violation_check['message'][:100]}...", flush=True)

                    if attempt < max_retries - 1:
                        print(f"🔄 프롬프트를 수정하여 재시도합니다...", flush=True)
                        time.sleep(3)
                        continue
                    else:
                        print(f"   ❌ 최대 재시도 횟수 초과, 다음 씬으로 이동", flush=True)
                        break

                # 입력 성공 및 정책 위반 없음
                print(f"✅ {scene_number} 입력 완료 (정책 위반 없음)", flush=True)
                break  # 성공하면 재시도 루프 탈출

            # Whisk가 이미지를 생성할 시간 대기 (씬당 최소 30초)
            generation_wait = 30
            print(f"\n⏳ 이미지 생성 대기 중... ({generation_wait}초)", flush=True)
            time.sleep(generation_wait)

            # 🔴 각 씬의 이미지를 즉시 수집 (모든 씬 처리 후가 아니라 각 씬마다)
            # 이렇게 해야 씬 00의 이미지가 반복되지 않음
            print(f"\n📥 {scene_number}의 이미지 수집 중...", flush=True)
            try:
                # 🔴 중요: 이미 다운로드한 src 목록을 JavaScript로 전달
                already_downloaded = list(downloaded_image_srcs)

                # Whisk 페이지에서 생성된 이미지 찾기 (이번 씬만)
                scene_image = driver.execute_script("""
                    const imgs = Array.from(document.querySelectorAll('img'));
                    const alreadyDownloaded = arguments[0];  // Python에서 전달받은 이미 다운로드한 src 목록

                    // 가장 최근에 생성된 큰 이미지 찾기
                    let excludedCount = 0;
                    const validImgs = imgs.filter(img => {
                        if (img.offsetWidth < 100 || img.offsetHeight < 100) return false;
                        const src = img.src || '';
                        if (src.startsWith('data:')) return false;
                        if (!src.startsWith('http') && !src.startsWith('blob:')) return false;

                        // 🔴 핵심: 이미 다운로드한 이미지는 제외!
                        if (alreadyDownloaded.includes(src)) {
                            excludedCount++;
                            return false;
                        }

                        return true;
                    });

                    // 크기 순으로 정렬 (가장 큰 것이 생성된 이미지)
                    const sorted = validImgs.sort((a, b) => {
                        const sizeA = a.offsetWidth * a.offsetHeight;
                        const sizeB = b.offsetWidth * b.offsetHeight;
                        return sizeB - sizeA;
                    });

                    // 첫 번째 이미지와 모든 variation src 반환
                    if (sorted.length > 0) {
                        const img = sorted[0];
                        // Whisk의 모든 variation src 수집 (중복 방지용)
                        const allVariationSrcs = sorted.map(img => img.src);
                        return {
                            src: img.src,
                            width: img.offsetWidth,
                            height: img.offsetHeight,
                            isBlob: img.src.startsWith('blob:'),
                            allSrcs: allVariationSrcs,  // 모든 variation src 배열
                            totalImages: imgs.length,
                            excludedCount: excludedCount,
                            candidateCount: validImgs.length
                        };
                    }
                    return {
                        src: null,
                        totalImages: imgs.length,
                        excludedCount: excludedCount,
                        candidateCount: validImgs.length
                    };
                """, already_downloaded)

                print(f"   📊 이미지 통계: 전체 {scene_image.get('totalImages', 0)}개, "
                      f"제외 {scene_image.get('excludedCount', 0)}개, "
                      f"후보 {scene_image.get('candidateCount', 0)}개", flush=True)

                if scene_image and scene_image.get('src'):
                    print(f"   ✅ 이미지 발견: {scene_image['width']}x{scene_image['height']}", flush=True)
                    # 이미지 즉시 다운로드
                    import requests
                    import base64

                    try:
                        download_success = False

                        if scene_image.get('isBlob'):
                            base64_data = driver.execute_script("""
                                const url = arguments[0];
                                return new Promise((resolve, reject) => {
                                    fetch(url)
                                        .then(res => res.blob())
                                        .then(blob => {
                                            const reader = new FileReader();
                                            reader.onloadend = () => resolve(reader.result);
                                            reader.onerror = reject;
                                            reader.readAsDataURL(blob);
                                        });
                                });
                            """, scene_image['src'])

                            if base64_data and base64_data.startswith('data:image'):
                                header, base64_str = base64_data.split(',', 1)
                                ext = '.' + header.split(';')[0].split('/')[-1] if 'image' in header else '.png'
                                output_path = os.path.join(output_folder, f"{scene_number}{ext}")

                                image_bytes = base64.b64decode(base64_str)
                                with open(output_path, 'wb') as f:
                                    f.write(image_bytes)
                                print(f"   ✅ 저장 완료: {os.path.basename(output_path)}", flush=True)
                                download_success = True

                        elif scene_image['src'].startswith('http'):
                            ext = '.jpg'
                            if 'png' in scene_image['src'].lower(): ext = '.png'
                            elif 'webp' in scene_image['src'].lower(): ext = '.webp'
                            output_path = os.path.join(output_folder, f"{scene_number}{ext}")

                            response = requests.get(scene_image['src'], timeout=30, headers={'Referer': 'https://labs.google/'})
                            if response.status_code == 200:
                                with open(output_path, 'wb') as f:
                                    f.write(response.content)
                                print(f"   ✅ 저장 완료: {os.path.basename(output_path)}", flush=True)
                                download_success = True

                        # 🔴 중복 방지: 다운로드 성공 시 모든 variation src 기록
                        if download_success:
                            all_srcs = scene_image.get('allSrcs', [scene_image['src']])
                            for src in all_srcs:
                                downloaded_image_srcs.add(src)
                            print(f"   📝 이미지 src 기록됨: {len(all_srcs)}개 variations (총 {len(downloaded_image_srcs)}개 기록)", flush=True)

                    except Exception as e:
                        print(f"   ❌ 다운로드 실패: {e}", flush=True)
                else:
                    print(f"   ⚠️ 이미지를 찾을 수 없습니다", flush=True)
            except Exception as e:
                print(f"   ❌ 이미지 수집 실패: {e}", flush=True)

            # 타이밍 제어 - 각 프롬프트 제출 후 충분한 대기 시간 확보
            if i < len(scenes) - 1:  # 마지막 씬이 아니면
                if i == 0:  # 첫 번째 씬 후
                    delay = 3
                elif i == 1:  # 두 번째 씬 후
                    delay = 5
                else:  # 그 이후
                    delay = 15
                print(f"\n⏳ 다음 씬까지 {delay}초 대기 중 (Whisk 처리 시간 확보)...", flush=True)
                time.sleep(delay)

        print(f"\n{'='*80}", flush=True)
        print("✅ 모든 프롬프트 입력 완료!", flush=True)
        print(f"{ '='*80}", flush=True)

        # === 이미지 생성 대기 ===
        print("\n" + "="*80, flush=True)
        print("🕐 이미지 생성 대기", flush=True)
        print("="*80, flush=True)

        # 씬 개수에 비례한 타임아웃 설정 (씬당 90초 - Whisk는 생성이 느림)
        max_wait_time = max(120, len(scenes) * 90)  # 최소 120초
        print(f"⏳ 이미지 생성 중... (최대 {max_wait_time}초, 씬 {len(scenes)}개)", flush=True)

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

        for i in range(max_wait_time):
            result = driver.execute_script("""
                const text = document.body.innerText;
                const imgs = Array.from(document.querySelectorAll('img'));

                // Whisk 결과 이미지 필터링: blob URL이면서 충분히 큰 이미지
                const whiskImgs = imgs.filter(img => {
                    const src = img.src || '';
                    // blob URL 또는 http URL
                    if (!src.startsWith('blob:') && !src.startsWith('http')) return false;
                    // data URL 제외
                    if (src.startsWith('data:')) return false;
                    // 충분히 큰 이미지 (natural 크기 또는 offset 크기)
                    const hasSize = (img.naturalWidth > 100 && img.naturalHeight > 100) ||
                                   (img.offsetWidth > 100 && img.offsetHeight > 100);
                    return hasSize;
                });

                const allImgs = imgs.map(img => ({
                    src: img.src.substring(0, 50),
                    width: img.offsetWidth,
                    height: img.offsetHeight,
                    naturalWidth: img.naturalWidth,
                    naturalHeight: img.naturalHeight
                }));

                return {
                    generating: text.includes('Generating') || text.includes('생성 중') || text.includes('Loading') || text.includes('처리'),
                    imageCount: whiskImgs.length,
                    allImagesCount: imgs.length,
                    sampleImages: allImgs.slice(0, 5)
                };
            """)

            # 모든 씬의 이미지가 생성될 때까지 대기
            # Whisk는 씬당 여러 배리에이션을 생성할 수 있으므로, 최소 씬 개수만큼만 확인
            expected_count = len(scenes)
            if result['imageCount'] >= expected_count:
                # Generating 상태가 아니면 완료
                if not result['generating']:
                    print(f"✅ 생성 완료! ({i+1}초) - 이미지 {result['imageCount']}/{expected_count}개 발견", flush=True)
                    break
                else:
                    # 이미지는 있지만 아직 생성 중
                    if i % 20 == 0 and i > 0:
                        print(f"   생성 진행 중... ({i}초) - 이미지 {result['imageCount']}개 발견, 추가 생성 대기 중", flush=True)
            elif i >= max_wait_time - 1:
                # 타임아웃 (현재까지 생성된 만큼만 사용)
                print(f"⚠️ 타임아웃 ({i+1}초/{max_wait_time}초) - 이미지 {result['imageCount']}/{expected_count}개 발견", flush=True)
                if result['imageCount'] < expected_count:
                    print(f"⚠️ 경고: {expected_count - result['imageCount']}개 이미지가 생성되지 않았습니다!", flush=True)
                    print(f"   샘플 이미지 (최대 5개): {result['sampleImages']}", flush=True)
                break

            if i % 15 == 0 and i > 0:
                print(f"   대기 중... ({i}초) - Whisk 이미지: {result['imageCount']}개, 전체: {result['allImagesCount']}개", flush=True)
                if i == 15:
                    print(f"   샘플 (최대 5개): {result['sampleImages']}", flush=True)
            time.sleep(1)

        time.sleep(5)

        # === 이미지 다운로드 (디버깅 강화) ===
        print("\n" + "="*80, flush=True)
        print("🔍 Whisk 다운로드 디버깅 시작", flush=True)
        print("="*80, flush=True)

        # 스크린샷 저장
        try:
            screenshot_path = os.path.join(os.path.dirname(os.path.abspath(scenes_json_file)), 'whisk_debug.png')
            driver.save_screenshot(screenshot_path)
            print(f"📸 스크린샷 저장: {screenshot_path}", flush=True)
        except Exception as e:
            print(f"⚠️ 스크린샷 저장 실패: {e}", flush=True)

        # 출력 폴더 확인 (이미 앞에서 정의됨)
        print(f"📁 출력 폴더: {output_folder}", flush=True)

        # 기존 이미지/영상 파일을 backup 폴더로 이동
        backup_folder = os.path.join(output_folder, 'backup')
        backup_files = []

        # 백업 대상: 이미지 파일 (scene_*.jpg, scene_*.jpeg, scene_*.png, scene_*.webp)
        # 백업 대상: 영상 파일 (*.mp4, *.avi, *.mov)
        backup_patterns = [
            'scene_*.jpg', 'scene_*.jpeg', 'scene_*.png', 'scene_*.webp',
            '*.mp4', '*.avi', '*.mov'
        ]

        for pattern in backup_patterns:
            files = glob.glob(os.path.join(output_folder, pattern))
            backup_files.extend(files)

        if backup_files:
            os.makedirs(backup_folder, exist_ok=True)
            print(f"\n📦 기존 파일 백업 중... ({len(backup_files)}개)", flush=True)
            import shutil
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

            for file_path in backup_files:
                filename = os.path.basename(file_path)
                # 타임스탬프 추가하여 백업
                name, ext = os.path.splitext(filename)
                backup_filename = f"{name}_{timestamp}{ext}"
                backup_path = os.path.join(backup_folder, backup_filename)

                try:
                    shutil.move(file_path, backup_path)
                    print(f"   ✅ {filename} → backup/{backup_filename}", flush=True)
                except Exception as e:
                    print(f"   ⚠️ {filename} 백업 실패: {e}", flush=True)

            print(f"✅ 백업 완료: {backup_folder}\n", flush=True)
        else:
            print("ℹ️ 백업할 기존 파일 없음\n", flush=True)
        
        # ✅ 이미지 수집은 이미 각 씬마다 수행됨 (라인 1533-1618)
        # 여기서는 추가 정보만 출력
        print(f"\n📋 모든 씬의 이미지 수집 완료", flush=True)

        print(f"\n{'='*80}", flush=True)
        print("🎉 전체 워크플로우 완료!", flush=True)
        print(f"{ '='*80}", flush=True)

        return 0

    except Exception as e:
        print(f"❌ 오류 발생: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # 임시 파일 정리
        try:
            if 'product_thumbnail_path' in locals() and product_thumbnail_path and os.path.exists(product_thumbnail_path):
                os.remove(product_thumbnail_path)
                print(f"🗑️ 임시 썸네일 파일 삭제: {product_thumbnail_path}", flush=True)
        except Exception as e:
            print(f"⚠️ 임시 파일 삭제 실패: {e}", flush=True)

        # NOTE: .crawl_complete 파일 대신 queue_tasks DB 상태 업데이트로 대체됨
        # 상태 업데이트는 main() 종료 후 __main__에서 처리

        if driver:
            print("\n✅ 작업 완료. 브라우저를 닫습니다.", flush=True)
            driver.quit()

def update_queue_task_status(queue_db_path, task_id, status, error=None):
    """queue_tasks 테이블의 작업 상태를 업데이트합니다."""
    if not queue_db_path or not task_id:
        print(f"⚠️ queue_db_path 또는 task_id가 없어 상태 업데이트 생략", flush=True)
        return False

    try:
        import sqlite3
        import datetime

        conn = sqlite3.connect(queue_db_path)
        cursor = conn.cursor()

        if status == 'completed':
            cursor.execute("""
                UPDATE queue_tasks
                SET status = ?, completed_at = ?
                WHERE id = ?
            """, (status, datetime.datetime.now().isoformat(), task_id))
        elif status == 'failed':
            cursor.execute("""
                UPDATE queue_tasks
                SET status = ?, error = ?, completed_at = ?
                WHERE id = ?
            """, (status, error or 'Unknown error', datetime.datetime.now().isoformat(), task_id))
        else:
            cursor.execute("""
                UPDATE queue_tasks
                SET status = ?
                WHERE id = ?
            """, (status, task_id))

        # 락 해제
        cursor.execute("""
            UPDATE queue_locks
            SET locked_by = NULL, locked_at = NULL
            WHERE task_type = 'image'
        """)

        conn.commit()
        conn.close()

        print(f"✅ 큐 작업 상태 업데이트: {task_id} → {status}", flush=True)
        return True
    except Exception as e:
        print(f"❌ 큐 상태 업데이트 실패: {e}", flush=True)
        return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='이미지 크롤링 자동화')
    parser.add_argument('scenes_file', help='씬 데이터 JSON 파일')
    parser.add_argument('--use-imagefx', action='store_true', help='ImageFX로 첫 이미지 생성')
    parser.add_argument('--output-dir', help='이미지를 저장할 기본 디렉토리 (지정하지 않으면 scenes_file 경로 기준)')
    parser.add_argument('--queue-task-id', help='큐 작업 ID (완료 시 상태 업데이트용)')
    parser.add_argument('--queue-db-path', help='큐 DB 경로')

    args = parser.parse_args()
    print(f"--- ARGS: {args} ---", flush=True)

    exit_code = main(args.scenes_file, use_imagefx=args.use_imagefx, output_dir=args.output_dir)

    # 큐 상태 업데이트
    if args.queue_task_id and args.queue_db_path:
        if exit_code == 0:
            update_queue_task_status(args.queue_db_path, args.queue_task_id, 'completed')
        else:
            update_queue_task_status(args.queue_db_path, args.queue_task_id, 'failed', f'Exit code: {exit_code}')

    sys.exit(exit_code)