#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Whisk 업로드 버튼 클릭 방법 찾기"""

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
print("🔍 add_photo_alternate 아이콘 찾기")
print("="*80)

# Material Icons로 이미지 추가 버튼 찾기
icons = driver.execute_script("""
    const allElements = Array.from(document.querySelectorAll('*'));
    const photoIcons = [];

    for (let elem of allElements) {
        const text = elem.textContent || '';
        const className = String(elem.className || '');

        // Material Icon 찾기
        if (text.includes('add_photo_alternate') ||
            text.includes('photo') ||
            className.includes('photo') ||
            className.includes('upload')) {

            // 부모 요소 정보도 포함
            const parent = elem.parentElement;
            const parentClassName = parent ? String(parent.className || '') : '';

            photoIcons.push({
                tag: elem.tagName,
                className: className.substring(0, 80),
                text: text.substring(0, 50),
                role: elem.getAttribute('role'),
                ariaLabel: elem.getAttribute('aria-label'),
                clickable: elem.onclick !== null || elem.getAttribute('onclick') !== null,
                parentTag: parent ? parent.tagName : null,
                parentClass: parentClassName.substring(0, 50),
                parentRole: parent ? parent.getAttribute('role') : null
            });
        }
    }

    return photoIcons;
""")

print(f"\n발견된 이미지/사진 관련 요소: {len(icons)}개\n")
for i, icon in enumerate(icons[:10]):  # 처음 10개만
    print(f"[{i}] {icon['tag']}")
    print(f"    className: {icon['className']}")
    print(f"    text: {icon['text']}")
    print(f"    role: {icon['role']}, ariaLabel: {icon['ariaLabel']}")
    print(f"    clickable: {icon['clickable']}")
    print(f"    parent: {icon['parentTag']}.{icon['parentClass']}")
    print(f"    parentRole: {icon['parentRole']}")
    print()

# Subject 영역 찾기
print("\n" + "="*80)
print("🔍 Subject/인물 영역 상세 분석")
print("="*80)

subject_area = driver.execute_script("""
    // "Subject" 또는 "인물" 텍스트를 포함하는 요소 찾기
    const allElements = Array.from(document.querySelectorAll('*'));
    const subjectElements = [];

    for (let elem of allElements) {
        const text = elem.textContent || '';
        if (text.includes('Subject') || text.includes('인물')) {
            // 이 요소의 형제와 자식들을 모두 검사
            const parent = elem.parentElement;
            if (parent) {
                const siblings = Array.from(parent.children);
                for (let sibling of siblings) {
                    const siblingText = sibling.textContent || '';
                    const siblingClass = String(sibling.className || '');

                    // 클릭 가능한 요소 찾기
                    const clickableChildren = sibling.querySelectorAll('[role="button"], button, div[onclick]');

                    if (clickableChildren.length > 0 || siblingText.includes('add_photo')) {
                        subjectElements.push({
                            tag: sibling.tagName,
                            className: siblingClass.substring(0, 80),
                            text: siblingText.substring(0, 100),
                            role: sibling.getAttribute('role'),
                            clickableChildrenCount: clickableChildren.length,
                            hasPhotoIcon: siblingText.includes('add_photo')
                        });
                    }
                }
            }
        }
    }

    return subjectElements;
""")

print(f"\nSubject 영역 내 클릭 가능한 요소: {len(subject_area)}개\n")
for i, elem in enumerate(subject_area[:5]):
    print(f"[{i}] {elem['tag']}")
    print(f"    className: {elem['className']}")
    print(f"    text: {elem['text']}")
    print(f"    role: {elem['role']}")
    print(f"    clickableChildren: {elem['clickableChildrenCount']}")
    print(f"    hasPhotoIcon: {elem['hasPhotoIcon']}")
    print()

# 실제 클릭 시도 (첫 번째 이미지 추가 버튼)
print("\n" + "="*80)
print("🖱️ 이미지 추가 버튼 클릭 시도")
print("="*80)

click_result = driver.execute_script("""
    // add_photo_alternate 아이콘이 있는 클릭 가능한 요소 찾기
    const findUploadButton = () => {
        const all = document.querySelectorAll('*');

        for (let elem of all) {
            const text = elem.textContent || '';
            const role = elem.getAttribute('role');

            // Material Icon이 있고 클릭 가능한 요소
            if (text.includes('add_photo_alternate') &&
                (role === 'button' || elem.tagName === 'BUTTON' ||
                 elem.onclick !== null)) {
                return elem;
            }

            // 부모가 클릭 가능한 경우
            if (text.includes('add_photo_alternate')) {
                let parent = elem.parentElement;
                if (parent &&
                    (parent.getAttribute('role') === 'button' ||
                     parent.tagName === 'BUTTON' ||
                     parent.onclick !== null)) {
                    return parent;
                }
            }
        }

        return null;
    };

    const btn = findUploadButton();
    if (btn) {
        btn.click();
        return {
            success: true,
            tag: btn.tagName,
            className: String(btn.className || '').substring(0, 50),
            role: btn.getAttribute('role')
        };
    }

    return {success: false, error: '버튼을 찾을 수 없음'};
""")

if click_result.get('success'):
    print(f"✅ 버튼 클릭 성공!")
    print(f"   tag: {click_result['tag']}")
    print(f"   className: {click_result['className']}")
    print(f"   role: {click_result['role']}")

    # 클릭 후 file input이 생성되었는지 확인
    print("\n⏳ file input 생성 확인 (3초 대기)...")
    time.sleep(3)

    file_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
    print(f"\n✅ file input 개수: {len(file_inputs)}")

    if file_inputs:
        print("✅ file input 생성됨! 파일 업로드 가능!")
        for i, inp in enumerate(file_inputs):
            attrs = driver.execute_script("""
                const elem = arguments[0];
                return {
                    visible: elem.offsetWidth > 0 && elem.offsetHeight > 0,
                    accept: elem.accept,
                    multiple: elem.multiple
                };
            """, inp)
            print(f"   [{i}] visible={attrs['visible']}, accept={attrs['accept']}, multiple={attrs['multiple']}")
    else:
        print("❌ file input이 생성되지 않음")
else:
    print(f"❌ 클릭 실패: {click_result.get('error')}")

print("\n" + "="*80)
print("✅ 분석 완료")
print("="*80)
