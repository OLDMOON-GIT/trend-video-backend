#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한 번에 모든 작업 수행 테스트"""

import sys
import io
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# UTF-8 출력 설정
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def test_onetime_input():
    # 실행 중인 Chrome에 연결
    chrome_options = Options()
    chrome_options.debugger_address = "127.0.0.1:9222"

    try:
        driver = webdriver.Chrome(options=chrome_options)
        print("✅ Chrome 연결 완료")
    except Exception as e:
        print(f"❌ Chrome 연결 실패: {e}")
        return

    # Image-FX 페이지 확인
    current_url = driver.current_url
    if 'image-fx' not in current_url:
        driver.get('https://labs.google/fx/tools/image-fx')
        print("📄 Image-FX 페이지로 이동...")
        time.sleep(15)

    print(f"🔗 현재 URL: {driver.current_url}")

    test_text = "A beautiful sunset over the ocean, golden hour, cinematic lighting"

    print("\n" + "="*80)
    print("🎯 한 번에 모든 작업 수행 테스트")
    print("="*80)
    print(f"입력할 텍스트: {test_text}")

    # 모든 작업을 JavaScript로 한 번에 수행
    result = driver.execute_script("""
        const testText = arguments[0];

        // 1. .fZKmcZ 요소 찾기
        const elem = document.querySelector('.fZKmcZ');
        if (!elem) {
            return {success: false, error: '.fZKmcZ 요소를 찾을 수 없음'};
        }

        // 2. 요소 클릭 및 포커스
        elem.click();
        elem.focus();

        // 3. 기존 텍스트 제거
        elem.textContent = '';
        elem.innerText = '';

        // 짧은 대기 (React 상태 업데이트)
        setTimeout(() => {
            // 4. 새 텍스트 입력
            elem.textContent = testText;
            elem.innerText = testText;

            // 5. React 이벤트 발생
            elem.dispatchEvent(new Event('input', { bubbles: true }));
            elem.dispatchEvent(new Event('change', { bubbles: true }));
            elem.dispatchEvent(new InputEvent('input', { bubbles: true, data: testText }));

            // 6. 엔터 키 이벤트
            elem.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
            elem.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
            elem.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
        }, 100);

        return {
            success: true,
            originalText: elem.textContent,
            newText: testText
        };
    """, test_text)

    if result.get('success'):
        print("✅ JavaScript 실행 성공!")
        print(f"   원본: {result.get('originalText', '')[:50]}...")
        print(f"   입력: {result.get('newText', '')}")
    else:
        print(f"❌ 실패: {result.get('error')}")
        return

    # 잠시 대기 후 결과 확인
    time.sleep(1)

    final_text = driver.execute_script("""
        const elem = document.querySelector('.fZKmcZ');
        return elem ? elem.textContent : null;
    """)

    print(f"\n📊 최종 결과:")
    print(f"   현재 텍스트: {final_text}")
    print(f"   일치 여부: {test_text in final_text}")

    # 스크린샷
    driver.save_screenshot('onetime_test.png')
    print(f"\n📸 스크린샷 저장: onetime_test.png")

    print("\n✅ 테스트 완료!")

if __name__ == '__main__':
    test_onetime_input()
