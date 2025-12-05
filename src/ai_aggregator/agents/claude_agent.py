from .base_agent import BaseAgent
import asyncio
# BTS-3186: subprocess, sys, os 더 이상 사용 안 함 (setup_login.py 호출 제거)


def ensure_claude_login() -> bool:
    """
    Claude.ai 로그인 세션 확인 및 수동 로그인 안내

    BTS-3186: setup_login.py 별도 실행 대신 기존 브라우저에서 로그인 대기
    (Chrome 프로필 lockfile 충돌 방지)

    Returns:
        bool: 항상 False 반환 (main.py에서 대기 처리)
    """
    print("[Claude] ⚠️  Claude.ai 세션이 만료되었습니다.")
    print("[Claude] 🌐 브라우저 창에서 직접 로그인해주세요.")
    print("[Claude] 💡 로그인 후 자동으로 재시도됩니다. (60초 대기)")

    # BTS-3186: setup_login.py 별도 실행 제거
    # main.py가 이미 Chrome 프로필을 사용 중이므로 setup_login.py를 실행하면
    # WinError 32 (다른 프로세스가 파일을 사용 중) 에러 발생
    # 대신 main.py의 60초 대기 로직에서 수동 로그인을 기다림

    return False  # main.py에서 대기 후 재시도하도록


class ClaudeAgent(BaseAgent):
    """Claude automation agent"""

    def get_name(self) -> str:
        return "Claude"

    def get_url(self) -> str:
        return "https://claude.ai/"

    async def login(self):
        """Claude login handling"""
        if self.skip_login_check:
            print(f"[{self.get_name()}] Skipping login check (assuming already logged in)")
            return

        print(f"[{self.get_name()}] Waiting for page to load...")
        await asyncio.sleep(3)  # BTS-3153: 페이지 로딩 대기 시간 증가 (1.5s -> 3s)

        try:
            # 로그인 페이지 감지 - 로그인 버튼 또는 텍스트 확인
            page_content = await self.page.content()
            login_indicators = [
                'Continue with Google',
                'Continue with email',
                'Continue with SSO',
                'Sign in',
                'Log in',
                'Login to Claude'
            ]

            is_login_page = any(indicator in page_content for indicator in login_indicators)

            if is_login_page:
                print(f"[{self.get_name()}] [WARN] Login page detected!")
                # ⭐ BTS-0000048: 자동 재로그인 프롬프트
                if ensure_claude_login():
                    print(f"[{self.get_name()}] Retrying login check after re-login...")
                    # 페이지 새로고침 후 다시 확인
                    await self.page.reload(wait_until='load')
                    await asyncio.sleep(3)  # BTS-3153: 대기 시간 증가
                    # 로그인 후 다시 확인 (재귀 호출 방지를 위해 skip_login_check 설정)
                    original_skip = self.skip_login_check
                    self.skip_login_check = True
                    try:
                        # 로그인 확인만 하고 넘어감
                        page_content = await self.page.content()
                        if any(indicator in page_content for indicator in login_indicators):
                            raise Exception("Claude.ai login still required after re-login attempt")
                    finally:
                        self.skip_login_check = original_skip
                else:
                    raise Exception("Claude.ai login required. Please run setup_login.py first to save your session.")

            # BTS-3153: 2025년 Claude UI 변경에 대응하는 확장된 셀렉터 목록
            selectors = [
                'div[contenteditable="true"]',
                '[contenteditable="true"]',
                'textarea',
                'div[role="textbox"]',
                # 2025년 Claude UI 추가 셀렉터
                'div.ProseMirror',  # ProseMirror 에디터
                '[data-placeholder]',  # placeholder 속성이 있는 입력 필드
                'div[class*="input"]',  # input 클래스 포함
                'div[class*="composer"]',  # composer 클래스 포함
                'fieldset div[contenteditable]',  # fieldset 내부 contenteditable
                'form div[contenteditable]',  # form 내부 contenteditable
            ]

            found = False
            for selector in selectors:
                try:
                    await self.page.wait_for_selector(selector, timeout=3000)
                    print(f"[{self.get_name()}] Already logged in (found: {selector})")
                    found = True
                    break
                except:
                    continue

            if not found:
                # BTS-3153: 입력 필드가 없으면 먼저 추가 대기 후 재시도
                print(f"[{self.get_name()}] [WARN] Input field not found - waiting for page to fully load...")
                await asyncio.sleep(3)  # 추가 대기

                # 재시도
                for selector in selectors:
                    try:
                        await self.page.wait_for_selector(selector, timeout=3000)
                        print(f"[{self.get_name()}] Found input after additional wait: {selector}")
                        found = True
                        break
                    except:
                        continue

            if not found:
                print(f"[{self.get_name()}] [WARN] Input field still not found - attempting re-login...")
                # ⭐ BTS-0000048: 자동 재로그인 프롬프트
                if ensure_claude_login():
                    print(f"[{self.get_name()}] Retrying after re-login...")
                    # 페이지 새로고침 후 다시 확인
                    await self.page.reload(wait_until='load')
                    await asyncio.sleep(4)  # BTS-3153: 대기 시간 증가
                    # 입력 필드 다시 찾기 (한 번만 시도)
                    for selector in selectors:
                        try:
                            await self.page.wait_for_selector(selector, timeout=5000)
                            print(f"[{self.get_name()}] Found input after re-login: {selector}")
                            found = True
                            break
                        except:
                            continue
                    if not found:
                        # BTS-3153: 디버깅을 위해 현재 페이지 URL과 상태 로그
                        current_url = self.page.url
                        print(f"[{self.get_name()}] [DEBUG] Current URL: {current_url}")
                        try:
                            await self.page.screenshot(path='claude_login_debug.png')
                            print(f"[{self.get_name()}] [DEBUG] Screenshot saved: claude_login_debug.png")
                        except:
                            pass
                        raise Exception(f"Claude.ai login still required after re-login attempt - Input field not found (URL: {current_url})")
                else:
                    raise Exception("Claude.ai login required. Please run setup_login.py first to save your session.")

        except Exception as e:
            print(f"[{self.get_name()}] Login check error: {str(e)}")
            raise  # 로그인 실패 시 예외를 상위로 전달

    async def _send_question_only(self, question: str):
        """Just send the question without waiting for response"""
        try:
            # BTS-3153: 2025년 Claude UI 변경에 대응하는 확장된 셀렉터 목록
            input_field = None
            selectors = [
                'div[contenteditable="true"]',
                '[contenteditable="true"]',
                'div[role="textbox"]',
                # 2025년 Claude UI 추가 셀렉터
                'div.ProseMirror',  # ProseMirror 에디터
                '[data-placeholder]',  # placeholder 속성이 있는 입력 필드
                'div[class*="input"]',  # input 클래스 포함
                'div[class*="composer"]',  # composer 클래스 포함
                'fieldset div[contenteditable]',  # fieldset 내부 contenteditable
                'form div[contenteditable]',  # form 내부 contenteditable
            ]

            for selector in selectors:
                try:
                    input_field = await self.page.wait_for_selector(selector, timeout=5000)
                    if input_field:
                        print(f"[{self.get_name()}] Found input field: {selector}")
                        break
                except:
                    continue

            if not input_field:
                raise Exception("Could not find Claude input field - selectors may need update")

            # Type the question using clipboard paste (faster and more reliable)
            print(f"[{self.get_name()}] Copying question to clipboard and pasting...")
            await input_field.click()
            await asyncio.sleep(0.3)

            # Use Playwright's evaluate to copy to clipboard and paste
            # This is more reliable than typing character by character
            try:
                # Set clipboard content using CDP (Chrome DevTools Protocol)
                await self.page.evaluate("""
                    (text) => {
                        navigator.clipboard.writeText(text);
                    }
                """, question)
                await asyncio.sleep(0.2)

                # Paste using Ctrl+V
                await self.page.keyboard.press('Control+KeyV')
                await asyncio.sleep(0.5)
                print(f"[{self.get_name()}] Text pasted successfully")
            except Exception as e:
                # Fallback to typing if clipboard doesn't work
                error_msg = str(e).encode('utf-8', errors='replace').decode('utf-8', errors='replace')
                print(f"[{self.get_name()}] Clipboard paste failed, falling back to typing: {error_msg}")
                await self.page.keyboard.type(question, delay=10)
                await asyncio.sleep(0.5)

            print(f"[{self.get_name()}] Sending with Enter key...")

            # Try different Enter key combinations
            sent = False

            # Method 1: Simple Enter
            try:
                print(f"[{self.get_name()}] Trying Enter...")
                await self.page.keyboard.press('Enter')
                await asyncio.sleep(1)
                # Don't check text_after since element may detach - just assume it worked
                print(f"[{self.get_name()}] Enter pressed")
                sent = True
            except Exception as e:
                # Safely encode error message to avoid cp949 errors
                error_msg = str(e).encode('utf-8', errors='replace').decode('utf-8', errors='replace')
                print(f"[{self.get_name()}] Enter failed: {error_msg}")

            # Method 2: Click Send button (fallback)
            if not sent:
                print(f"[{self.get_name()}] Trying to find and click Send button...")
                try:
                    # Try to find send button by various selectors
                    send_button_selectors = [
                        'button[aria-label*="Send"]',
                        'button[aria-label*="전송"]',
                        'button:has-text("Send")',
                        'button:has-text("전송")',
                    ]

                    for selector in send_button_selectors:
                        try:
                            send_btn = await self.page.wait_for_selector(selector, timeout=2000)
                            if send_btn:
                                await send_btn.click()
                                print(f"[{self.get_name()}] Send button clicked with selector: {selector}")
                                sent = True
                                break
                        except:
                            continue

                except Exception as e:
                    # Safely encode error message to avoid cp949 errors
                    error_msg = str(e).encode('utf-8', errors='replace').decode('utf-8', errors='replace')
                    print(f"[{self.get_name()}] Button click failed: {error_msg}")

            if not sent:
                print(f"[{self.get_name()}] Warning: Could not confirm message send, but continuing...")

        except Exception as e:
            # Safely encode error message to avoid cp949 errors
            error_msg = str(e).encode('utf-8', errors='replace').decode('utf-8', errors='replace')
            error_msg = f"Error sending question: {error_msg}"
            print(f"[{self.get_name()}] {error_msg}")
            raise Exception(error_msg)

    async def _click_continue_button_if_exists(self) -> bool:
        """
        "계속하기" / "Continue generating" 버튼이 있으면 클릭
        Returns: True if button was clicked, False otherwise

        SPEC-1764747483348: Chrome 자동화에서 Claude "계속하기" 버튼 자동 클릭
        """
        continue_button_selectors = [
            # 한국어 버튼
            'button:has-text("계속")',
            'button:has-text("계속하기")',
            'button:has-text("계속 생성")',
            # 영어 버튼
            'button:has-text("Continue")',
            'button:has-text("Continue generating")',
            # aria-label 기반
            'button[aria-label*="Continue"]',
            'button[aria-label*="계속"]',
            # class 기반 (Claude UI에서 자주 사용되는 패턴)
            'button.continue-button',
            'button[class*="continue"]',
        ]

        for selector in continue_button_selectors:
            try:
                btn = await self.page.query_selector(selector)
                if btn:
                    is_visible = await btn.is_visible()
                    if is_visible:
                        print(f"[{self.get_name()}] 🔄 '계속하기' 버튼 발견! 클릭합니다...")
                        await btn.click()
                        await asyncio.sleep(2)  # 클릭 후 응답 재개 대기
                        print(f"[{self.get_name()}] ✅ '계속하기' 버튼 클릭 완료")
                        return True
            except Exception as e:
                # 버튼 찾기 실패는 무시 (정상 상황일 수 있음)
                continue

        return False

    async def wait_for_complete_response(self) -> str:
        """Wait for Claude to complete its response"""
        try:
            # Wait for response to start
            print(f"[{self.get_name()}] Waiting for response to start...")
            await asyncio.sleep(2)

            # Wait for response to complete by checking for stop button disappearing
            print(f"[{self.get_name()}] Waiting for Claude to finish typing...")
            max_wait = 3600  # Maximum 60 minutes (1 hour) for very long responses
            waited = 0
            last_length = 0
            stable_count = 0
            continue_click_count = 0  # 계속하기 버튼 클릭 횟수 추적

            while waited < max_wait:
                try:
                    # Check if stop button exists (Claude is still typing)
                    stop_button = await self.page.query_selector('button[aria-label*="Stop"]')

                    if not stop_button:
                        # SPEC-1764747483348: "계속하기" 버튼 체크 (5초마다)
                        if waited % 5 == 0:
                            if await self._click_continue_button_if_exists():
                                continue_click_count += 1
                                stable_count = 0  # 계속하기 클릭 후 안정화 카운터 리셋
                                last_length = 0
                                continue  # 응답 재개, 다시 대기

                        # No stop button, might be done - check if text is stable
                        try:
                            messages = await self.page.query_selector_all('[data-test-render-count]')
                            if messages and len(messages) > 0:
                                current_text = await messages[-1].inner_text()
                                current_length = len(current_text)

                                if current_length == last_length and current_length > 0:
                                    stable_count += 1
                                    if stable_count >= 5:  # Stable for 5 seconds to be sure
                                        # 마지막으로 계속하기 버튼 한 번 더 체크
                                        if not await self._click_continue_button_if_exists():
                                            print(f"[{self.get_name()}] Response completed! (계속하기 버튼 {continue_click_count}회 클릭)")
                                            break
                                        else:
                                            continue_click_count += 1
                                            stable_count = 0
                                            last_length = 0
                                            continue
                                else:
                                    stable_count = 0
                                    last_length = current_length
                        except:
                            pass
                except Exception as e:
                    error_str = str(e)
                    # Handle browser/page closed errors - stop immediately
                    if "has been closed" in error_str or "closed" in error_str.lower():
                        print(f"[{self.get_name()}] [ERROR] Browser or page has been closed. Stopping...")
                        self.response = "Browser closed by user"
                        return self.response
                    # Handle navigation/context destruction errors
                    elif "Execution context was destroyed" in error_str or "navigation" in error_str.lower():
                        print(f"[{self.get_name()}] [WARN] Page navigation detected, waiting for page to stabilize...")
                        await asyncio.sleep(3)
                        # Reset stability counters
                        stable_count = 0
                        last_length = 0
                        continue
                    else:
                        # Other errors, just log and continue
                        print(f"[{self.get_name()}] Query error (continuing): {error_str}")

                await asyncio.sleep(1)
                waited += 1

                if waited % 15 == 0:
                    print(f"[{self.get_name()}] Still waiting... ({waited}s)")

            # Extract the response text - Updated selectors for 2025 Claude.ai
            messages = None
            message_selectors = [
                # 2025년 최신 Claude 셀렉터
                'div.font-claude-message',
                'div[data-is-streaming]',
                '[data-test-render-count]',
                'div.font-user-message ~ div',  # 사용자 메시지 다음 div
                'div[class*="font-claude"]',
                'div[class*="prose"]',
                'div[class*="markdown"]',
                'main div[class*="whitespace"]',
                # 가장 넓은 범위
                'main > div > div > div > div',
            ]

            for msg_selector in message_selectors:
                try:
                    messages = await self.page.query_selector_all(msg_selector)
                    if messages and len(messages) > 0:
                        # 마지막 메시지의 텍스트 길이 확인
                        last_text = await messages[-1].inner_text()
                        if len(last_text.strip()) > 10:  # 최소 10자 이상
                            print(f"[{self.get_name()}] [OK] Found messages with: {msg_selector} ({len(messages)} messages)")
                            break
                except Exception as e:
                    error_str = str(e)
                    # Handle browser/page closed errors - stop immediately
                    if "has been closed" in error_str or "closed" in error_str.lower():
                        print(f"[{self.get_name()}] [ERROR] Browser closed during extraction. Stopping...")
                        self.response = "Browser closed by user"
                        return self.response
                    elif "Execution context was destroyed" in error_str or "navigation" in error_str.lower():
                        print(f"[{self.get_name()}] [WARN] Navigation during extraction, retrying after stabilization...")
                        await asyncio.sleep(2)
                        # Try this selector one more time
                        try:
                            messages = await self.page.query_selector_all(msg_selector)
                            if messages and len(messages) > 0:
                                last_text = await messages[-1].inner_text()
                                if len(last_text.strip()) > 10:
                                    print(f"[{self.get_name()}] [OK] Found messages after retry: {msg_selector}")
                                    break
                        except:
                            pass
                    else:
                        print(f"[{self.get_name()}] Selector {msg_selector} failed: {e}")
                    continue
                messages = None

            if messages and len(messages) > 0:
                last_message = messages[-1]
                response_text = await last_message.inner_text()

                # Remove UI button texts that appear at the end of responses
                ui_elements_to_remove = [
                    '\n재시도',
                    '\n복사',
                    '\n좋아요',
                    '\n싫어요',
                    '\nRetry',
                    '\nCopy',
                    '\nLike',
                    '\nDislike',
                    '재시도',  # At the very end
                    'Retry',
                ]

                cleaned_text = response_text
                for ui_element in ui_elements_to_remove:
                    if cleaned_text.endswith(ui_element):
                        cleaned_text = cleaned_text[:-len(ui_element)]
                    cleaned_text = cleaned_text.replace(ui_element, '')

                # Remove "json" at the beginning if present (code block indicator)
                if cleaned_text.strip().startswith('json\n'):
                    cleaned_text = cleaned_text.strip()[5:]  # Remove "json\n"
                elif cleaned_text.strip().startswith('json'):
                    cleaned_text = cleaned_text.strip()[4:]  # Remove "json"

                # 로그인 페이지 텍스트가 응답에 포함되어 있는지 확인
                login_indicators = [
                    'Continue with Google',
                    'Continue with email',
                    'Continue with SSO',
                    'Impossible? Possible',
                    'The AI for problem solvers'
                ]

                if any(indicator in cleaned_text for indicator in login_indicators):
                    print(f"[{self.get_name()}] [ERROR] Login page detected in response!")
                    raise Exception("Claude.ai login session expired. Response contains login page content. Please run setup_login.py to refresh your session.")

                self.response = cleaned_text.strip()
                print(f"[{self.get_name()}] [OK] Response received ({len(cleaned_text)} chars)")
                print(f"[{self.get_name()}] Preview: {cleaned_text[:100]}...")
                return cleaned_text
            else:
                # Fallback 1: main 안의 모든 텍스트
                print(f"[{self.get_name()}] Trying fallback: main element")
                try:
                    chat_area = await self.page.query_selector('main')
                    if chat_area:
                        response_text = await chat_area.inner_text()
                        # 사용자 입력 제외하고 응답만 추출 시도
                        lines = response_text.split('\n')
                        if len(lines) > 5:
                            # 마지막 부분이 응답일 가능성이 높음
                            response_text = '\n'.join(lines[-20:])

                        # Remove UI button texts
                        ui_elements_to_remove = [
                            '\n재시도', '\n복사', '\n좋아요', '\n싫어요',
                            '\nRetry', '\nCopy', '\nLike', '\nDislike',
                            '재시도', 'Retry',
                        ]
                        for ui_element in ui_elements_to_remove:
                            if response_text.endswith(ui_element):
                                response_text = response_text[:-len(ui_element)]
                            response_text = response_text.replace(ui_element, '')

                        # Remove "json" at the beginning if present
                        if response_text.strip().startswith('json\n'):
                            response_text = response_text.strip()[5:]
                        elif response_text.strip().startswith('json'):
                            response_text = response_text.strip()[4:]

                        self.response = response_text.strip()
                        print(f"[{self.get_name()}] Fallback response ({len(self.response)} chars)")
                        print(f"[{self.get_name()}] Preview: {self.response[:100]}...")
                        return self.response
                except Exception as e:
                    print(f"[{self.get_name()}] Fallback extraction failed: {str(e)}")

                # Fallback 2: 스크린샷 찍어서 확인 가능하도록
                print(f"[{self.get_name()}] [ERROR] No response found - taking screenshot for debugging")
                try:
                    await self.page.screenshot(path='claude_no_response_debug.png')
                except:
                    print(f"[{self.get_name()}] Could not take screenshot")
                self.response = "No response found"
                return self.response

        except Exception as e:
            error_msg = f"Error waiting for response: {str(e)}"
            print(f"[{self.get_name()}] {error_msg}")
            self.response = error_msg
            return error_msg

    async def send_question(self, question: str) -> str:
        """Send question to Claude and get response (complete flow)"""
        await self._send_question_only(question)
        return await self.wait_for_complete_response()
