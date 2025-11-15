#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fZKmcZ 요소와 상호작용 테스트"""

import sys
import io
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

# UTF-8 출력 설정
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def test_fZKmcZ():
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

    # .fZKmcZ 요소 찾기
    print("\n" + "="*80)
    print("1️⃣ .fZKmcZ 요소 찾기")
    print("="*80)

    try:
        element = driver.find_element(By.CSS_SELECTOR, '.fZKmcZ')
        print("✅ .fZKmcZ 요소 발견!")

        # 요소 정보 출력
        info = driver.execute_script("""
            const elem = arguments[0];
            return {
                tagName: elem.tagName,
                className: elem.className,
                id: elem.id,
                contentEditable: elem.contentEditable,
                isContentEditable: elem.isContentEditable,
                innerHTML: elem.innerHTML.substring(0, 200),
                outerHTML: elem.outerHTML.substring(0, 500),
                text: elem.textContent,
                offsetWidth: elem.offsetWidth,
                offsetHeight: elem.offsetHeight,
                children: elem.children.length
            };
        """, element)

        print("\n📊 요소 정보:")
        for key, value in info.items():
            print(f"   {key}: {value}")

    except Exception as e:
        print(f"❌ 요소를 찾을 수 없음: {e}")
        return

    # 2. 클릭 및 포커스 테스트
    print("\n" + "="*80)
    print("2️⃣ 클릭 및 포커스 테스트")
    print("="*80)

    try:
        element.click()
        print("✅ 클릭 성공")
        time.sleep(0.5)

        # activeElement 확인
        active_info = driver.execute_script("""
            const active = document.activeElement;
            const target = arguments[0];
            return {
                isFocused: active === target,
                activeTag: active.tagName,
                activeClass: active.className,
                activeText: active.textContent.substring(0, 100)
            };
        """, element)

        print(f"   포커스 상태: {active_info}")

    except Exception as e:
        print(f"⚠️ 클릭 실패: {e}")

    # 3. JavaScript로 텍스트 입력 테스트
    print("\n" + "="*80)
    print("3️⃣ JavaScript로 텍스트 입력 테스트")
    print("="*80)

    test_text = "A beautiful sunset over the ocean"

    try:
        # 기존 텍스트 백업
        original_text = driver.execute_script("return arguments[0].textContent;", element)
        print(f"   원본 텍스트: {original_text[:100]}")

        # 텍스트 설정
        result = driver.execute_script("""
            const elem = arguments[0];
            const newText = arguments[1];

            // 기존 텍스트 지우기
            elem.textContent = '';
            elem.innerText = '';

            // 새 텍스트 설정
            elem.textContent = newText;
            elem.innerText = newText;

            // 이벤트 발생
            elem.dispatchEvent(new Event('input', { bubbles: true }));
            elem.dispatchEvent(new Event('change', { bubbles: true }));
            elem.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
            elem.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', bubbles: true }));

            return elem.textContent;
        """, element, test_text)

        print(f"✅ JavaScript 입력 성공: {result}")
        time.sleep(1)

        # 결과 확인
        current_text = driver.execute_script("return arguments[0].textContent;", element)
        print(f"   현재 텍스트: {current_text[:100]}")

    except Exception as e:
        print(f"❌ JavaScript 입력 실패: {e}")

    # 4. send_keys 테스트
    print("\n" + "="*80)
    print("4️⃣ send_keys 테스트")
    print("="*80)

    try:
        element.click()
        time.sleep(0.2)
        element.clear()
        element.send_keys(test_text)
        print("✅ send_keys 성공")
        time.sleep(1)

        current_text = driver.execute_script("return arguments[0].textContent;", element)
        print(f"   현재 텍스트: {current_text[:100]}")

    except Exception as e:
        print(f"⚠️ send_keys 실패: {e}")

    # 5. ActionChains 테스트
    print("\n" + "="*80)
    print("5️⃣ ActionChains 테스트")
    print("="*80)

    try:
        element.click()
        time.sleep(0.2)

        actions = ActionChains(driver)
        actions.send_keys(Keys.CONTROL + 'a')
        actions.send_keys(test_text)
        actions.perform()

        print("✅ ActionChains 성공")
        time.sleep(1)

        current_text = driver.execute_script("return arguments[0].textContent;", element)
        print(f"   현재 텍스트: {current_text[:100]}")

    except Exception as e:
        print(f"⚠️ ActionChains 실패: {e}")

    # 6. 자식 요소 분석
    print("\n" + "="*80)
    print("6️⃣ 자식 요소 분석")
    print("="*80)

    children_info = driver.execute_script("""
        const elem = arguments[0];
        const children = Array.from(elem.children);

        return children.map(child => ({
            tag: child.tagName,
            class: child.className,
            contentEditable: child.contentEditable,
            isContentEditable: child.isContentEditable,
            text: child.textContent.substring(0, 50)
        }));
    """, element)

    print(f"   자식 요소 수: {len(children_info)}")
    for i, child in enumerate(children_info):
        print(f"   [{i}] {child}")

    print("\n✅ 테스트 완료!")

if __name__ == '__main__':
    test_fZKmcZ()
