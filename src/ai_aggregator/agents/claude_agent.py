from .base_agent import BaseAgent
import asyncio


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
        await asyncio.sleep(1.5)

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
                raise Exception("Claude.ai login required. Please run setup_login.py first to save your session.")

            # Try multiple selectors for the input field
            selectors = [
                'div[contenteditable="true"]',
                '[contenteditable="true"]',
                'textarea',
                'div[role="textbox"]',
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
                print(f"[{self.get_name()}] [ERROR] Login required - Input field not found")
                raise Exception("Claude.ai login required. Please run setup_login.py first to save your session.")

        except Exception as e:
            print(f"[{self.get_name()}] Login check error: {str(e)}")
            raise  # 로그인 실패 시 예외를 상위로 전달

    async def _send_question_only(self, question: str):
        """Just send the question without waiting for response"""
        try:
            # Try multiple selectors for the input field
            input_field = None
            selectors = [
                'div[contenteditable="true"]',
                '[contenteditable="true"]',
                'div[role="textbox"]',
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
                raise Exception("Could not find Claude input field")

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

    async def wait_for_complete_response(self) -> str:
        """Wait for Claude to complete its response"""
        try:
            # Wait for response to start
            print(f"[{self.get_name()}] Waiting for response to start...")
            await asyncio.sleep(2)

            # Wait for response to complete by checking for stop button disappearing
            print(f"[{self.get_name()}] Waiting for Claude to finish typing...")
            max_wait = 600  # Maximum 10 minutes (no timeout essentially)
            waited = 0
            last_length = 0
            stable_count = 0

            while waited < max_wait:
                try:
                    # Check if stop button exists (Claude is still typing)
                    stop_button = await self.page.query_selector('button[aria-label*="Stop"]')

                    if not stop_button:
                        # No stop button, might be done - check if text is stable
                        try:
                            messages = await self.page.query_selector_all('[data-test-render-count]')
                            if messages and len(messages) > 0:
                                current_text = await messages[-1].inner_text()
                                current_length = len(current_text)

                                if current_length == last_length and current_length > 0:
                                    stable_count += 1
                                    if stable_count >= 5:  # Stable for 5 seconds to be sure
                                        print(f"[{self.get_name()}] Response completed!")
                                        break
                                else:
                                    stable_count = 0
                                    last_length = current_length
                        except:
                            pass
                except Exception as e:
                    error_str = str(e)
                    # Handle navigation/context destruction errors
                    if "Execution context was destroyed" in error_str or "navigation" in error_str.lower():
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
                    if "Execution context was destroyed" in error_str or "navigation" in error_str.lower():
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
