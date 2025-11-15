#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
완전한 워크플로우: Image-FX → Whisk 인물 업로드 → Whisk 이미지 생성 → 다운로드
"""

import sys
import io
import time
import json
import os
import glob

# UTF-8 출력
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True, write_through=True)

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
import pyperclip

print("="*80, flush=True)
print("🚀 Image-FX → Whisk 완전 자동화", flush=True)
print("="*80, flush=True)

# JSON 파일 읽기
if len(sys.argv) < 2:
    print("사용법: python full_workflow.py <scenes.json>", flush=True)
    sys.exit(1)

with open(sys.argv[1], 'r', encoding='utf-8') as f:
    scenes = json.load(f)

print(f"📝 총 {len(scenes)}개 씬", flush=True)

# Chrome 연결
print("⏳ ChromeDriver 준비 중...", flush=True)
service = Service(ChromeDriverManager().install())
print("✅ ChromeDriver 준비 완료", flush=True)

chrome_options = Options()
chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(service=service, options=chrome_options)
print("✅ Chrome 연결 완료", flush=True)

# === 1단계: Image-FX에서 첫 이미지 생성 ===
print("\n" + "="*80, flush=True)
print("1️⃣ Image-FX - 첫 이미지 생성", flush=True)
print("="*80, flush=True)

first_prompt = scenes[0].get('image_prompt', '')
print(f"프롬프트: {first_prompt[:50]}...", flush=True)

driver.get('https://labs.google/fx/tools/image-fx')
print("⏳ 페이지 로딩...", flush=True)

# 페이지 로드 대기
for i in range(30):
    if driver.execute_script("return document.readyState") == "complete":
        print(f"✅ 로드 완료 ({i+1}초)", flush=True)
        break
    time.sleep(1)
time.sleep(5)

# 입력창 기다리기
print("🔍 입력창 찾는 중...", flush=True)
for i in range(30):
    if driver.execute_script("return document.querySelector('.fZKmcZ') !== null;"):
        print(f"✅ 입력창 발견 ({i+1}초)", flush=True)
        break
    if i % 5 == 0 and i > 0:
        print(f"   대기 중... ({i}초)", flush=True)
    time.sleep(1)

# 텍스트 입력
print(f"⌨️ 입력 중...", flush=True)
result = driver.execute_script("""
    const prompt = arguments[0];

    // 요소 찾기
    let elem = document.querySelector('.fZKmcZ') || document.querySelector('.sc-1004f4bc-4');
    if (!elem) {
        return {success: false, error: '요소를 찾을 수 없음'};
    }

    // 클릭 및 포커스
    elem.click();
    elem.focus();

    // 잠시 대기 후 다시 찾기 (React 재렌더링)
    setTimeout(() => {
        let inputElem = document.querySelector('.fZKmcZ') || document.querySelector('.sc-1004f4bc-4');
        if (inputElem) {
            inputElem.textContent = prompt;
            inputElem.innerText = prompt;
            inputElem.dispatchEvent(new Event('input', { bubbles: true }));
            inputElem.dispatchEvent(new Event('change', { bubbles: true }));
            inputElem.focus();
        }
    }, 200);

    return {success: true};
""", first_prompt)

if not result.get('success'):
    print(f"❌ {result.get('error')}", flush=True)
    sys.exit(1)

# setTimeout이 완료될 때까지 대기 (200ms + 여유)
time.sleep(0.5)
print("✅ 입력 완료", flush=True)

# Enter 키 전송 (ActionChains 사용)
print("⏎ Enter 입력 중...", flush=True)
try:
    actions = ActionChains(driver)
    actions.send_keys(Keys.RETURN).perform()
    print("✅ Enter 입력 완료", flush=True)
except Exception as e:
    print(f"❌ Enter 입력 실패: {e}", flush=True)
    # 실패해도 계속 진행 (이미지 생성이 시작되었을 수 있음)

time.sleep(1)

# 이미지 생성 대기
print("⏳ 이미지 생성 대기 중...", flush=True)
for i in range(60):  # 60초 대기
    # 이미지가 생성되었는지 확인
    has_image = driver.execute_script("""
        const imgs = Array.from(document.querySelectorAll('img'));
        const largeImgs = imgs.filter(img => img.offsetWidth > 300 && img.offsetHeight > 300);
        return largeImgs.length > 0;
    """)
    if has_image:
        print(f"✅ 이미지 생성 완료! ({i+1}초)", flush=True)
        break
    if i % 10 == 0 and i > 0:
        print(f"   대기 중... ({i}초)", flush=True)
    time.sleep(1)

time.sleep(3)

# 자동 다운로드 시도
print("\n📥 이미지 다운로드 시도 중...", flush=True)
download_success = False

try:
    # 다운로드 버튼 찾기 (여러 선택자 시도)
    download_button = None
    selectors = [
        'button[aria-label*="Download"]',
        'button[aria-label*="다운로드"]',
        '[aria-label*="Download"]',
        '[aria-label*="download"]',
        'button:has-text("Download")',
        'svg[aria-label*="Download"]',
    ]

    for selector in selectors:
        try:
            btn = driver.execute_script(f"""
                const btn = document.querySelector('{selector}');
                if (btn) {{
                    btn.click();
                    return true;
                }}
                return false;
            """)
            if btn:
                print(f"✅ 다운로드 버튼 클릭 성공: {selector}", flush=True)
                download_success = True
                break
        except:
            continue

    if download_success:
        print("⏳ 다운로드 완료 대기 (5초)...", flush=True)
        time.sleep(5)
except Exception as e:
    print(f"⚠️  자동 다운로드 실패: {e}", flush=True)

# 최근 다운로드 파일 찾기 (이미지 파일만)
download_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp')
files = []
for ext in image_extensions:
    files.extend(glob.glob(os.path.join(download_dir, f'*{ext}')))
    files.extend(glob.glob(os.path.join(download_dir, f'*{ext.upper()}')))

# .crdownload 파일 제외
files = [f for f in files if not f.endswith('.crdownload') and not f.endswith('.tmp')]
latest_file = max(files, key=os.path.getctime) if files else None

if not latest_file:
    print("❌ 자동 다운로드 실패, 수동으로 다운로드하세요", flush=True)
    print("⚠️  Image-FX에서 이미지를 수동으로 다운로드하세요!", flush=True)
    print("   다운로드 후 파일 전체 경로를 입력하세요: ", flush=True)
    try:
        latest_file = input().strip()
    except EOFError:
        print("❌ 입력 실패 (비대화형 모드)", flush=True)
        sys.exit(1)
else:
    print(f"✅ 이미지 다운로드 확인: {os.path.basename(latest_file)}", flush=True)

if not latest_file or not os.path.exists(latest_file):
    print(f"❌ 이미지 파일을 찾을 수 없음: {latest_file}", flush=True)
    sys.exit(1)

# === 2단계: Whisk 인물 업로드 ===
print("\n" + "="*80, flush=True)
print("2️⃣ Whisk - 인물 업로드", flush=True)
print("="*80, flush=True)

driver.get('https://labs.google/fx/ko/tools/whisk/project')
print("⏳ Whisk 페이지 로딩...", flush=True)
time.sleep(5)

# JavaScript로 file input 직접 생성 및 파일 할당
upload_success = False
abs_path = os.path.abspath(latest_file)
print(f"🔍 파일 업로드 시도: {os.path.basename(abs_path)}", flush=True)

# 먼저 hidden file input 생성
create_result = driver.execute_script("""
    // 숨겨진 file input 생성
    const input = document.createElement('input');
    input.type = 'file';
    input.id = 'auto-upload-input';
    input.accept = 'image/*';
    input.style.position = 'absolute';
    input.style.left = '-9999px';
    document.body.appendChild(input);

    return {success: true};
""")

print("✅ file input 생성 완료", flush=True)
time.sleep(1)

# 생성된 input 찾기
file_input = driver.find_element(By.ID, 'auto-upload-input')
if file_input:
    try:
        # 파일 할당
        print(f"📤 파일 할당 중...", flush=True)
        file_input.send_keys(abs_path)
        time.sleep(2)
        print("✅ 파일 할당 완료", flush=True)

        # change 이벤트 발생 및 파일 업로드 처리
        upload_result = driver.execute_script("""
            const input = document.getElementById('auto-upload-input');
            if (!input || !input.files || input.files.length === 0) {
                return {success: false, error: '파일이 할당되지 않음'};
            }

            const file = input.files[0];

            // change 이벤트 발생
            input.dispatchEvent(new Event('change', { bubbles: true }));

            // add_photo_alternate 버튼 찾기
            const findUploadButton = () => {
                const all = document.querySelectorAll('*');
                for (let elem of all) {
                    const text = elem.textContent || '';
                    if (elem.tagName === 'BUTTON' && text.includes('add_photo_alternate')) {
                        return elem;
                    }
                }
                return null;
            };

            const btn = findUploadButton();
            if (btn) {
                // 버튼의 이벤트 핸들러를 트리거하면서 파일 전달
                const clickEvent = new MouseEvent('click', {
                    bubbles: true,
                    cancelable: true
                });
                btn.dispatchEvent(clickEvent);
            }

            return {
                success: true,
                fileName: file.name,
                fileSize: file.size
            };
        """)

        if upload_result.get('success'):
            print(f"✅ 파일 업로드 성공!", flush=True)
            print(f"   파일명: {upload_result.get('fileName')}", flush=True)
            print(f"   파일 크기: {upload_result.get('fileSize')} bytes", flush=True)
            upload_success = True
            time.sleep(3)
        else:
            print(f"⚠️  업로드 실패: {upload_result.get('error')}", flush=True)

    except Exception as e:
        print(f"❌ 파일 할당 오류: {e}", flush=True)

if not upload_success:
    print("❌ 자동 업로드 실패", flush=True)
    print("⚠️  수동으로 파일을 업로드하세요:", flush=True)
    print(f"   {latest_file}", flush=True)
    print("   업로드 완료 후 Enter를 누르세요...", flush=True)
    try:
        input()
    except EOFError:
        print("⚠️  비대화형 모드 - 계속 진행합니다...", flush=True)
        time.sleep(3)

# === 3단계: Whisk 프롬프트 입력 ===
print("\n" + "="*80, flush=True)
print("3️⃣ Whisk - 프롬프트 입력", flush=True)
print("="*80, flush=True)

for i, scene in enumerate(scenes):
    prompt = scene.get('image_prompt', '')
    scene_num = f"scene_{str(i).zfill(2)}"

    if i >= 3:
        print(f"\n⏳ {scene_num} - 15초 대기...", flush=True)
        time.sleep(15)
    elif i == 2:
        print(f"\n⏳ {scene_num} - 2초 대기...", flush=True)
        time.sleep(2)
    elif i == 1:
        time.sleep(0.5)

    print(f"\n📌 {scene_num}", flush=True)
    pyperclip.copy(prompt)
    print(f"   클립보드: {prompt[:40]}...", flush=True)

    # Ctrl+A, Ctrl+V, Enter
    driver.find_element(By.TAG_NAME, 'body').click()
    time.sleep(0.2)
    driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.CONTROL, 'a')
    time.sleep(0.2)
    driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.CONTROL, 'v')
    time.sleep(0.3)
    driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.RETURN)
    print("   ✅ 입력 완료", flush=True)
    time.sleep(2)

print("\n✅ 모든 프롬프트 입력 완료!", flush=True)

# === 4단계: 이미지 생성 대기 ===
print("\n" + "="*80, flush=True)
print("4️⃣ 이미지 생성 대기", flush=True)
print("="*80, flush=True)

print("⏳ 이미지 생성 중... (최대 120초)", flush=True)
for i in range(120):
    generating = driver.execute_script("""
        const text = document.body.innerText;
        return text.includes('Generating') || text.includes('생성 중');
    """)
    if not generating:
        print(f"✅ 생성 완료! ({i+1}초)", flush=True)
        break
    if i % 10 == 0 and i > 0:
        print(f"   대기 중... ({i}초)", flush=True)
    time.sleep(1)

time.sleep(3)

# === 5단계: 이미지 다운로드 ===
print("\n" + "="*80, flush=True)
print("5️⃣ 이미지 다운로드", flush=True)
print("="*80, flush=True)

json_dir = os.path.dirname(os.path.abspath(sys.argv[1]))
output_folder = os.path.join(json_dir, 'images')
os.makedirs(output_folder, exist_ok=True)
print(f"📁 저장 폴더: {output_folder}", flush=True)

# 페이지의 모든 이미지 찾기
images = driver.execute_script("""
    const imgs = Array.from(document.querySelectorAll('img'));
    return imgs
        .filter(img => img.offsetWidth > 200 && img.offsetHeight > 200)
        .map(img => img.src);
""")

print(f"🔍 발견된 이미지: {len(images)}개", flush=True)

import requests
downloaded = []
for i, img_src in enumerate(images[:len(scenes)]):
    if not img_src.startswith('http'):
        continue

    scene_num = f"scene_{str(i).zfill(2)}"
    ext = '.jpg'
    if 'png' in img_src.lower():
        ext = '.png'
    elif 'webp' in img_src.lower():
        ext = '.webp'

    output_path = os.path.join(output_folder, f"{scene_num}{ext}")

    try:
        response = requests.get(img_src, timeout=30)
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(response.content)
            downloaded.append(output_path)
            print(f"   ✅ {scene_num}{ext}", flush=True)
    except Exception as e:
        print(f"   ❌ {scene_num}: {e}", flush=True)

print(f"\n✅ 다운로드 완료: {len(downloaded)}/{len(scenes)}", flush=True)
print(f"📁 저장 위치: {output_folder}", flush=True)

print("\n" + "="*80, flush=True)
print("🎉 전체 워크플로우 완료!", flush=True)
print("="*80, flush=True)
