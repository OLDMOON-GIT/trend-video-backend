#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Image-FX 입력 테스트 - 빠른 검증용"""

import sys
import io
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# UTF-8 출력
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True, write_through=True)

def test_imagefx_input():
    # Chrome 연결
    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    driver = webdriver.Chrome(options=chrome_options)
    print("✅ Chrome 연결 완료")

    # Image-FX 열기
    driver.get('https://labs.google/fx/tools/image-fx')
    print("📄 Image-FX 페이지로 이동...")

    # 페이지 완전 로드 대기
    print("⏳ 페이지 로딩 중...", flush=True)
    for i in range(30):
        ready = driver.execute_script("return document.readyState")
        if ready == "complete":
            print(f"✅ 페이지 로드 완료 ({i+1}초)", flush=True)
            break
        time.sleep(1)

    # 추가 렌더링 대기
    time.sleep(5)

    # .fZKmcZ 요소 기다리기
    print("🔍 입력창 찾는 중...", flush=True)
    found = False
    for i in range(30):
        has_elem = driver.execute_script("""
            const elem = document.querySelector('.fZKmcZ') || document.querySelector('.sc-1004f4bc-4');
            return elem !== null;
        """)

        if has_elem:
            print(f"✅ 입력창 발견! ({i+1}초)", flush=True)
            found = True
            break

        if i % 5 == 0 and i > 0:
            print(f"   대기 중... ({i}초)", flush=True)
        time.sleep(1)

    if not found:
        print("❌ 입력창을 찾을 수 없음", flush=True)
        return False

    # 테스트 프롬프트
    test_prompt = "A beautiful sunset over the ocean, golden hour, cinematic lighting"

    # 클릭 및 포커스
    print(f"⌨️ 입력 시작: {test_prompt[:40]}...", flush=True)
    driver.execute_script("""
        const elem = document.querySelector('.fZKmcZ') || document.querySelector('.sc-1004f4bc-4');
        if (elem) {
            elem.click();
            elem.focus();
        }
    """)
    time.sleep(0.5)

    # 텍스트 입력
    result = driver.execute_script("""
        const prompt = arguments[0];
        const elem = document.querySelector('.fZKmcZ') || document.querySelector('.sc-1004f4bc-4');

        if (!elem) {
            return {success: false, error: '요소를 찾을 수 없음'};
        }

        // 기존 텍스트 제거
        elem.textContent = '';
        elem.innerText = '';

        // 새 텍스트 입력
        elem.textContent = prompt;
        elem.innerText = prompt;

        // React 이벤트 발생
        elem.dispatchEvent(new Event('input', { bubbles: true }));
        elem.dispatchEvent(new Event('change', { bubbles: true }));
        elem.dispatchEvent(new InputEvent('input', { bubbles: true, data: prompt }));

        elem.focus();

        return {success: true, text: elem.textContent};
    """, test_prompt)

    if result.get('success'):
        print(f"✅ 입력 성공!", flush=True)
        print(f"   입력된 텍스트: {result.get('text', '')[:50]}...", flush=True)

        # 엔터 키
        time.sleep(1)
        driver.execute_script("""
            const elem = document.querySelector('.fZKmcZ') || document.querySelector('.sc-1004f4bc-4');
            if (elem) {
                elem.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', keyCode: 13, bubbles: true }));
                elem.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', keyCode: 13, bubbles: true }));
            }
        """)
        print("⏎ Enter 입력 완료", flush=True)
        print("\n✅ 테스트 성공! Image-FX에서 이미지 생성이 시작되었는지 확인하세요.", flush=True)
        return True
    else:
        print(f"❌ 입력 실패: {result.get('error')}", flush=True)
        return False

if __name__ == '__main__':
    success = test_imagefx_input()
    sys.exit(0 if success else 1)
