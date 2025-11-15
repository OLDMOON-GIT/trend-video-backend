#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Image-FX 페이지 실시간 디버그"""

import sys
import io
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# UTF-8 출력 설정
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def debug_imagefx():
    # 실행 중인 Chrome에 연결
    chrome_options = Options()
    chrome_options.debugger_address = "127.0.0.1:9222"

    try:
        driver = webdriver.Chrome(options=chrome_options)
        print("✅ Chrome 연결 완료")
    except Exception as e:
        print(f"❌ Chrome 연결 실패: {e}")
        return

    # Image-FX로 이동
    driver.get('https://labs.google/fx/tools/image-fx')
    print("📄 Image-FX 페이지로 이동...")
    time.sleep(15)

    # 스크린샷
    driver.save_screenshot('imagefx_debug.png')
    print("📸 스크린샷 저장: imagefx_debug.png")

    # 현재 URL 확인
    print(f"🔗 현재 URL: {driver.current_url}")

    # 1. 모든 input 요소 찾기
    print("\n" + "="*80)
    print("1️⃣ 모든 input 요소:")
    print("="*80)
    inputs = driver.find_elements(By.TAG_NAME, 'input')
    for i, inp in enumerate(inputs):
        try:
            print(f"{i}: type={inp.get_attribute('type')}, visible={inp.is_displayed()}, class={inp.get_attribute('class')}")
        except:
            pass

    # 2. 모든 textarea 찾기
    print("\n" + "="*80)
    print("2️⃣ 모든 textarea:")
    print("="*80)
    textareas = driver.find_elements(By.TAG_NAME, 'textarea')
    for i, ta in enumerate(textareas):
        try:
            print(f"{i}: visible={ta.is_displayed()}, class={ta.get_attribute('class')}")
        except:
            pass

    # 3. contenteditable div 찾기
    print("\n" + "="*80)
    print("3️⃣ contenteditable div:")
    print("="*80)
    result = driver.execute_script("""
        const editables = document.querySelectorAll('[contenteditable]');
        return Array.from(editables).map((el, i) => ({
            index: i,
            tag: el.tagName,
            contentEditable: el.contentEditable,
            isContentEditable: el.isContentEditable,
            className: el.className,
            text: el.textContent.substring(0, 100),
            visible: el.offsetHeight > 0 && el.offsetWidth > 0
        }));
    """)
    for item in result:
        print(f"{item}")

    # 4. styled-components (sc-) 클래스 가진 div 중 contenteditable 찾기
    print("\n" + "="*80)
    print("4️⃣ styled-components div (sc-*):")
    print("="*80)
    result = driver.execute_script("""
        const scDivs = document.querySelectorAll('[class*="sc-"]');
        return Array.from(scDivs).slice(0, 30).map((el, i) => ({
            index: i,
            tag: el.tagName,
            className: el.className,
            contentEditable: el.contentEditable,
            isContentEditable: el.isContentEditable,
            text: el.textContent.substring(0, 80),
            visible: el.offsetHeight > 0 && el.offsetWidth > 0,
            height: el.offsetHeight,
            width: el.offsetWidth
        }));
    """)
    for item in result:
        if item['visible'] and item['height'] > 20 and item['height'] < 300:
            print(f"✅ {item}")

    # 5. .fZKmcZ 선택자 확인
    print("\n" + "="*80)
    print("5️⃣ .fZKmcZ 선택자 테스트:")
    print("="*80)
    result = driver.execute_script("""
        const elem = document.querySelector('.fZKmcZ');
        if (elem) {
            return {
                found: true,
                tag: elem.tagName,
                className: elem.className,
                contentEditable: elem.contentEditable,
                isContentEditable: elem.isContentEditable,
                text: elem.textContent.substring(0, 100),
                visible: elem.offsetHeight > 0 && elem.offsetWidth > 0
            };
        }
        return {found: false};
    """)
    print(f"{result}")

    # 6. Shadow DOM 검색
    print("\n" + "="*80)
    print("6️⃣ Shadow DOM 검색:")
    print("="*80)
    result = driver.execute_script("""
        const shadowHosts = document.querySelectorAll('*');
        const shadowResults = [];

        for (let host of shadowHosts) {
            if (host.shadowRoot) {
                const editables = host.shadowRoot.querySelectorAll('[contenteditable]');
                if (editables.length > 0) {
                    shadowResults.push({
                        host: host.tagName,
                        hostClass: host.className,
                        editableCount: editables.length,
                        firstEditable: {
                            tag: editables[0].tagName,
                            class: editables[0].className,
                            text: editables[0].textContent.substring(0, 50)
                        }
                    });
                }
            }
        }

        return shadowResults;
    """)
    print(f"Shadow DOM 호스트 수: {len(result)}")
    for item in result:
        print(f"{item}")

    # 7. 페이지 HTML 일부 저장
    print("\n" + "="*80)
    print("7️⃣ HTML 저장:")
    print("="*80)
    html = driver.page_source[:5000]
    with open('imagefx_html.txt', 'w', encoding='utf-8') as f:
        f.write(html)
    print("💾 HTML 저장: imagefx_html.txt")

    print("\n✅ 디버깅 완료! 브라우저는 그대로 유지됩니다.")
    print("   스크린샷과 로그를 확인하세요.")

if __name__ == '__main__':
    debug_imagefx()
