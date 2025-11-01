"""
Claude.ai를 자동으로 열고 프롬프트를 붙여넣어서 전송하는 스크립트
multi-ai-aggregator의 main.py 로직 기반
"""
import asyncio
import sys
import json
import os
import pathlib
from playwright.async_api import async_playwright

async def open_claude_with_prompt(prompt_text: str):
    """Claude.ai를 열고 프롬프트를 자동으로 입력/전송"""
    # automation profile 사용 (main.py와 동일)
    automation_profile = os.path.join(os.getcwd(), '.chrome-automation-profile-claude')
    pathlib.Path(automation_profile).mkdir(exist_ok=True)

    print(f"[INFO] Chrome 프로필 사용: {automation_profile}")
    print(f"[INFO] 저장된 로그인 세션 사용 (로그인 안 되어 있으면 수동 로그인 필요)")

    p = await async_playwright().start()
    try:
        # Chrome 실행 (main.py와 동일한 설정)
        context = await p.chromium.launch_persistent_context(
            automation_profile,
            headless=False,
            channel='chrome',
            args=[
                '--start-maximized',
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-features=IsolateOrigins,site-per-process',
                '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            ],
            accept_downloads=True,
            ignore_https_errors=True,
            timeout=60000,
            viewport=None  # 최대화
        )

        # navigator.webdriver 숨기기
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        # 페이지 가져오기
        if len(context.pages) > 0:
            page = context.pages[0]
        else:
            page = await context.new_page()

        print("[INFO] Claude.ai 접속 중...")
        await page.goto('https://claude.ai/new', timeout=60000)
        await asyncio.sleep(3)

        # 로그인 확인
        current_url = page.url
        if 'login' in current_url or 'auth' in current_url:
            print("\n" + "="*60)
            print("  [WAIT] 로그인이 필요합니다!")
            print("  브라우저에서 Claude.ai 로그인을 완료해주세요.")
            print("  로그인 후 다음부터는 자동 로그인됩니다.")
            print("  최대 5분 대기합니다...")
            print("="*60 + "\n")

            # 로그인 완료 대기
            for i in range(60):
                await asyncio.sleep(5)
                if not page.is_closed():
                    current_url = page.url
                    if 'login' not in current_url and 'auth' not in current_url:
                        print("[INFO] ✅ 로그인 완료!")
                        await asyncio.sleep(3)
                        break
            else:
                print("[ERROR] 로그인 시간 초과")
                return False

        print("[INFO] 프롬프트 입력 창 찾는 중...")
        await asyncio.sleep(2)

        # 입력 창 찾기
        selectors = [
            'div[contenteditable="true"]',
            'textarea',
            '[role="textbox"]',
            '.ProseMirror',
            'div.ProseMirror'
        ]

        input_element = None
        for selector in selectors:
            try:
                input_element = await page.wait_for_selector(selector, timeout=5000)
                if input_element:
                    print(f"[INFO] 입력 창 발견: {selector}")
                    break
            except:
                continue

        if not input_element:
            print("[ERROR] 입력 창을 찾을 수 없습니다.")
            return False

        # 입력 창 클릭 및 포커스
        await input_element.click()
        await asyncio.sleep(0.5)

        print("[INFO] 프롬프트 입력 중...")
        # 프롬프트 한꺼번에 붙여넣기
        await input_element.fill(prompt_text)
        await asyncio.sleep(1)

        print("[INFO] 전송 중...")
        # Enter 키로 전송
        await page.keyboard.press('Enter')
        await asyncio.sleep(1)

        print("\n" + "="*60)
        print("  ✅ 프롬프트 전송 완료!")
        print("  Claude의 응답을 기다립니다...")
        print("  브라우저는 열린 상태로 유지됩니다.")
        print("  작업이 끝나면 브라우저를 닫아주세요.")
        print("  (브라우저 닫으면 이 창도 자동으로 닫힙니다)")
        print("="*60 + "\n")

        # 브라우저를 계속 열어두기 - 브라우저가 닫히면 종료
        try:
            # 무한 루프로 대기 (브라우저가 닫히기를 감지)
            while True:
                await asyncio.sleep(2)  # 2초마다 체크 (빠른 응답)
                # 브라우저나 페이지가 닫혔는지 확인
                try:
                    if page.is_closed():
                        print("\n[INFO] 🚪 브라우저가 닫혔습니다.")
                        print("[INFO] 👋 스크립트를 종료합니다...")
                        break
                except:
                    # context가 닫혔을 수도 있음
                    print("\n[INFO] 🚪 브라우저 세션이 종료되었습니다.")
                    print("[INFO] 👋 스크립트를 종료합니다...")
                    break
        except KeyboardInterrupt:
            print("\n[INFO] ⚠️ 사용자가 중단했습니다. (Ctrl+C)")
        except Exception as e:
            print(f"\n[INFO] 대기 중 예외 발생: {e}")

        print("[INFO] ✅ 정상 종료")
        return True

    except Exception as e:
        print(f"[ERROR] 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Playwright를 명시적으로 닫지 않음 - 브라우저 유지
        pass

if __name__ == "__main__":
    prompt = None

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        # @ 로 시작하면 파일에서 읽기
        if arg.startswith('@'):
            file_path = arg[1:]
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    prompt = f.read()
                print(f"[INFO] 파일에서 프롬프트 읽기: {file_path}")
            except Exception as e:
                print(json.dumps({"success": False, "error": f"파일 읽기 실패: {e}"}))
                sys.exit(1)
        else:
            prompt = arg
    else:
        try:
            data = json.loads(sys.stdin.read())
            prompt = data.get('prompt', '')
        except:
            print(json.dumps({"success": False, "error": "프롬프트를 찾을 수 없습니다."}))
            sys.exit(1)

    if not prompt:
        print(json.dumps({"success": False, "error": "프롬프트가 비어있습니다."}))
        sys.exit(1)

    result = asyncio.run(open_claude_with_prompt(prompt))

    if result:
        print(json.dumps({"success": True, "message": "프롬프트 전송 완료"}))
        sys.exit(0)
    else:
        print(json.dumps({"success": False, "error": "프롬프트 전송 실패"}))
        sys.exit(1)
