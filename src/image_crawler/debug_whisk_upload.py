#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Whisk 업로드 요소 찾기 디버그"""

import sys
import io
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# UTF-8 출력
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True, write_through=True)

# Chrome 연결
chrome_options = Options()
chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=chrome_options)
print("✅ Chrome 연결 완료")

# Whisk 페이지로 이동
driver.get('https://labs.google/fx/ko/tools/whisk/project')
print("⏳ Whisk 페이지 로딩...")
time.sleep(5)

print("\n" + "="*80)
print("🔍 Whisk 페이지 구조 분석")
print("="*80)

# 1. 모든 input[type="file"] 찾기
file_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
print(f"\n1️⃣ input[type='file'] 요소 개수: {len(file_inputs)}")
for i, inp in enumerate(file_inputs):
    visible = inp.is_displayed()
    enabled = inp.is_enabled()
    print(f"   [{i}] visible={visible}, enabled={enabled}")
    if visible or enabled:
        # 속성 출력
        attrs = driver.execute_script("""
            const elem = arguments[0];
            return {
                id: elem.id,
                className: elem.className,
                accept: elem.accept,
                multiple: elem.multiple,
                name: elem.name
            };
        """, inp)
        print(f"       속성: {attrs}")

# 2. 업로드 버튼 찾기
print("\n2️⃣ 업로드 관련 버튼 찾기")
selectors = [
    'button[aria-label*="upload"]',
    'button[aria-label*="Upload"]',
    'button[aria-label*="업로드"]',
    '[role="button"][aria-label*="upload"]',
    '[role="button"][aria-label*="Upload"]',
    'button:has(svg)',
    'button:has(input[type="file"])',
]

for selector in selectors:
    elements = driver.find_elements(By.CSS_SELECTOR, selector)
    if elements:
        print(f"   ✅ '{selector}': {len(elements)}개 발견")
        for i, elem in enumerate(elements[:3]):  # 처음 3개만
            try:
                text = elem.text[:50] if elem.text else ''
                aria_label = elem.get_attribute('aria-label')
                print(f"      [{i}] text='{text}', aria-label='{aria_label}'")
            except:
                pass

# 3. 인물/Subject 관련 요소 찾기
print("\n3️⃣ Subject/인물 관련 요소 찾기")
subject_texts = ['subject', 'Subject', '인물', 'character', 'Character']
for text in subject_texts:
    elements = driver.find_elements(By.XPATH, f"//*[contains(text(), '{text}')]")
    if elements:
        print(f"   ✅ '{text}' 포함 요소: {len(elements)}개")

# 4. 전체 페이지 구조 (상위 레벨 div들)
print("\n4️⃣ 페이지 주요 구조")
structure = driver.execute_script("""
    const findUploadElements = () => {
        const all = document.querySelectorAll('*');
        const results = [];

        for (let elem of all) {
            // aria-label에 upload 포함
            const ariaLabel = elem.getAttribute('aria-label') || '';
            if (ariaLabel.toLowerCase().includes('upload')) {
                results.push({
                    tag: elem.tagName,
                    className: elem.className,
                    ariaLabel: ariaLabel,
                    text: elem.textContent.substring(0, 30)
                });
            }
        }

        return results;
    };

    return findUploadElements();
""")

print(f"   'upload' 포함 요소: {len(structure)}개")
for item in structure[:5]:
    print(f"   - {item['tag']}.{item['className'][:50]}")
    print(f"     aria-label: {item['ariaLabel']}")

# 5. 파일 드래그 앤 드롭 영역 찾기
print("\n5️⃣ 드래그 앤 드롭 영역 찾기")
drop_zones = driver.execute_script("""
    const zones = [];
    const all = document.querySelectorAll('[role="button"], div, section');

    for (let elem of all) {
        const text = elem.textContent.toLowerCase();
        if (text.includes('drag') || text.includes('drop') ||
            text.includes('드래그') || text.includes('click to upload')) {
            zones.push({
                tag: elem.tagName,
                className: elem.className,
                text: elem.textContent.substring(0, 50),
                hasFileInput: elem.querySelector('input[type="file"]') !== null
            });
        }
    }

    return zones;
""")

print(f"   드래그 앤 드롭 영역: {len(drop_zones)}개")
for zone in drop_zones[:3]:
    print(f"   - {zone['tag']}: {zone['text']}")
    print(f"     hasFileInput: {zone['hasFileInput']}")

# 6. 숨겨진 file input 찾기 (display:none이어도)
print("\n6️⃣ 숨겨진 file input 찾기")
hidden_inputs = driver.execute_script("""
    const inputs = document.querySelectorAll('input[type="file"]');
    return Array.from(inputs).map(inp => ({
        visible: inp.offsetWidth > 0 && inp.offsetHeight > 0,
        display: window.getComputedStyle(inp).display,
        visibility: window.getComputedStyle(inp).visibility,
        opacity: window.getComputedStyle(inp).opacity,
        id: inp.id,
        className: inp.className,
        parentTag: inp.parentElement ? inp.parentElement.tagName : null,
        parentClass: inp.parentElement ? inp.parentElement.className : null
    }));
""")

print(f"   총 input[type='file']: {len(hidden_inputs)}개")
for i, inp in enumerate(hidden_inputs):
    print(f"   [{i}] visible={inp['visible']}, display={inp['display']}, opacity={inp['opacity']}")
    print(f"       parent: {inp['parentTag']}.{inp['parentClass'][:30] if inp['parentClass'] else ''}")

print("\n" + "="*80)
print("✅ 분석 완료! 위 정보로 올바른 업로드 방법 찾기")
print("="*80)
