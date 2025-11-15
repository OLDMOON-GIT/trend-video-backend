#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Whisk 직접 파일 할당 테스트"""

import sys
import io
import time
import os
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

# 테스트 파일
test_file = os.path.join(os.path.expanduser('~'), 'Downloads')
files = [f for f in os.listdir(test_file) if f.endswith(('.jpg', '.jpeg', '.png'))]
if files:
    test_file = os.path.join(test_file, files[0])
    print(f"📁 테스트 파일: {test_file}")
else:
    print("❌ 테스트 파일 없음")
    sys.exit(1)

print("\n" + "="*80)
print("🔍 방법 1: JavaScript로 file input 동적 생성 및 할당")
print("="*80)

result = driver.execute_script("""
    const filePath = arguments[0];

    // file input을 동적으로 생성
    const input = document.createElement('input');
    input.type = 'file';
    input.style.display = 'none';
    document.body.appendChild(input);

    // 파일 선택 완료 시 이벤트 처리
    input.addEventListener('change', function() {
        console.log('File selected:', this.files[0]);
    });

    return {success: true, created: true};
""", test_file)

print(f"   생성 결과: {result}")

# 생성된 input 찾기
time.sleep(1)
file_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
print(f"   file input 개수: {len(file_inputs)}")

if file_inputs:
    try:
        print(f"   파일 할당 시도...")
        file_inputs[-1].send_keys(os.path.abspath(test_file))  # 마지막 것 (방금 생성한 것)
        print("   ✅ 파일 할당 성공!")
        time.sleep(3)

        # change 이벤트 발생
        driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", file_inputs[-1])
        print("   ✅ change 이벤트 발생")

    except Exception as e:
        print(f"   ❌ 파일 할당 실패: {e}")

print("\n" + "="*80)
print("🔍 방법 2: 드래그 앤 드롭 영역에 DataTransfer 사용")
print("="*80)

drop_result = driver.execute_script("""
    // 드래그 앤 드롭 영역 찾기
    const dropZone = document.querySelector('[role="button"]');
    if (!dropZone) {
        return {success: false, error: '드롭 영역을 찾을 수 없음'};
    }

    // drop 이벤트 시뮬레이션
    const dropEvent = new DragEvent('drop', {
        bubbles: true,
        cancelable: true,
        dataTransfer: new DataTransfer()
    });

    dropZone.dispatchEvent(dropEvent);

    return {
        success: true,
        tag: dropZone.tagName,
        className: String(dropZone.className || '').substring(0, 50)
    };
""")

print(f"   결과: {drop_result}")

print("\n" + "="*80)
print("✅ 테스트 완료 - 페이지에서 파일이 업로드되었는지 확인하세요")
print("="*80)
