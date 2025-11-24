# -*- coding: utf-8 -*-
"""
향상된 이미지 크롤링 자동화 스크립트
Whisk로 프롬프트당 2개 이미지를 생성하고 선택하는 기능 포함
"""

import sys
import time
import json
import os
import glob
import argparse
import io
import requests
import base64
from datetime import datetime

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

# 전역 설정
WAIT_BETWEEN_PROMPTS = 10  # 프롬프트 간 대기 시간
IMAGES_PER_PROMPT = 2  # 프롬프트당 생성할 이미지 수

def setup_driver():
    """Chrome 드라이버 설정"""
    print("🔧 Chrome 드라이버 설정 중...", flush=True)

    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    try:
        driver = webdriver.Chrome(options=chrome_options)
        print("✅ Chrome 드라이버 연결 성공", flush=True)
        return driver
    except Exception as e:
        print(f"❌ Chrome 드라이버 연결 실패: {e}", flush=True)
        raise

def navigate_to_whisk(driver):
    """Whisk 페이지로 이동"""
    print("🌐 Whisk 페이지로 이동 중...", flush=True)
    driver.get("https://labs.google/whisk")
    time.sleep(5)

    # 페이지 로드 확인
    try:
        WebDriverWait(driver, 20).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        print("✅ Whisk 페이지 로드 완료", flush=True)
    except Exception as e:
        print(f"⚠️ 페이지 로드 대기 중 타임아웃: {e}", flush=True)

def clear_whisk_state(driver):
    """Whisk 상태 초기화"""
    print("🧹 Whisk 상태 초기화 중...", flush=True)

    try:
        # 새로고침으로 초기화
        driver.refresh()
        time.sleep(5)

        # 기존 이미지 제거 시도
        driver.execute_script("""
            // 모든 생성된 이미지 컨테이너 제거
            const containers = document.querySelectorAll('[data-image-container], .image-result, .generated-image');
            containers.forEach(c => c.remove());

            // 프롬프트 입력 필드 초기화
            const inputs = document.querySelectorAll('textarea, input[type="text"]');
            inputs.forEach(input => {
                input.value = '';
                input.dispatchEvent(new Event('input', {bubbles: true}));
            });
        """)

        print("✅ Whisk 상태 초기화 완료", flush=True)
    except Exception as e:
        print(f"⚠️ 초기화 중 오류: {e}", flush=True)

def submit_prompt_and_generate(driver, prompt, scene_number):
    """프롬프트를 제출하고 2개의 이미지 variation 생성"""
    print(f"\n📝 씬 {scene_number}: 프롬프트 입력 중...", flush=True)
    print(f"   프롬프트: {prompt[:100]}...", flush=True)

    results = []

    # 프롬프트당 2개 이미지 생성
    for variation_idx in range(IMAGES_PER_PROMPT):
        print(f"\n   🎨 Variation {variation_idx + 1}/{IMAGES_PER_PROMPT} 생성 중...", flush=True)

        # 프롬프트 입력
        prompt_input = find_prompt_input(driver)
        if not prompt_input:
            print(f"   ❌ 프롬프트 입력 필드를 찾을 수 없습니다", flush=True)
            continue

        # 기존 텍스트 지우고 새 프롬프트 입력
        prompt_input.clear()
        time.sleep(1)

        # variation을 위한 프롬프트 수정
        modified_prompt = prompt
        if variation_idx > 0:
            modified_prompt = f"{prompt}, variation {variation_idx + 1}, different style"

        prompt_input.send_keys(modified_prompt)
        time.sleep(1)

        # Generate 버튼 클릭 또는 Enter 키 전송
        if not click_generate_button(driver):
            prompt_input.send_keys(Keys.RETURN)

        # 이미지 생성 대기
        print(f"   ⏳ 이미지 생성 대기 중... (최대 60초)", flush=True)
        image_url = wait_for_image_generation(driver, timeout=60)

        if image_url:
            print(f"   ✅ Variation {variation_idx + 1} 생성 완료", flush=True)
            results.append({
                'variation': variation_idx + 1,
                'url': image_url,
                'timestamp': datetime.now().isoformat()
            })
        else:
            print(f"   ❌ Variation {variation_idx + 1} 생성 실패", flush=True)

        # variation 간 대기
        if variation_idx < IMAGES_PER_PROMPT - 1:
            time.sleep(5)

    return results

def find_prompt_input(driver):
    """프롬프트 입력 필드 찾기"""
    try:
        # 여러 방법으로 입력 필드 찾기
        selectors = [
            'textarea[placeholder*="prompt"]',
            'textarea[placeholder*="describe"]',
            'textarea[placeholder*="입력"]',
            'textarea[aria-label*="prompt"]',
            'textarea',
            'input[type="text"][placeholder*="prompt"]'
        ]

        for selector in selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                return elements[0]

        # JavaScript로 찾기
        input_elem = driver.execute_script("""
            const textareas = Array.from(document.querySelectorAll('textarea'));
            const inputs = Array.from(document.querySelectorAll('input[type="text"]'));
            const allInputs = [...textareas, ...inputs];

            // 보이는 입력 필드 찾기
            for (const elem of allInputs) {
                if (elem.offsetParent !== null && elem.offsetWidth > 100) {
                    return elem;
                }
            }
            return null;
        """)

        return input_elem

    except Exception as e:
        print(f"⚠️ 프롬프트 입력 필드 검색 실패: {e}", flush=True)
        return None

def click_generate_button(driver):
    """Generate 버튼 클릭"""
    try:
        # 버튼 찾기
        button_selectors = [
            'button:contains("Generate")',
            'button:contains("생성")',
            'button:contains("Create")',
            'button[aria-label*="generate"]'
        ]

        button = driver.execute_script("""
            const buttons = Array.from(document.querySelectorAll('button'));
            for (const btn of buttons) {
                const text = btn.textContent.toLowerCase();
                if (text.includes('generate') || text.includes('생성') ||
                    text.includes('create') || text.includes('make')) {
                    btn.click();
                    return true;
                }
            }
            return false;
        """)

        return button

    except Exception as e:
        print(f"⚠️ Generate 버튼 클릭 실패: {e}", flush=True)
        return False

def wait_for_image_generation(driver, timeout=60):
    """이미지 생성 완료 대기 및 URL 반환"""
    start_time = time.time()
    last_image_url = None

    while time.time() - start_time < timeout:
        try:
            # 생성된 이미지 찾기
            image_data = driver.execute_script("""
                const imgs = Array.from(document.querySelectorAll('img'));

                // 큰 이미지만 필터링 (생성된 이미지)
                const largeImgs = imgs.filter(img => {
                    if (img.offsetWidth < 200 || img.offsetHeight < 200) return false;
                    const src = img.src || '';
                    if (src.startsWith('data:image/svg')) return false;  // SVG 아이콘 제외
                    if (src.includes('logo') || src.includes('icon')) return false;
                    return src.startsWith('http') || src.startsWith('blob:');
                });

                // 가장 최근 이미지 (마지막 요소)
                if (largeImgs.length > 0) {
                    const latestImg = largeImgs[largeImgs.length - 1];
                    return {
                        url: latestImg.src,
                        width: latestImg.offsetWidth,
                        height: latestImg.offsetHeight,
                        count: largeImgs.length
                    };
                }

                return null;
            """)

            if image_data and image_data['url'] != last_image_url:
                last_image_url = image_data['url']
                print(f"   🖼️ 새 이미지 감지: {image_data['width']}x{image_data['height']}", flush=True)
                time.sleep(3)  # 이미지 완전 로드 대기
                return image_data['url']

        except Exception as e:
            print(f"   ⚠️ 이미지 확인 중 오류: {e}", flush=True)

        time.sleep(2)

    return None

def select_best_image(variations):
    """여러 variation 중 최적의 이미지 선택"""
    if not variations:
        return None

    print(f"\n🎯 {len(variations)}개 variation 중 최적 이미지 선택 중...", flush=True)

    # 간단한 선택 로직: 첫 번째 성공한 이미지 선택
    # 향후 이미지 품질 평가 로직 추가 가능
    for idx, var in enumerate(variations):
        if var.get('url'):
            print(f"   ✅ Variation {var['variation']} 선택", flush=True)
            return var

    return None

def download_image(url, output_path):
    """이미지 다운로드 및 저장"""
    try:
        print(f"   📥 이미지 다운로드 중: {output_path}", flush=True)

        if url.startswith('blob:'):
            # blob URL은 브라우저 내에서만 유효하므로 별도 처리 필요
            print(f"   ⚠️ Blob URL은 직접 다운로드 불가", flush=True)
            return False

        response = requests.get(url, timeout=30, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://labs.google/'
        })

        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(response.content)
            print(f"   ✅ 저장 완료: {os.path.basename(output_path)}", flush=True)
            return True
        else:
            print(f"   ❌ 다운로드 실패: HTTP {response.status_code}", flush=True)
            return False

    except Exception as e:
        print(f"   ❌ 다운로드 오류: {e}", flush=True)
        return False

def download_blob_image(driver, blob_url, output_path):
    """Blob URL 이미지를 Base64로 변환하여 저장"""
    try:
        print(f"   📥 Blob 이미지 다운로드 중: {output_path}", flush=True)

        # Blob을 Base64로 변환
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
                    })
                    .catch(reject);
            });
        """, blob_url)

        if base64_data and base64_data.startswith('data:image'):
            # Base64 데이터 파싱
            header, base64_str = base64_data.split(',', 1)
            image_bytes = base64.b64decode(base64_str)

            # 파일 저장
            with open(output_path, 'wb') as f:
                f.write(image_bytes)

            print(f"   ✅ Blob 이미지 저장 완료: {os.path.basename(output_path)}", flush=True)
            return True
        else:
            print(f"   ❌ Blob 데이터 변환 실패", flush=True)
            return False

    except Exception as e:
        print(f"   ❌ Blob 다운로드 오류: {e}", flush=True)
        return False

def process_scenes(driver, scenes, output_dir):
    """모든 씬 처리"""
    print(f"\n{'='*80}", flush=True)
    print(f"🎬 총 {len(scenes)}개 씬 처리 시작", flush=True)
    print(f"   출력 폴더: {output_dir}", flush=True)
    print(f"   프롬프트당 이미지: {IMAGES_PER_PROMPT}개", flush=True)
    print(f"{'='*80}", flush=True)

    results = []

    for idx, scene in enumerate(scenes):
        scene_number = scene.get('scene_number', idx + 1)
        image_prompt = scene.get('image_prompt', '')

        if not image_prompt:
            print(f"\n⚠️ 씬 {scene_number}: image_prompt가 없습니다. 건너뜁니다.", flush=True)
            continue

        print(f"\n{'='*60}", flush=True)
        print(f"📍 씬 {scene_number}/{len(scenes)} 처리 중", flush=True)
        print(f"{'='*60}", flush=True)

        # Whisk 상태 초기화 (매 씬마다)
        if idx > 0:
            clear_whisk_state(driver)

        # 프롬프트 제출 및 variations 생성
        variations = submit_prompt_and_generate(driver, image_prompt, scene_number)

        # 최적 이미지 선택
        best_image = select_best_image(variations)

        if best_image:
            # 이미지 저장
            output_filename = f"scene_{str(scene_number).zfill(2)}.jpg"
            output_path = os.path.join(output_dir, output_filename)

            # URL 타입에 따라 다른 다운로드 방법 사용
            if best_image['url'].startswith('blob:'):
                success = download_blob_image(driver, best_image['url'], output_path)
            else:
                success = download_image(best_image['url'], output_path)

            if success:
                results.append({
                    'scene': scene_number,
                    'path': output_path,
                    'variations_generated': len(variations)
                })

        # 씬 간 대기
        if idx < len(scenes) - 1:
            print(f"\n⏳ 다음 씬까지 {WAIT_BETWEEN_PROMPTS}초 대기...", flush=True)
            time.sleep(WAIT_BETWEEN_PROMPTS)

    return results

def main():
    """메인 실행 함수"""
    parser = argparse.ArgumentParser(description='Enhanced Image Crawler for Whisk')
    parser.add_argument('scenes_file', help='Path to scenes JSON file')
    parser.add_argument('--output-dir', help='Output directory for images')
    parser.add_argument('--images-per-prompt', type=int, default=2, help='Number of images per prompt')

    args = parser.parse_args()

    # scenes 파일 읽기
    try:
        with open(args.scenes_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            scenes = data.get('scenes', data) if isinstance(data, dict) else data
    except Exception as e:
        print(f"❌ scenes 파일 읽기 실패: {e}", flush=True)
        sys.exit(1)

    # 출력 디렉토리 설정
    if args.output_dir:
        output_dir = args.output_dir
    else:
        # 기본 출력 디렉토리
        project_id = f"project_{int(time.time())}"
        output_dir = os.path.join(os.path.dirname(args.scenes_file), '..', 'input', project_id)

    # 출력 디렉토리 생성
    os.makedirs(output_dir, exist_ok=True)
    print(f"📁 출력 디렉토리: {output_dir}", flush=True)

    # 이미지 수 설정
    global IMAGES_PER_PROMPT
    IMAGES_PER_PROMPT = args.images_per_prompt

    # 드라이버 설정
    driver = setup_driver()

    try:
        # Whisk로 이동
        navigate_to_whisk(driver)

        # 씬 처리
        results = process_scenes(driver, scenes, output_dir)

        # 결과 요약
        print(f"\n{'='*80}", flush=True)
        print(f"✅ 이미지 크롤링 완료!", flush=True)
        print(f"   성공: {len(results)}/{len(scenes)} 씬", flush=True)
        print(f"   출력 폴더: {output_dir}", flush=True)
        print(f"{'='*80}", flush=True)

        # 결과 JSON 저장
        result_file = os.path.join(output_dir, 'crawling_results.json')
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump({
                'success': True,
                'total_scenes': len(scenes),
                'processed': len(results),
                'results': results,
                'timestamp': datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)

    except Exception as e:
        print(f"❌ 크롤링 중 오류 발생: {e}", flush=True)
        sys.exit(1)

    finally:
        print("\n🔚 브라우저 종료", flush=True)
        # driver.quit()  # 디버그 모드에서는 브라우저 유지

if __name__ == "__main__":
    main()