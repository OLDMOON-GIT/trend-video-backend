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
import pyautogui

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

    개선된 감지 로직:
    1. 더 많은 정책 위반 패턴 지원 (한글/영문)
    2. 일반적인 에러 메시지도 감지
    3. 전체 페이지 텍스트에서도 검색 (UI 요소 외)

    Returns:
        dict: {
            'violation_detected': bool,
            'message': str or None,
            'type': str or None ('policy', 'safety', 'content', etc.)
        }
    """
    try:
        result = driver.execute_script("""
            // 🔴 1단계: 에러/경고 UI 요소 찾기
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
                'p[class*="error"]',
                // Whisk/ImageFX 특정 요소
                '[class*="snackbar"]',
                '[class*="toast"]',
                '[class*="notification"]',
                '[class*="banner"]'
            ];

            let errorElements = [];
            for (const selector of errorSelectors) {
                const elements = Array.from(document.querySelectorAll(selector));
                errorElements = errorElements.concat(elements);
            }

            // 추가: 에러 메시지 같은 텍스트 길이를 가진 요소들도 검사
            const allDivs = Array.from(document.querySelectorAll('div, span, p'));
            for (const elem of allDivs) {
                const text = elem.textContent || '';
                // 길이가 15~500자 정도의 텍스트만 에러 메시지 후보로 간주 (범위 확장)
                if (text.length > 15 && text.length < 500) {
                    errorElements.push(elem);
                }
            }

            // 🔴 2단계: 정책 위반 패턴 정의 (확장됨)
            const specificViolationPatterns = [
                // === 한글 정책 위반 메시지 ===
                // 구체적인 문구
                '유명인.*동영상.*생성.*Google.*정책',
                '유명인.*Google.*정책.*위반',
                'Google.*정책.*위반',
                '이 프롬프트는.*정책을 위반',
                '정책을 위반할 가능성',
                '다른 프롬프트를.*사용해 보거나',
                '정책.*위반',
                '위반.*정책',

                // 일반적인 에러 메시지 (한글)
                '이미지를 생성할 수 없',
                '생성할 수 없습니다',
                '생성에 실패',
                '요청을 처리할 수 없',
                '처리할 수 없습니다',
                '유해한 콘텐츠',
                '부적절한 콘텐츠',
                '안전하지 않은',
                '문제가 발생',
                '다시 시도해',
                '콘텐츠.*생성.*불가',
                '이미지.*생성.*불가',
                '프롬프트를.*수정',
                '다른.*프롬프트',

                // === 영문 정책 위반 메시지 ===
                'celebrity.*video.*google.*policy',
                'violates.*google.*policy',
                'google.*policy.*violation',
                'this prompt.*violates.*policy',
                'may violate.*policy',
                'policy violation',
                'violates.*policy',

                // 일반적인 에러 메시지 (영문)
                'unable to generate',
                'cannot generate',
                'can\\'t generate',
                'failed to generate',
                'generation failed',
                'could not create',
                'cannot create',
                'unsafe content',
                'harmful content',
                'inappropriate content',
                'try a different prompt',
                'modify your prompt',
                'something went wrong',
                'error occurred',
                'request failed',
                'content policy',
                'safety filter',
                'blocked by',
                'not allowed'
            ];

            let violationDetected = false;
            let errorMessage = '';
            let matchedPatterns = [];
            let violationType = null;

            // 에러 요소들 중에서 패턴 검색
            for (const elem of errorElements) {
                const text = elem.textContent || '';
                const lowerText = text.toLowerCase();

                for (const pattern of specificViolationPatterns) {
                    try {
                        const regex = new RegExp(pattern, 'i');
                        if (regex.test(lowerText) || regex.test(text)) {
                            violationDetected = true;
                            matchedPatterns.push(pattern);
                            errorMessage = text.trim();

                            // 위반 유형 분류
                            if (pattern.includes('policy') || pattern.includes('정책')) {
                                violationType = 'policy';
                            } else if (pattern.includes('unsafe') || pattern.includes('harmful') || pattern.includes('유해')) {
                                violationType = 'safety';
                            } else {
                                violationType = 'error';
                            }
                            break;
                        }
                    } catch (e) {
                        // 정규식 오류 무시
                    }
                }

                if (violationDetected) {
                    break;
                }
            }

            // 🔴 3단계: 전체 페이지 텍스트에서도 검색 (백업)
            if (!violationDetected) {
                const bodyText = document.body.innerText || '';
                const criticalPatterns = [
                    '정책.*위반',
                    'policy.*violation',
                    '생성할 수 없',
                    'unable to generate',
                    'cannot generate',
                    '이미지를 생성할 수 없',
                    'failed to generate'
                ];

                for (const pattern of criticalPatterns) {
                    try {
                        const regex = new RegExp(pattern, 'i');
                        if (regex.test(bodyText)) {
                            violationDetected = true;
                            matchedPatterns.push(pattern + ' (page-level)');
                            errorMessage = '페이지에서 정책 위반/에러 메시지 감지됨';
                            violationType = 'page-level';
                            break;
                        }
                    } catch (e) {}
                }
            }

            if (violationDetected) {
                return {
                    violation_detected: true,
                    matched_keywords: matchedPatterns,
                    message: errorMessage || '정책 위반 메시지 감지됨',
                    match_count: matchedPatterns.length,
                    type: violationType
                };
            }

            return {
                violation_detected: false,
                matched_keywords: [],
                message: null,
                match_count: 0,
                type: null
            };
        """)

        return result
    except Exception as e:
        print(f"⚠️ 정책 위반 감지 실패: {e}", flush=True)
        return {
            'violation_detected': False,
            'message': None,
            'match_count': 0,
            'type': None
        }

def sanitize_prompt_for_google(prompt, aggressive=False):
    """
    Google 이미지 정책 위반을 방지하기 위해 프롬프트를 안전하게 변환합니다.

    개선된 전략:
    1. 단순 삭제 대신 안전한 동의어로 대체
    2. 안전한 컨텍스트 추가로 의도 명확화
    3. 상품 중심의 객관적 묘사로 전환
    """
    if not prompt or not isinstance(prompt, str):
        return prompt

    sanitized = prompt

    # 1. 위험 키워드를 안전한 대체어로 변경 (삭제하지 않고 대체)
    safe_replacements = {
        # 인물/유명인 관련
        r'\bKorean\s+person\b': 'model',
        r'\bKorean\s+man\b': 'male model',
        r'\bKorean\s+woman\b': 'female model',
        r'\bAsian\s+person\b': 'model',
        r'\bEast\s+Asian\b': 'modern',
        r'\bcelebrity\b': 'professional model',
        r'\bfamous\s+person\b': 'professional',
        r'\bpolitician\b': 'business person',
        r'\bactor\b': 'model',
        r'\bactress\b': 'model',
        r'\bsinger\b': 'performer',
        r'\bathlete\b': 'sports person',
        r'유명인': '모델',

        # 신체/의료 관련
        r'\bskin\s+tone\b': 'appearance',
        r'\bface\b': 'expression',
        r'\bfacial\s+features\b': 'appearance',
        r'\bbody\b': 'figure',
        r'\bskinny\b': 'slim',
        r'\bfat\b': 'full-figured',
        r'\bwrinkle\b': 'texture',
        r'\baging\b': 'mature',
        r'\bdisease\b': 'condition',
        r'\bmedical\b': 'health-related',
        r'\btreatment\b': 'care',
        r'\bpain\b': 'discomfort',

        # 효과/과장 표현
        r'\bamazing\b': 'quality',
        r'\bmiraculous\b': 'effective',
        r'\bshocking\b': 'notable',
        r'\bincredible\b': 'impressive',
        r'\binstant\b': 'quick',
        r'\bguaranteed\b': 'reliable',
        r'\b100%\b': 'high quality',
        r'\bperfect\b': 'excellent',

        # 다이어트/건강 관련
        r'\bweight\s+loss\b': 'wellness',
        r'\bdiet\b': 'nutrition',
        r'\blose\s+weight\b': 'healthy lifestyle',
        r'\bburn\s+fat\b': 'active lifestyle',
        r'\bcalories\b': 'energy',
        r'다이어트': '웰빙',
        r'살빠지는': '건강한',
        r'뱃살': '복부',

        # 브랜드명 (추가)
        r'\bnike\b': 'sports brand',
        r'\badidas\b': 'athletic brand',
        r'\bapple\b': 'tech brand',
        r'\bsamsung\b': 'electronics brand',
        r'\bcoca-cola\b': 'beverage',
        r'\bstarbucks\b': 'coffee shop',
    }

    for pattern, replacement in safe_replacements.items():
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    # 2. 문맥상 위험한 구문을 안전한 표현으로 전환
    phrase_replacements = {
        r'before\s+and\s+after': 'product showcase',
        r'비포\s*애프터': '제품 소개',
        r'dramatic\s+change': 'product benefits',
        r'life-changing': 'beneficial',
        r'must-have': 'recommended',
        r'exclusive\s+offer': 'special product',
        r'limited\s+time': 'available now',
    }

    for pattern, replacement in phrase_replacements.items():
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    # 3. 안전한 컨텍스트 래퍼 추가
    if aggressive:
        # 시작 부분에 안전한 컨텍스트 추가
        safe_context_prefix = "Product advertisement image, professional photography, commercial setting, "

        # 끝 부분에 안전 지시어 추가
        safe_context_suffix = " Focus on product design and features, safe for all audiences, no people prominently featured."

        # 이미 안전 컨텍스트가 없으면 추가
        if not any(keyword in sanitized.lower() for keyword in ['advertisement', 'commercial', 'product showcase']):
            sanitized = safe_context_prefix + sanitized

        if not any(keyword in sanitized.lower() for keyword in ['safe for all', 'family friendly']):
            sanitized = sanitized + safe_context_suffix

    # 4. 상품 중심 표현 강화 (사람보다 제품에 초점)
    product_focus_patterns = {
        r'person\s+holding': 'product displayed with',
        r'person\s+using': 'product in use',
        r'person\s+wearing': 'product being worn',
        r'person\s+eating': 'product being consumed',
        r'person\s+drinking': 'beverage being enjoyed',
    }

    for pattern, replacement in product_focus_patterns.items():
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    # 5. 최종 정리
    # 중복 공백 제거
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()

    # 중복 단어 제거
    words = sanitized.split()
    seen = set()
    result = []
    for word in words:
        word_lower = word.lower()
        if word_lower not in seen or word_lower in ['the', 'a', 'an', 'and', 'or', 'with', 'in', 'on', 'at']:
            seen.add(word_lower)
            result.append(word)
    sanitized = ' '.join(result)

    # 길이 제한 (Google 제한에 맞춤)
    max_length = 400
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rsplit(' ', 1)[0]

    # 변경사항 로그
    if sanitized != prompt:
        print(f"🔒 프롬프트 안전화 적용 (aggressive={aggressive})", flush=True)
        changes = []
        if 'Korean person' in prompt and 'Korean person' not in sanitized:
            changes.append("인물 표현 중립화")
        if 'diet' in prompt.lower() and 'diet' not in sanitized.lower():
            changes.append("건강 표현 순화")
        if 'advertisement' in sanitized and 'advertisement' not in prompt:
            changes.append("안전 컨텍스트 추가")
        if changes:
            print(f"   변경사항: {', '.join(changes)}", flush=True)
        print(f"   글자수: {len(prompt)} → {len(sanitized)}", flush=True)

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

def generate_image_with_imagefx(driver, prompt, aspect_ratio=None):
    """ImageFX로 이미지 생성 및 다운로드"""
    print("\n" + "="*80, flush=True)
    print("1️⃣ ImageFX - 첫 이미지 생성", flush=True)
    print("="*80, flush=True)
    print(f"📝 프롬프트 길이: {len(prompt)}자", flush=True)
    print(f"📝 프롬프트 내용: {prompt}", flush=True)
    if aspect_ratio:
        print(f"📐 목표 비율: {aspect_ratio}", flush=True)
    print("="*80, flush=True)

    # 창 크기 최대화 (입력창이 보이도록)
    try:
        driver.maximize_window()
        print("📐 창 크기 최대화 완료", flush=True)
    except:
        driver.set_window_size(1920, 1080)
        print("📐 창 크기 1920x1080 설정", flush=True)

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
    print("🖱️ 입력창 찾아서 활성화 시도...", flush=True)

    # 비율 설정이 필요한 경우 가로/세로 모드 선택
    if aspect_ratio:
        print(f"⚙️ 비율 설정: {aspect_ratio}", flush=True)

        # Step 1: 가로/세로 모드 버튼 찾기 및 클릭
        mode_button_clicked = driver.execute_script("""
            // 가로/세로 모드 버튼 찾기 (보통 아이콘이나 텍스트로 표시)
            const buttons = Array.from(document.querySelectorAll('button, [role="button"]'));

            for (const btn of buttons) {
                const text = (btn.innerText || btn.textContent || '').trim().toLowerCase();
                const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();

                // 가로/세로, aspect ratio, orientation 등의 키워드 찾기
                if (text.includes('가로') || text.includes('세로') ||
                    text.includes('aspect') || text.includes('ratio') ||
                    text.includes('orientation') || text.includes('mode') ||
                    ariaLabel.includes('aspect') || ariaLabel.includes('ratio')) {

                    btn.click();
                    console.log('Clicked mode button:', text || ariaLabel);
                    return {success: true, text: text, ariaLabel: ariaLabel};
                }

                // 아이콘 기반 버튼 (보통 crop 아이콘)
                const icon = btn.querySelector('svg, i, span[class*="icon"]');
                if (icon) {
                    const classes = btn.className + ' ' + (icon.className || '');
                    if (classes.includes('crop') || classes.includes('aspect') ||
                        classes.includes('ratio') || classes.includes('orientation')) {
                        btn.click();
                        console.log('Clicked icon button');
                        return {success: true, type: 'icon'};
                    }
                }
            }

            return {success: false};
        """)

        if mode_button_clicked.get('success'):
            print(f"✅ 가로/세로 모드 버튼 클릭", flush=True)
            time.sleep(1)

            # Step 2: 셀렉트박스에서 비율 선택
            ratio_text = "세로 모드(9:16)" if aspect_ratio == "9:16" else "가로 모드(16:9)"
            ratio_value = aspect_ratio  # 9:16 또는 16:9

            ratio_selected = driver.execute_script("""
                const targetRatio = arguments[0];
                const ratioValue = arguments[1];

                // 드롭다운 옵션들 찾기
                const options = Array.from(document.querySelectorAll(
                    '[role="option"], [role="menuitem"], option, li[role="option"], button[role="option"]'
                ));

                console.log('Found options:', options.length);

                for (const opt of options) {
                    const text = (opt.innerText || opt.textContent || '').trim();
                    const value = opt.value || opt.getAttribute('data-value') || '';

                    console.log('Checking option:', text, 'value:', value);

                    // 9:16, 16:9 또는 세로/가로 텍스트 매칭
                    if (text.includes(ratioValue) || value.includes(ratioValue) ||
                        (ratioValue === '9:16' && (text.includes('세로') || text.includes('Portrait') || text.includes('Vertical'))) ||
                        (ratioValue === '16:9' && (text.includes('가로') || text.includes('Landscape') || text.includes('Horizontal')))) {

                        opt.click();
                        console.log('Selected ratio:', text);
                        return {success: true, text: text};
                    }
                }

                // 못 찾으면 모든 옵션 텍스트 반환 (디버깅용)
                const allTexts = options.slice(0, 10).map(o => (o.innerText || o.textContent || '').trim());
                return {success: false, options: allTexts};
            """, ratio_text, ratio_value)

            if ratio_selected.get('success'):
                print(f"✅ 비율 {aspect_ratio} 선택 완료: {ratio_selected.get('text')}", flush=True)
            else:
                print(f"⚠️ 비율 선택 실패. 발견된 옵션들: {ratio_selected.get('options', [])}", flush=True)
                print("   기본 비율로 진행합니다.", flush=True)
        else:
            print("⚠️ 가로/세로 모드 버튼을 찾지 못했습니다. 기본 비율로 진행합니다.", flush=True)

        time.sleep(1)

    # "입력" 탭 클릭 (프롬프트 입력을 위해)
    driver.execute_script("""
        const tabs = document.querySelectorAll('button, [role="tab"]');
        for (const tab of tabs) {
            const text = (tab.innerText || '').trim();
            if (text === '입력' || text === 'Input') {
                tab.click();
                console.log('Clicked 입력 tab');
                break;
            }
        }
    """)
    time.sleep(1)

    # 입력창(contenteditable div) 찾아서 클릭 및 포커스
    input_focused = driver.execute_script("""
        // contenteditable 요소 찾기
        const editables = document.querySelectorAll('[contenteditable="true"]');
        let targetInput = null;

        for (const el of editables) {
            // 보이는 요소만 선택
            if (el.offsetParent !== null && el.offsetWidth > 100) {
                targetInput = el;
                break;
            }
        }

        if (targetInput) {
            // 포커스 및 전체 선택
            targetInput.focus();
            targetInput.click();

            // 전체 선택 (기존 내용 대체용)
            const selection = window.getSelection();
            const range = document.createRange();
            range.selectNodeContents(targetInput);
            selection.removeAllRanges();
            selection.addRange(range);

            return {success: true, tag: targetInput.tagName, classes: targetInput.className, hadContent: targetInput.innerText.length > 0};
        }

        // fallback: 일반 텍스트 입력창
        const textareas = document.querySelectorAll('textarea, input[type="text"]');
        for (const el of textareas) {
            if (el.offsetParent !== null) {
                el.focus();
                el.select();
                return {success: true, tag: el.tagName, type: 'fallback'};
            }
        }

        return {success: false};
    """)

    if input_focused and input_focused.get('success'):
        print(f"✅ 입력창 포커스 완료: {input_focused}", flush=True)
    else:
        print("⚠️ 입력창을 찾지 못했습니다. 클릭으로 대체...", flush=True)
        driver.execute_script("document.body.click();")

    time.sleep(1)

    # 클립보드를 이용한 직접 입력 시도
    try:
        print("📋 프롬프트를 클립보드에 복사하고 붙여넣기 시도...", flush=True)
        pyperclip.copy(prompt)
        time.sleep(0.5)

        # Ctrl+V 붙여넣기
        actions = ActionChains(driver)
        actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
        time.sleep(1)
        print("✅ Ctrl+V 붙여넣기 완료", flush=True)

        # 붙여넣기 확인
        paste_check = driver.execute_script("""
            const editables = document.querySelectorAll('[contenteditable="true"]');
            for (const el of editables) {
                if (el.offsetParent !== null && el.innerText) {
                    return {success: true, length: el.innerText.length, preview: el.innerText.substring(0, 100)};
                }
            }
            return {success: false};
        """)

        # 프롬프트 길이 확인하고 부족하면 재입력
        expected_length = len(prompt)
        actual_length = paste_check.get('length', 0) if paste_check else 0

        if actual_length < expected_length * 0.9:  # 90% 미만이면 재입력
            print(f"⚠️ 프롬프트 입력 부족 (예상: {expected_length}자, 실제: {actual_length}자)", flush=True)
            print("   JavaScript로 직접 입력 시도...", flush=True)

            # 기존 텍스트 삭제하고 다시 입력
            driver.execute_script("""
                const prompt = arguments[0];
                const editables = document.querySelectorAll('[contenteditable="true"]');

                for (const el of editables) {
                    if (el.offsetParent !== null && el.offsetWidth > 100) {
                        // 기존 내용 완전 삭제
                        el.innerText = '';
                        el.innerHTML = '';

                        // 포커스
                        el.focus();
                        el.click();

                        // 새 텍스트 설정
                        el.innerText = prompt;

                        // 여러 이벤트 발생
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new KeyboardEvent('keyup', { key: ' ', bubbles: true }));

                        console.log('Prompt set directly:', prompt.length, 'chars');
                        return {success: true, length: el.innerText.length};
                    }
                }
                return {success: false};
            """, prompt)
            time.sleep(1)

            # 재확인
            final_check = driver.execute_script("""
                const editables = document.querySelectorAll('[contenteditable="true"]');
                for (const el of editables) {
                    if (el.offsetParent !== null && el.innerText) {
                        return {length: el.innerText.length};
                    }
                }
                return {length: 0};
            """)

            print(f"✅ JavaScript 직접 입력 완료: {final_check.get('length')}자", flush=True)
        else:
            print(f"✅ 프롬프트 입력 확인: {actual_length}자", flush=True)

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
    # 생성된 4개 이미지 중 랜덤으로 1개 선택하여 다운로드
    print("\n📥 이미지 다운로드 시도 중 (4개 중 랜덤 선택)...", flush=True)
    download_success = False

    # 랜덤으로 이미지 인덱스 선택 (0~3)
    import random
    selected_index = random.randint(0, 3)
    print(f"   선택된 이미지 번호: {selected_index + 1}/4", flush=True)

    # 방법 1: 선택된 인덱스의 다운로드 버튼 찾기
    try:
        btn_info = driver.execute_script("""
            const selectedIndex = arguments[0];

            // 모든 다운로드 버튼 찾기
            const selectors = [
                'button[aria-label*="Download"]',
                'button[aria-label*="다운로드"]',
                '[aria-label*="Download"]',
                '[aria-label*="download"]',
                'button[title*="Download"]',
                'button[title*="다운로드"]'
            ];

            let downloadButtons = [];

            // 각 셀렉터로 버튼 수집
            for (const sel of selectors) {
                const btns = document.querySelectorAll(sel);
                btns.forEach(btn => {
                    if (btn.offsetParent !== null && !downloadButtons.includes(btn)) {
                        downloadButtons.push(btn);
                    }
                });
            }

            // 텍스트 기반으로도 찾기
            const allButtons = Array.from(document.querySelectorAll('button'));
            allButtons.forEach(btn => {
                const text = (btn.textContent || '').toLowerCase();
                const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
                if ((text.includes('download') || text.includes('다운로드') ||
                     ariaLabel.includes('download') || ariaLabel.includes('다운로드')) &&
                    btn.offsetParent !== null && !downloadButtons.includes(btn)) {
                    downloadButtons.push(btn);
                }
            });

            console.log('Found download buttons:', downloadButtons.length);

            // 선택된 인덱스의 버튼 클릭
            if (downloadButtons.length > selectedIndex) {
                downloadButtons[selectedIndex].click();
                return {success: true, index: selectedIndex, total: downloadButtons.length};
            } else if (downloadButtons.length > 0) {
                // 인덱스가 범위를 벗어나면 랜덤 선택
                const randomIndex = Math.floor(Math.random() * downloadButtons.length);
                downloadButtons[randomIndex].click();
                return {success: true, index: randomIndex, total: downloadButtons.length, random: true};
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

        # 🔴 ImageFX 종료 전 열려있는 모달/팝업 닫기
        try:
            driver.execute_script("""
                // ESC 키로 모달 닫기
                document.body.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', keyCode: 27, bubbles: true}));

                // 닫기 버튼 클릭
                const closeSelectors = [
                    'button[aria-label*="close"]', 'button[aria-label*="닫기"]',
                    '[class*="close-button"]', '[class*="modal-close"]'
                ];
                closeSelectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(btn => {
                        try { btn.click(); } catch(e) {}
                    });
                });

                // 오버레이 클릭
                document.querySelectorAll('.cdk-overlay-backdrop, .mdc-dialog__scrim').forEach(el => {
                    try { el.click(); } catch(e) {}
                });
            """)
            print("🔄 ImageFX 종료 전 모달 닫기 완료", flush=True)
        except:
            pass

        return latest_file
    else:
        raise Exception("❌ 다운로드된 이미지 파일을 찾을 수 없습니다 - Downloads 폴더에 새 파일이 없습니다")

def upload_image_to_whisk(driver, image_path, aspect_ratio=None, box_index=0, box_name="피사체"):
    """
    Whisk에 이미지 업로드

    Args:
        driver: 웹드라이버
        image_path: 업로드할 이미지 경로
        aspect_ratio: 비율 설정 (16:9 또는 9:16)
        box_index: 업로드할 박스 인덱스 (0: 사람/캐릭터, 1: 상품/장소, 2: 스타일)
        box_name: 박스 이름 (로그용)
    """
    print("\n" + "="*80, flush=True)
    print(f"2️⃣ Whisk - {box_name} 이미지 업로드 (박스 {box_index + 1})", flush=True)
    print("="*80, flush=True)

    # 🔴 Whisk로 이동 전 열려있는 모달/팝업 닫기
    try:
        closed_count = driver.execute_script("""
            let closedCount = 0;

            // ESC 키로 모달 닫기 시도
            document.body.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', keyCode: 27, bubbles: true}));

            // 닫기 버튼 클릭
            const closeSelectors = [
                'button[aria-label*="close"]', 'button[aria-label*="Close"]',
                'button[aria-label*="닫기"]', 'button[aria-label*="취소"]',
                '[class*="close-button"]', '[class*="closeButton"]',
                '[class*="dialog-close"]', '[class*="modal-close"]',
                'mat-dialog-container button[mat-icon-button]',
                '.mdc-dialog button.mdc-icon-button'
            ];

            for (const sel of closeSelectors) {
                const btns = document.querySelectorAll(sel);
                btns.forEach(btn => {
                    try { btn.click(); closedCount++; } catch(e) {}
                });
            }

            // 오버레이/백드롭 클릭
            const overlaySelectors = [
                '.cdk-overlay-backdrop', '.mdc-dialog__scrim',
                '[class*="overlay"]', '[class*="backdrop"]'
            ];

            for (const sel of overlaySelectors) {
                const overlays = document.querySelectorAll(sel);
                overlays.forEach(overlay => {
                    try { overlay.click(); closedCount++; } catch(e) {}
                });
            }

            return closedCount;
        """)
        if closed_count > 0:
            print(f"🔄 Whisk 이동 전 {closed_count}개 모달/팝업 닫기 시도", flush=True)
            time.sleep(0.5)
    except Exception as e:
        print(f"⚠️ 모달 닫기 중 오류 (무시): {e}", flush=True)

    driver.get('https://labs.google/fx/ko/tools/whisk/project')
    print("⏳ Whisk 페이지 로딩...", flush=True)
    time.sleep(5)

    # "도구 열기" 버튼이 있으면 클릭
    tool_open_clicked = driver.execute_script("""
        const buttons = Array.from(document.querySelectorAll('button'));
        for (const btn of buttons) {
            const text = (btn.innerText || btn.textContent || '').trim();
            if (text.includes('도구 열기') || text.includes('도구') || text.includes('열기') ||
                text.includes('Open tool') || text.includes('Open')) {
                btn.click();
                console.log('Clicked 도구 열기 button');
                return {success: true, text: text};
            }
        }
        return {success: false};
    """)

    if tool_open_clicked.get('success'):
        print(f"✅ 도구 열기 버튼 클릭: {tool_open_clicked.get('text')}", flush=True)
        time.sleep(3)

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

    # 먼저 메인 화면의 "이미지 추가" 버튼 클릭
    print("🔍 이미지 추가 버튼 찾는 중...", flush=True)
    add_image_clicked = driver.execute_script("""
        // "이미지 추가" 버튼 찾기
        const buttons = Array.from(document.querySelectorAll('button'));

        for (const btn of buttons) {
            const text = (btn.innerText || btn.textContent || '').trim();
            if (text.includes('이미지 추가') || text.includes('이미지')) {
                btn.click();
                console.log('Clicked 이미지 추가 button');
                return {success: true, text: text};
            }
        }

        // aria-label로도 찾기
        for (const btn of buttons) {
            const ariaLabel = btn.getAttribute('aria-label') || '';
            if (ariaLabel.includes('이미지') || ariaLabel.includes('추가')) {
                btn.click();
                return {success: true, ariaLabel: ariaLabel};
            }
        }

        return {success: false};
    """)

    if add_image_clicked.get('success'):
        print(f"✅ 이미지 추가 버튼 클릭: {add_image_clicked}", flush=True)
        time.sleep(2)  # 메뉴가 열릴 때까지 대기

    # 업로드 박스 영역 찾기 (0: 피사체, 1: 장면, 2: 스타일)
    box_names = ['피사체', '장면', '스타일']
    target_box_name = box_names[box_index] if box_index < len(box_names) else f'박스{box_index}'
    print(f"🔍 {target_box_name} 업로드 영역 찾는 중... (box_index={box_index})", flush=True)

    # 점선 테두리가 있는 업로드 박스를 정확히 찾아서 클릭
    subject_clicked = driver.execute_script("""
        const boxIndex = arguments[0];  // 박스 인덱스 받기 (0: 피사체, 1: 장면, 2: 스타일)
        const boxNames = ['피사체', '장면', '스타일'];

        // 방법 1: 점선 테두리가 있는 업로드 박스 찾기 (가장 정확한 방법)
        const allElements = Array.from(document.querySelectorAll('*'));
        const dashedBoxes = allElements.filter(elem => {
            const style = window.getComputedStyle(elem);
            const rect = elem.getBoundingClientRect();
            // 점선 테두리, 적절한 크기, 왼쪽 사이드바 영역
            return style.borderStyle.includes('dashed') &&
                   rect.width > 100 && rect.width < 300 &&
                   rect.height > 100 && rect.height < 300 &&
                   rect.left < 150;
        });

        console.log('Dashed boxes found:', dashedBoxes.length);

        // top 순서로 정렬 (피사체 → 장면 → 스타일)
        dashedBoxes.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);

        if (dashedBoxes.length > boxIndex) {
            const targetBox = dashedBoxes[boxIndex];
            const rect = targetBox.getBoundingClientRect();
            console.log('Target box rect:', rect.top, rect.left);

            // 해당 박스 내의 "이미지 업로드" 버튼 정확히 찾기
            // (텍스트 입력 버튼이 아닌 이미지 업로드 버튼을 찾아야 함)
            const allButtons = targetBox.querySelectorAll('button');
            let uploadButton = null;

            for (const btn of allButtons) {
                const btnText = btn.textContent || '';
                // "이미지 업로드" 또는 "image" 텍스트가 포함된 버튼 찾기
                if (btnText.includes('이미지 업로드') || btnText.includes('image') ||
                    btnText.toLowerCase().includes('upload')) {
                    uploadButton = btn;
                    console.log('Found image upload button:', btnText);
                    break;
                }
            }

            // "이미지 업로드" 버튼을 못 찾으면 마지막 버튼 사용 (보통 업로드 버튼이 마지막)
            if (!uploadButton && allButtons.length > 0) {
                uploadButton = allButtons[allButtons.length - 1];
                console.log('Using last button as upload button');
            }

            if (uploadButton) {
                const btnRect = uploadButton.getBoundingClientRect();
                uploadButton.click();
                console.log('Clicked upload button in dashed box');
                return {
                    success: true,
                    method: 'dashed-box-button',
                    rect: {left: btnRect.left, top: btnRect.top, width: btnRect.width, height: btnRect.height},
                    boxIndex: boxIndex,
                    boxName: boxNames[boxIndex] || 'unknown',
                    buttonText: uploadButton.textContent.substring(0, 30)
                };
            }

            // 버튼이 없으면 박스 직접 클릭
            targetBox.click();
            return {
                success: true,
                method: 'dashed-box-direct',
                rect: {left: rect.left, top: rect.top, width: rect.width, height: rect.height},
                boxIndex: boxIndex,
                boxName: boxNames[boxIndex] || 'unknown'
            };
        }

        // 방법 2: 박스 이름으로 찾기 (피사체/장면/스타일 텍스트)
        const targetName = boxNames[boxIndex];
        if (targetName) {
            const textElements = Array.from(document.querySelectorAll('div')).filter(elem => {
                const text = elem.textContent || '';
                return text.startsWith(targetName) || text.includes(targetName + 'ifl');
            });

            // top 기준으로 정렬 후 적절한 크기의 요소 찾기
            textElements.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);

            for (const elem of textElements) {
                const rect = elem.getBoundingClientRect();
                if (rect.width > 100 && rect.height > 100) {
                    // 해당 영역 내 업로드 버튼 찾기
                    const btn = elem.querySelector('button');
                    if (btn) {
                        btn.click();
                        return {
                            success: true,
                            method: 'text-element-button',
                            rect: {left: rect.left, top: rect.top, width: rect.width, height: rect.height},
                            boxIndex: boxIndex,
                            boxName: targetName
                        };
                    }
                }
            }
        }

        // 방법 3: 모든 "이미지 업로드" 버튼을 top 순서로 정렬해서 선택
        const uploadButtons = Array.from(document.querySelectorAll('button')).filter(btn => {
            const text = btn.textContent || '';
            const rect = btn.getBoundingClientRect();
            return (text.includes('이미지') || text.includes('업로드')) && rect.left < 150;
        });

        uploadButtons.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
        console.log('Upload buttons found:', uploadButtons.length);

        if (uploadButtons.length > boxIndex) {
            const targetBtn = uploadButtons[boxIndex];
            const rect = targetBtn.getBoundingClientRect();
            targetBtn.click();
            return {
                success: true,
                method: 'upload-button-sorted',
                rect: {left: rect.left, top: rect.top, width: rect.width, height: rect.height},
                boxIndex: boxIndex
            };
        }

        return {success: false, method: 'none', dashedBoxCount: dashedBoxes.length, uploadButtonCount: uploadButtons.length};
    """, box_index)

    if subject_clicked.get('success'):
        clicked_box_name = subject_clicked.get('boxName', target_box_name)
        print(f"✅ {clicked_box_name} 영역 클릭 성공: {subject_clicked.get('method')}", flush=True)
        print(f"   박스 인덱스: {subject_clicked.get('boxIndex')}", flush=True)
        if subject_clicked.get('text'):
            print(f"   텍스트: {subject_clicked.get('text')}", flush=True)
        if subject_clicked.get('rect'):
            print(f"   위치: {subject_clicked.get('rect')}", flush=True)

        # pyautogui를 사용하여 실제 클릭 시도
        rect = subject_clicked.get('rect')
        if rect:
            try:
                # 브라우저 창 활성화
                driver.switch_to.window(driver.current_window_handle)
                time.sleep(1)

                # 피사체 영역 중앙 클릭
                center_x = rect['left'] + rect['width'] / 2
                center_y = rect['top'] + rect['height'] / 2

                print(f"🖱️ pyautogui로 실제 클릭: ({center_x}, {center_y})", flush=True)
                pyautogui.click(center_x, center_y)
                time.sleep(2)

                # 파일 다이얼로그가 열렸으면 ESC로 닫기 (file input 방식 사용)
                print("🔒 파일 다이얼로그 닫기 (ESC) - file input 방식으로 업로드 예정", flush=True)
                pyautogui.press('escape')
                time.sleep(1)

                print("✅ pyautogui 클릭 완료 (file input으로 업로드 진행)", flush=True)
            except Exception as e:
                print(f"⚠️ pyautogui 사용 실패: {e}", flush=True)
                print("   기존 방식으로 계속 진행...", flush=True)
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
        from selenium.webdriver.common.by import By
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

    # 업로드 확인 (최대 15초 대기)
    upload_success = False
    initial_img_count = driver.execute_script("return document.querySelectorAll('img').length;")

    for i in range(15):
        uploaded = driver.execute_script("""
            // 업로드된 이미지 확인
            const imgs = Array.from(document.querySelectorAll('img'));
            const initialCount = arguments[0];

            // 새로 추가된 이미지 찾기
            const newImages = imgs.filter(img => {
                const src = img.src || '';
                // blob URL이나 새로운 이미지
                if (!src.startsWith('blob:') && !src.includes('googleusercontent')) {
                    return false;
                }

                // 크기가 충분히 큰 이미지 (썸네일이 아닌)
                if (img.offsetWidth < 30 || img.offsetHeight < 30) {
                    return false;
                }

                return true;
            });

            return {
                hasImage: imgs.length > initialCount || newImages.length > 0,
                imageCount: imgs.length,
                newImageCount: newImages.length,
                imageSrc: newImages.length > 0 ? newImages[0].src.substring(0, 80) : '',
                imageSize: newImages.length > 0 ? `${newImages[0].offsetWidth}x${newImages[0].offsetHeight}` : ''
            };
        """, initial_img_count)

        if uploaded.get('hasImage') or uploaded.get('newImageCount', 0) > 0:
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
        # 🔴 재시도 시 오버레이/다이얼로그 닫기 (ESC 키)
        try:
            # 오버레이가 있는지 확인하고 닫기
            overlay_closed = driver.execute_script("""
                // 오버레이/다이얼로그 찾기 및 닫기
                const overlays = document.querySelectorAll('[data-state="open"], [class*="overlay"], [class*="modal"], [class*="dialog"]');
                let closed = 0;
                for (const overlay of overlays) {
                    // backdrop-filter가 있거나 pointer-events: auto인 오버레이
                    const style = window.getComputedStyle(overlay);
                    if (style.backdropFilter !== 'none' || style.pointerEvents === 'auto') {
                        // 닫기 버튼 찾기
                        const closeBtn = overlay.querySelector('[aria-label*="close"], [aria-label*="닫기"], button[class*="close"]');
                        if (closeBtn) {
                            closeBtn.click();
                            closed++;
                        } else {
                            // 닫기 버튼이 없으면 오버레이 자체를 클릭 시도
                            overlay.click();
                            closed++;
                        }
                    }
                }
                return closed;
            """)

            if overlay_closed > 0:
                print(f"🔄 오버레이 {overlay_closed}개 닫음", flush=True)
                time.sleep(1)

            # ESC 키로 추가 다이얼로그 닫기
            actions = ActionChains(driver)
            actions.send_keys(Keys.ESCAPE).perform()
            time.sleep(0.5)

        except Exception as e:
            pass  # 오버레이 닫기 실패해도 계속 진행

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
            # 입력창을 못 찾으면 페이지 중앙 근처를 클릭 (URL 창 피하기)
            print("⚠️ 입력창을 찾지 못함, 페이지 하단 클릭 시도", flush=True)
            # 페이지 하단 클릭 (URL 창 피하고 입력 영역 활성화)
            import pyautogui
            screen_width, screen_height = pyautogui.size()
            # 화면 하단 75% 지점 클릭 (URL 창 피하기)
            pyautogui.click(screen_width // 2, int(screen_height * 0.75))
            time.sleep(1)  # 충분한 대기 시간

            # 다시 한번 입력창 찾기 시도
            for selector in selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        # 가시적이고 사용 가능한 요소만 선택
                        if element.is_displayed() and element.is_enabled():
                            input_box = element
                            print(f"✅ 재시도: 입력창 발견: {selector}", flush=True)
                            input_box.click()
                            time.sleep(0.3)
                            break
                    if input_box:
                        break
                except:
                    continue
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
            is_product = False  # 배열 형식에는 category 정보 없음
        elif isinstance(data, dict) and 'scenes' in data:
            scenes = data['scenes']
            # metadata에서 aspect_ratio 및 category 추출
            metadata = data.get('metadata', {})
            aspect_ratio_raw = metadata.get('aspect_ratio', '')
            format_type = metadata.get('format', '')
            category = metadata.get('category', '')  # 카테고리 확인

            # aspect_ratio 정규화: "9:16 (portrait)" -> "9:16", "16:9 horizontal" -> "16:9"
            aspect_ratio = None
            if aspect_ratio_raw:
                if '9:16' in str(aspect_ratio_raw):
                    aspect_ratio = '9:16'
                elif '16:9' in str(aspect_ratio_raw):
                    aspect_ratio = '16:9'

            # format_type에서도 비율 추출 시도: "세로형 9:16" -> 9:16
            if not aspect_ratio and format_type:
                if '9:16' in str(format_type) or 'shortform' in str(format_type).lower() or '세로' in str(format_type):
                    aspect_ratio = '9:16'
                elif '16:9' in str(format_type) or 'longform' in str(format_type).lower() or '가로' in str(format_type):
                    aspect_ratio = '16:9'

            # product_info에서 썸네일 추출 (상품 영상인 경우)
            product_info = data.get('product_info', {})
            product_thumbnail = product_info.get('thumbnail', '')

            # 카테고리가 "상품"이거나 product_info가 있으면 상품으로 판단
            is_product = (category == '상품' or bool(product_info.get('thumbnail')))

            # 최종 기본값 설정 (위에서 결정되지 않은 경우)
            if not aspect_ratio:
                aspect_ratio = '9:16'  # 기본값은 세로형

            print(f"📐 비디오 형식: {format_type or 'unknown'}, 비율: {aspect_ratio}", flush=True)
            print(f"📂 카테고리: {category or 'unknown'}", flush=True)

            if is_product:
                print(f"🛒 상품 비디오 감지됨", flush=True)
                if product_thumbnail:
                    print(f"   썸네일: {product_thumbnail[:80]}...", flush=True)
                else:
                    print(f"   ⚠️ 상품 카테고리지만 썸네일이 없습니다", flush=True)
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

    # 🔴 출력 폴더가 없으면 생성
    if not os.path.exists(output_folder):
        os.makedirs(output_folder, exist_ok=True)
        print(f"📁 출력 폴더 생성: {output_folder}", flush=True)

    driver = None
    try:
        driver = setup_chrome_driver()

        # ImageFX 사용 시 첫 이미지 생성 및 업로드
        if use_imagefx:
            # 백업 처리 (ImageFX+Whisk 모드, 이미지 생성 전에 실행)
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

            # ImageFX로 첫 이미지 생성 (aspect_ratio 전달)
            image_path = generate_image_with_imagefx(driver, first_prompt, aspect_ratio)

            # Whisk에 업로드 - ImageFX 이미지는 피사체 박스(index=0)에 업로드
            print(f"\n📤 ImageFX 이미지를 Whisk 피사체 박스에 업로드...", flush=True)
            upload_image_to_whisk(driver, image_path, aspect_ratio, box_index=0, box_name="피사체(ImageFX)")

        else:
            # 백업 처리 (Whisk만 사용하는 경우, 이미지 생성 전에 실행)
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

        # 상품 카테고리면 Whisk에 썸네일 업로드
        product_thumbnail_path = None
        if is_product and product_thumbnail:
            print("\n" + "="*80, flush=True)
            print("🛒 상품 썸네일 다운로드 및 업로드", flush=True)
            print("="*80, flush=True)

            try:
                import requests

                # 확장자 결정
                ext = '.jpg'
                if 'png' in product_thumbnail.lower():
                    ext = '.png'
                elif 'webp' in product_thumbnail.lower():
                    ext = '.webp'

                # task 폴더에 썸네일 저장 (안정적인 경로)
                product_thumbnail_path = os.path.join(output_folder, f'product_thumbnail{ext}')

                # 이미 존재하면 재사용
                if os.path.exists(product_thumbnail_path) and os.path.getsize(product_thumbnail_path) > 1000:
                    print(f"✅ 기존 썸네일 사용: {product_thumbnail_path}", flush=True)
                else:
                    # 썸네일 다운로드
                    print(f"📥 썸네일 다운로드 중: {product_thumbnail[:80]}...", flush=True)
                    response = requests.get(product_thumbnail, timeout=30)
                    if response.status_code == 200:
                        with open(product_thumbnail_path, 'wb') as f:
                            f.write(response.content)
                        print(f"✅ 썸네일 저장 완료: {product_thumbnail_path}", flush=True)
                        print(f"   파일 크기: {os.path.getsize(product_thumbnail_path)} bytes", flush=True)
                    else:
                        print(f"⚠️ 썸네일 다운로드 실패: HTTP {response.status_code}", flush=True)
                        product_thumbnail_path = None

                if product_thumbnail_path and os.path.exists(product_thumbnail_path):
                    # Whisk 전용 모드일 때만 썸네일을 업로드
                    # ImageFX+Whisk 모드에서는 ImageFX 이미지만 사용
                    if not args.use_imagefx:
                        # 상품 카테고리는 항상 스타일 박스(2번)에 업로드
                        if is_product:
                            # 상품: 항상 스타일 박스(2번)에 업로드
                            upload_image_to_whisk(driver, product_thumbnail_path, aspect_ratio,
                                                  box_index=2, box_name="스타일(상품 썸네일)")
                            print(f"✅ 상품 썸네일 Whisk 스타일 박스 업로드 완료 (카테고리: 상품)", flush=True)
                        elif aspect_ratio == '16:9':
                            # 롱폼: 상품 썸네일을 피사체 박스(0번)에 업로드
                            upload_image_to_whisk(driver, product_thumbnail_path, aspect_ratio,
                                                  box_index=0, box_name="피사체(썸네일-롱폼)")
                            print(f"✅ 썸네일 Whisk 피사체 박스 업로드 완료 (롱폼 16:9)", flush=True)
                        else:
                            # 숏폼: 상품 썸네일을 스타일 박스(2번)에 업로드
                            upload_image_to_whisk(driver, product_thumbnail_path, aspect_ratio,
                                                  box_index=2, box_name="스타일(썸네일)")
                            print(f"✅ 썸네일 Whisk 스타일 박스 업로드 완료 (9:16)", flush=True)
                    else:
                        print(f"ℹ️ ImageFX+Whisk 모드: 상품 썸네일 업로드 생략 (ImageFX 이미지 사용)", flush=True)
                else:
                    print(f"⚠️ 썸네일 파일이 존재하지 않음: {product_thumbnail_path}", flush=True)
            except Exception as e:
                print(f"⚠️ 썸네일 처리 실패: {e}", flush=True)
                import traceback
                traceback.print_exc()

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
            current_prompt = prompt  # 현재 시도할 프롬프트

            for attempt in range(max_retries):
                print(f"\n{'-'*80}", flush=True)
                print(f"📌 {scene_number} 입력 중 (시도 {attempt + 1}/{max_retries})...", flush=True)
                print(f"{'-'*80}", flush=True)

                prompt_source = 'image_prompt' if scene.get('image_prompt') else 'sora_prompt'
                print(f"   프롬프트 출처: {prompt_source}", flush=True)
                print(f"   내용: {current_prompt[:80]}{'...' if len(current_prompt) > 80 else ''}", flush=True)

                # 프롬프트 입력
                success = input_prompt_to_whisk(driver, current_prompt, is_first=(i == 0 and attempt == 0))

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
                        # 프롬프트를 실제로 수정 (aggressive 모드는 2번째 시도부터)
                        safe_prompt = sanitize_prompt_for_google(prompt, aggressive=(attempt > 0))
                        current_prompt = safe_prompt  # 수정된 프롬프트로 교체
                        print(f"   📝 프롬프트 수정됨 (aggressive={attempt > 0})", flush=True)
                        time.sleep(3)
                        continue
                    else:
                        print(f"   ❌ 최대 재시도 횟수 초과, 다음 씬으로 이동", flush=True)
                        break

                # 입력 성공 및 정책 위반 없음 - 이미지 생성 및 수집으로 진행
                print(f"✅ {scene_number} 입력 완료 (정책 위반 없음)", flush=True)

                # 🔴 이미지 생성 대기 및 수집을 재시도 루프 안에서 처리
                # Whisk가 이미지를 생성할 시간 대기 (씬당 최소 30초)
                generation_wait = 30
                print(f"\n⏳ 이미지 생성 대기 중... ({generation_wait}초)", flush=True)
                time.sleep(generation_wait)

                # 이미지 수집
                print(f"\n📥 {scene_number}의 이미지 수집 중...", flush=True)

                # 🔴 중요: 이미 다운로드한 src 목록을 JavaScript로 전달
                already_downloaded = list(downloaded_image_srcs)

                # Whisk 페이지에서 생성된 이미지 찾기 (이번 씬만)
                scene_image = driver.execute_script("""
                    const imgs = Array.from(document.querySelectorAll('img'));
                    const alreadyDownloaded = arguments[0];  // Python에서 전달받은 이미 다운로드한 src 목록

                    // 🔴 디버그: 모든 이미지 정보 수집
                    const debugInfo = imgs.map(img => ({
                        src: (img.src || '').substring(0, 80),
                        width: img.offsetWidth,
                        height: img.offsetHeight,
                        naturalWidth: img.naturalWidth,
                        naturalHeight: img.naturalHeight,
                        classList: Array.from(img.classList).join(' '),
                        parentClass: img.parentElement ? Array.from(img.parentElement.classList).join(' ') : ''
                    }));

                    // 가장 최근에 생성된 큰 이미지 찾기
                    let excludedCount = 0;
                    let filterReasons = [];

                    const validImgs = imgs.filter(img => {
                        const src = img.src || '';

                        // 🔴 개선된 필터링 조건 (더 관대하게)
                        // 1. 크기 체크: 50x50 이상 (기존 100x100에서 완화)
                        //    또는 naturalWidth/Height가 큰 경우 (아직 렌더링 안됨)
                        const displaySize = img.offsetWidth * img.offsetHeight;
                        const naturalSize = img.naturalWidth * img.naturalHeight;
                        if (displaySize < 2500 && naturalSize < 10000) {
                            filterReasons.push({src: src.substring(0, 50), reason: 'size_too_small', displaySize, naturalSize});
                            return false;
                        }

                        // 2. data URL은 여전히 제외 (인라인 아이콘 등)
                        if (src.startsWith('data:')) {
                            filterReasons.push({src: src.substring(0, 50), reason: 'data_url'});
                            return false;
                        }

                        // 3. 🔴 개선: http, https, blob 외에도 상대 경로(/로 시작) 허용
                        if (!src.startsWith('http') && !src.startsWith('blob:') && !src.startsWith('/')) {
                            filterReasons.push({src: src.substring(0, 50), reason: 'invalid_protocol'});
                            return false;
                        }

                        // 4. 🔴 Whisk 결과 이미지 특성: 특정 클래스나 부모 확인
                        //    Whisk 생성 이미지는 보통 특정 컨테이너 안에 있음
                        const parentClass = img.parentElement ? img.parentElement.className : '';
                        const grandParentClass = img.parentElement?.parentElement ? img.parentElement.parentElement.className : '';

                        // 5. 이미 다운로드한 이미지는 제외
                        if (alreadyDownloaded.includes(src)) {
                            excludedCount++;
                            return false;
                        }

                        // 6. 🔴 추가: 아바타/프로필 이미지 제외 (보통 작고 동그람)
                        if (src.includes('avatar') || src.includes('profile') ||
                            parentClass.includes('avatar') || parentClass.includes('profile')) {
                            filterReasons.push({src: src.substring(0, 50), reason: 'avatar_image'});
                            return false;
                        }

                        // 7. 🔴 추가: 로고/아이콘 이미지 제외
                        if (src.includes('logo') || src.includes('icon') || src.includes('favicon')) {
                            filterReasons.push({src: src.substring(0, 50), reason: 'logo_icon'});
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

                    // 이미지가 2개 이상이면 랜덤으로 1개 선택, 1개면 해당 이미지 선택
                    if (sorted.length > 0) {
                        let selectedImg;
                        let selectedIndex;

                        if (sorted.length >= 2) {
                            // 2개 이상: 랜덤으로 선택
                            selectedIndex = Math.floor(Math.random() * Math.min(sorted.length, 2)); // 상위 2개 중 랜덤
                            selectedImg = sorted[selectedIndex];
                            console.log(`Randomly selected image ${selectedIndex + 1} of ${sorted.length}`);
                        } else {
                            // 1개: 해당 이미지 선택
                            selectedImg = sorted[0];
                            selectedIndex = 0;
                            console.log('Only one image, selecting it');
                        }

                        // Whisk의 모든 variation src 수집 (중복 방지용)
                        const allVariationSrcs = sorted.map(img => img.src);
                        return {
                            src: selectedImg.src,
                            width: selectedImg.offsetWidth,
                            height: selectedImg.offsetHeight,
                            isBlob: selectedImg.src.startsWith('blob:'),
                            allSrcs: allVariationSrcs,  // 모든 variation src 배열
                            totalImages: imgs.length,
                            excludedCount: excludedCount,
                            candidateCount: validImgs.length,
                            selectedIndex: selectedIndex,
                            imageCount: sorted.length,
                            debugInfo: debugInfo.slice(0, 5),  // 디버그용 (상위 5개만)
                            filterReasons: filterReasons.slice(0, 5)  // 필터링 이유 (상위 5개만)
                        };
                    }
                    return {
                        src: null,
                        totalImages: imgs.length,
                        excludedCount: excludedCount,
                        candidateCount: validImgs.length,
                        debugInfo: debugInfo.slice(0, 10),  // 이미지 0개일 때 더 많은 디버그 정보
                        filterReasons: filterReasons
                    };
                """, already_downloaded)

                print(f"   📊 이미지 통계: 전체 {scene_image.get('totalImages', 0)}개, "
                      f"제외 {scene_image.get('excludedCount', 0)}개, "
                      f"후보 {scene_image.get('candidateCount', 0)}개", flush=True)

                # 🔴 이미지 0개 체크 - 정책 위반/생성 실패로 간주하고 재시도
                if not scene_image or not scene_image.get('src') or scene_image.get('candidateCount', 0) == 0:
                    print(f"   ⚠️ 이미지를 찾을 수 없습니다 - 정책 위반 가능성", flush=True)

                    # 🔴 디버그: 필터링 탈락 이유 출력
                    debug_info = scene_image.get('debugInfo', [])
                    filter_reasons = scene_image.get('filterReasons', [])

                    if debug_info:
                        print(f"   🔍 페이지 이미지 정보 (상위 {len(debug_info)}개):", flush=True)
                        for idx, img_info in enumerate(debug_info[:5]):
                            print(f"      [{idx+1}] {img_info.get('width')}x{img_info.get('height')} "
                                  f"(natural: {img_info.get('naturalWidth')}x{img_info.get('naturalHeight')}) "
                                  f"src: {img_info.get('src', '')[:50]}...", flush=True)

                    if filter_reasons:
                        print(f"   🚫 필터링 탈락 이유:", flush=True)
                        for reason in filter_reasons[:5]:
                            print(f"      - {reason.get('reason')}: {reason.get('src', '')[:40]}...", flush=True)

                    # 추가 정책 위반 체크
                    violation_after = detect_policy_violation(driver)
                    if violation_after.get('violation_detected'):
                        print(f"   🔍 정책 위반 확인: {violation_after.get('matched_keywords', [])}", flush=True)

                    if attempt < max_retries - 1:
                        print(f"   🔄 이미지 0개/정책 위반 - 프롬프트 수정 후 재시도 ({attempt + 2}/{max_retries})", flush=True)
                        # aggressive 모드로 프롬프트 강력하게 수정
                        current_prompt = sanitize_prompt_for_google(prompt, aggressive=True)
                        print(f"   📝 프롬프트 수정됨 (aggressive=True)", flush=True)
                        time.sleep(5)
                        continue  # 재시도 루프의 다음 반복으로
                    else:
                        print(f"   ❌ 최대 재시도 횟수({max_retries}회) 초과 - 이 씬은 건너뜁니다", flush=True)
                        print(f"   💡 팁: 프롬프트에서 'Korean person', '유명인' 관련 단어를 제거해보세요", flush=True)
                        break  # 재시도 루프 탈출, 다음 씬으로

                # 이미지 발견됨 - 다운로드 진행
                image_count = scene_image.get('imageCount', 1)
                selected_index = scene_image.get('selectedIndex', 0)

                if image_count >= 2:
                    print(f"   🎲 {image_count}개 이미지 중 랜덤 선택: #{selected_index + 1}", flush=True)
                elif image_count == 1:
                    print(f"   ✅ 1개 이미지 발견", flush=True)

                print(f"   📐 크기: {scene_image['width']}x{scene_image['height']}", flush=True)

                # 이미지 다운로드
                import requests
                import base64
                download_success = False

                try:
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
                        break  # 성공! 재시도 루프 탈출
                    else:
                        # 다운로드 실패 시 재시도
                        if attempt < max_retries - 1:
                            print(f"   ⚠️ 다운로드 실패 - 재시도 ({attempt + 2}/{max_retries})", flush=True)
                            current_prompt = sanitize_prompt_for_google(prompt, aggressive=True)
                            time.sleep(5)
                            continue
                        else:
                            print(f"   ❌ 다운로드 실패 - 최대 재시도 횟수 초과", flush=True)
                            break

                except Exception as e:
                    print(f"   ❌ 다운로드 중 오류: {e}", flush=True)
                    if attempt < max_retries - 1:
                        print(f"   🔄 재시도 중... ({attempt + 2}/{max_retries})", flush=True)
                        current_prompt = sanitize_prompt_for_google(prompt, aggressive=True)
                        time.sleep(5)
                        continue
                    else:
                        print(f"   ❌ 최대 재시도 횟수 초과", flush=True)
                        break

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
            try:
                print("\n✅ 작업 완료. 브라우저를 닫습니다.", flush=True)
                driver.quit()
                print("✅ 브라우저 종료 완료", flush=True)
            except Exception as e:
                print(f"⚠️ 브라우저 종료 실패: {e}", flush=True)
                try:
                    # 강제 종료 시도
                    driver.service.process.kill()
                    print("✅ 브라우저 프로세스 강제 종료 완료", flush=True)
                except:
                    pass

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