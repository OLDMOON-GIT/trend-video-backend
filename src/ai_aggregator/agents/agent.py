from .base_agent import BaseAgent
import asyncio


class UnifiedAgent(BaseAgent):
    """Unified AI automation agent supporting Claude, ChatGPT, Gemini, and Grok"""

    def __init__(self, browser, headless: bool = False, skip_login_check: bool = False, ai_type: str = 'claude'):
        """
        Initialize unified agent

        Args:
            browser: Playwright browser or context object
            headless: Run in headless mode
            skip_login_check: Skip login verification
            ai_type: Type of AI ('claude', 'chatgpt', 'gemini', 'grok')
        """
        super().__init__(browser, headless, skip_login_check)
        self.ai_type = ai_type.lower()

        print(f"[UnifiedAgent] 🔧 Initializing agent for: {self.ai_type}")

        # AI별 설정
        self.configs = {
            'claude': {
                'name': 'Claude',
                'url': 'https://claude.ai/',
                'login_check_page_content': True,
                'login_indicators': [
                    'Continue with Google',
                    'Continue with email',
                    'Continue with SSO',
                    'Sign in',
                    'Log in',
                    'Login to Claude'
                ],
                'input_selectors': [
                    'div[contenteditable="true"]',
                    '[contenteditable="true"]',
                    'textarea',
                    'div[role="textbox"]',
                ],
                'use_clipboard': True,
                'send_method': 'enter',
                'send_button_selectors': [
                    'button[aria-label*="Send"]',
                    'button[aria-label*="전송"]',
                    'button:has-text("Send")',
                    'button:has-text("전송")',
                ],
                'stop_button_selector': 'button[aria-label*="Stop"]',
                'message_selectors': [
                    'div.font-claude-message',
                    'div[data-is-streaming]',
                    '[data-test-render-count]',
                    'div.font-user-message ~ div',
                    'div[class*="font-claude"]',
                    'div[class*="prose"]',
                    'div[class*="markdown"]',
                    'main div[class*="whitespace"]',
                    'main > div > div > div > div',
                ],
                'cleanup_ui_elements': True,
                'ui_elements_to_remove': [
                    '\n재시도', '\n복사', '\n좋아요', '\n싫어요',
                    '\nRetry', '\nCopy', '\nLike', '\nDislike',
                    '재시도', 'Retry',
                ],
                'cleanup_code_headers': True,
                'handle_navigation_errors': True,
                'fallback_main_selector': 'main',
                'take_screenshot_on_error': True,
            },
            'chatgpt': {
                'name': 'ChatGPT',
                'url': 'https://chat.openai.com/',
                'login_check_page_content': False,
                'input_selectors': [
                    '#prompt-textarea',
                    'textarea[id="prompt-textarea"]',
                    'textarea[placeholder*="Message"]',
                    'textarea[data-id="root"]',
                    'textarea',
                ],
                'use_clipboard': False,
                'send_method': 'enter',
                'stop_button_selector': 'button[aria-label*="Stop"]',
                'message_selectors': [
                    'article[data-testid^="conversation-turn-"]',
                    '[data-message-author-role="assistant"]',
                    '.group.w-full',
                    'div[class*="markdown"]',
                ],
                'cleanup_ui_elements': False,
                'cleanup_code_headers': False,
                'handle_navigation_errors': False,
                'fallback_main_selector': 'body',
            },
            'gemini': {
                'name': 'Gemini',
                'url': 'https://gemini.google.com/',
                'login_check_page_content': False,
                'input_selectors': [
                    'rich-textarea',
                    'textarea',
                    'div[contenteditable="true"]',
                    '[role="textbox"]',
                ],
                'use_clipboard': True,
                'clipboard_fallback': True,
                'send_method': 'button',
                'send_button_selectors': [
                    'button[aria-label*="Send"]',
                    'button[mattooltip*="Send"]',
                    'button[aria-label*="send"]',
                    'button[class*="send"]',
                    'button svg',
                ],
                'stop_button_selector': None,
                'message_selectors': [
                    '.model-response-text',
                    'message-content',
                    '.response-container',
                    '[data-test-id*="conversation"]',
                    'div[class*="model-response"]',
                ],
                'cleanup_ui_elements': False,
                'cleanup_code_headers': False,
                'handle_navigation_errors': False,
                'fallback_message_selector': '[class*="message"]',
            },
            'grok': {
                'name': 'Grok',
                'url': 'https://x.com/i/grok',
                'login_check_page_content': False,
                'input_selectors': [
                    '[data-testid="tweetTextarea_0"]',
                    'textarea',
                    'div[contenteditable="true"]',
                    '[role="textbox"]',
                ],
                'use_clipboard': False,
                'send_method': 'button',
                'send_button_selectors': [
                    'button[data-testid*="send"]',
                    'button[aria-label*="Send"]',
                ],
                'search_send_button_by_text': True,
                'stop_button_selector': None,
                'message_selectors': [
                    '[data-testid*="messageContent"]',
                    '[class*="message"]',
                    'article',
                ],
                'cleanup_ui_elements': False,
                'cleanup_code_headers': False,
                'handle_navigation_errors': False,
                'fallback_main_selector': 'main, [role="main"]',
            }
        }

        if self.ai_type not in self.configs:
            raise ValueError(f"Unsupported AI type: {ai_type}. Supported: {list(self.configs.keys())}")

        self.config = self.configs[self.ai_type]
        print(f"[UnifiedAgent] ✅ Configuration loaded for {self.get_name()}")

    def get_name(self) -> str:
        return self.config['name']

    def get_url(self) -> str:
        return self.config['url']

    async def login(self):
        """AI login handling"""
        if self.skip_login_check:
            print(f"[{self.get_name()}] Skipping login check (assuming already logged in)")
            return

        print(f"[{self.get_name()}] 🔍 Checking login status...")
        print(f"[{self.get_name()}] Current URL: {self.page.url}")
        await asyncio.sleep(1.5)

        try:
            # Claude만 페이지 전체 HTML 검사
            if self.config.get('login_check_page_content'):
                page_content = await self.page.content()
                login_indicators = self.config.get('login_indicators', [])

                is_login_page = any(indicator in page_content for indicator in login_indicators)

                if is_login_page:
                    print(f"[{self.get_name()}] [WARN] Login page detected!")
                    raise Exception(f"{self.get_name()} login required. Please run setup_login.py first to save your session.")

            # Input 필드 확인
            selectors = self.config['input_selectors']
            found = False
            print(f"[{self.get_name()}] 🔎 Searching for input field...")
            for i, selector in enumerate(selectors, 1):
                try:
                    print(f"[{self.get_name()}]   Trying selector {i}/{len(selectors)}: {selector}")
                    await self.page.wait_for_selector(selector, timeout=3000)
                    print(f"[{self.get_name()}] ✅ Already logged in (found: {selector})")
                    found = True
                    break
                except:
                    print(f"[{self.get_name()}]   ❌ Not found: {selector}")
                    continue

            if not found:
                print(f"[{self.get_name()}] [WARN] Login page detected!")
                raise Exception(f"{self.get_name()} login required. Please run setup_login.py first to save your session.")

        except Exception as e:
            print(f"[{self.get_name()}] Login check error: {str(e)}")
            if self.ai_type == 'claude':
                raise  # Claude는 로그인 실패 시 예외 전달
            # 다른 AI는 계속 진행

    async def _send_question_only(self, question: str):
        """Just send the question without waiting for response"""
        try:
            print(f"[{self.get_name()}] 📝 Preparing to send question...")
            print(f"[{self.get_name()}] Question length: {len(question)} chars")

            # Input 필드 찾기
            input_field = None
            selectors = self.config['input_selectors']

            print(f"[{self.get_name()}] 🔎 Looking for input field...")
            for i, selector in enumerate(selectors, 1):
                try:
                    print(f"[{self.get_name()}]   Trying {i}/{len(selectors)}: {selector}")
                    input_field = await self.page.wait_for_selector(selector, timeout=5000)
                    if input_field:
                        print(f"[{self.get_name()}] ✅ Found input field: {selector}")
                        break
                except:
                    print(f"[{self.get_name()}]   ❌ Not found: {selector}")
                    continue

            if not input_field:
                print(f"[{self.get_name()}] ❌ ERROR: Could not find {self.get_name()} input field!")
                raise Exception(f"Could not find {self.get_name()} input field")

            print(f"[{self.get_name()}] 📋 Clicking input field...")
            await input_field.click()
            await asyncio.sleep(0.3 if self.config.get('use_clipboard') else 0.1)

            # 입력 방식 분기
            if self.config.get('use_clipboard'):
                # 클립보드 사용 (Claude, Gemini)
                print(f"[{self.get_name()}] 📋 Copying question to clipboard and pasting...")
                try:
                    # 클립보드에 복사
                    await self.page.evaluate("""
                        (text) => {
                            navigator.clipboard.writeText(text);
                        }
                    """, question)
                    await asyncio.sleep(0.2)

                    # Gemini는 내부 textarea 확인
                    if self.ai_type == 'gemini':
                        textarea = await input_field.query_selector('textarea')
                        if textarea:
                            await textarea.focus()
                            await asyncio.sleep(0.1)

                    # Ctrl+V로 붙여넣기
                    print(f"[{self.get_name()}] ⌨️ Pressing Ctrl+V...")
                    await self.page.keyboard.press('Control+KeyV')
                    await asyncio.sleep(0.5 if self.ai_type == 'claude' else 0.3)
                    print(f"[{self.get_name()}] ✅ Text pasted successfully")
                except Exception as e:
                    # Fallback: 직접 입력
                    if self.config.get('clipboard_fallback'):
                        print(f"[{self.get_name()}] Clipboard paste failed, falling back to typing: {e}")
                        if self.ai_type == 'gemini':
                            textarea = await input_field.query_selector('textarea')
                            if textarea:
                                await textarea.fill(question)
                            else:
                                await self.page.keyboard.type(question)
                        else:
                            await self.page.keyboard.type(question, delay=10)
                        await asyncio.sleep(0.5)
                    else:
                        raise
            else:
                # 직접 입력 (ChatGPT, Grok)
                print(f"[{self.get_name()}] ⌨️ Typing question...")
                await input_field.fill(question)
                await asyncio.sleep(0.2)
                print(f"[{self.get_name()}] ✅ Question filled successfully")

            # 전송 방식 분기
            send_method = self.config.get('send_method', 'enter')
            sent = False

            if send_method in ['button', 'both']:
                # Send 버튼 찾기
                send_button_selectors = self.config.get('send_button_selectors', [])

                print(f"[{self.get_name()}] 🔘 Looking for send button...")
                for i, btn_selector in enumerate(send_button_selectors, 1):
                    try:
                        print(f"[{self.get_name()}]   Trying button {i}/{len(send_button_selectors)}: {btn_selector}")
                        send_button = await self.page.query_selector(btn_selector)
                        if send_button:
                            print(f"[{self.get_name()}] ✅ Found send button: {btn_selector}")
                            await send_button.click()
                            await asyncio.sleep(0.5)
                            print(f"[{self.get_name()}] 📤 Send button clicked!")
                            sent = True
                            break
                    except:
                        print(f"[{self.get_name()}]   ❌ Not found: {btn_selector}")
                        continue

                # Grok: 텍스트로 버튼 찾기
                if not sent and self.config.get('search_send_button_by_text'):
                    print(f"[{self.get_name()}] 🔎 Searching for send button by text...")
                    send_buttons = await self.page.query_selector_all('button')
                    for btn in send_buttons:
                        text = await btn.inner_text()
                        if 'send' in text.lower() or 'submit' in text.lower():
                            await btn.click()
                            sent = True
                            print(f"[{self.get_name()}] ✅ Send button found by text and clicked")
                            break

            if not sent and send_method in ['enter', 'both']:
                # Enter 키로 전송
                print(f"[{self.get_name()}] 📤 Sending with Enter key...")
                try:
                    await self.page.keyboard.press('Enter')
                    await asyncio.sleep(1)
                    print(f"[{self.get_name()}] ✅ Enter pressed")
                    sent = True
                except Exception as e:
                    print(f"[{self.get_name()}] Enter failed: {e}")

            if not sent:
                print(f"[{self.get_name()}] Warning: Could not confirm message send, but continuing...")

        except Exception as e:
            error_msg = f"Error sending question: {str(e)}"
            print(f"[{self.get_name()}] ❌ {error_msg}")
            raise

    async def wait_for_complete_response(self) -> str:
        """Wait for AI to complete its response"""
        try:
            # 응답 시작 대기
            print(f"[{self.get_name()}] ⏳ Waiting for response to start...")
            await asyncio.sleep(2)

            # 응답 완료 대기
            print(f"[{self.get_name()}] ⏳ Waiting for {self.get_name()} to finish typing...")
            max_wait = 3600 if self.ai_type == 'claude' else 600
            waited = 0
            last_length = 0
            stable_count = 0

            while waited < max_wait:
                try:
                    # Stop 버튼 확인 (있으면 아직 타이핑 중)
                    stop_button_selector = self.config.get('stop_button_selector')
                    if stop_button_selector:
                        stop_button = await self.page.query_selector(stop_button_selector)

                        if not stop_button:
                            # Stop 버튼 없음 - 텍스트 안정성 확인
                            try:
                                message_selectors = self.config['message_selectors']
                                messages = None

                                for msg_selector in message_selectors:
                                    messages = await self.page.query_selector_all(msg_selector)
                                    if messages and len(messages) > 0:
                                        break

                                if messages and len(messages) > 0:
                                    current_text = await messages[-1].inner_text()
                                    current_length = len(current_text)

                                    if current_length == last_length and current_length > 0:
                                        stable_count += 1
                                        if stable_count >= 5:  # 5초간 안정
                                            print(f"[{self.get_name()}] ✅ Response completed!")
                                            break
                                    else:
                                        stable_count = 0
                                        last_length = current_length
                            except:
                                pass
                    else:
                        # Stop 버튼 체크 안 함 - 텍스트 안정성만 확인 (Gemini, Grok)
                        try:
                            message_selectors = self.config['message_selectors']
                            messages = None

                            for msg_selector in message_selectors:
                                messages = await self.page.query_selector_all(msg_selector)
                                if messages and len(messages) > 0:
                                    break

                            if messages and len(messages) > 0:
                                current_text = await messages[-1].inner_text()
                                current_length = len(current_text)

                                if current_length == last_length and current_length > 0:
                                    stable_count += 1
                                    if stable_count >= 5:
                                        print(f"[{self.get_name()}] ✅ Response completed!")
                                        break
                                else:
                                    stable_count = 0
                                    last_length = current_length
                        except:
                            pass

                except Exception as e:
                    error_str = str(e)
                    # Claude의 네비게이션 오류 처리
                    if self.config.get('handle_navigation_errors'):
                        if "Execution context was destroyed" in error_str or "navigation" in error_str.lower():
                            print(f"[{self.get_name()}] ⚠️ Page navigation detected, waiting for page to stabilize...")
                            await asyncio.sleep(3)
                            stable_count = 0
                            last_length = 0
                            continue
                        else:
                            print(f"[{self.get_name()}] Query error (continuing): {error_str}")
                    # 다른 AI는 그냥 계속 진행

                await asyncio.sleep(1)
                waited += 1

                if waited % 15 == 0:
                    print(f"[{self.get_name()}] Still waiting... ({waited}s)")

            # 응답 추출
            messages = None
            message_selectors = self.config['message_selectors']

            print(f"[{self.get_name()}] 📥 Extracting response...")
            for i, msg_selector in enumerate(message_selectors, 1):
                try:
                    print(f"[{self.get_name()}]   Trying selector {i}/{len(message_selectors)}: {msg_selector}")
                    messages = await self.page.query_selector_all(msg_selector)
                    if messages and len(messages) > 0:
                        # 최소 길이 확인 (Claude만)
                        if self.ai_type == 'claude':
                            last_text = await messages[-1].inner_text()
                            if len(last_text.strip()) > 10:
                                print(f"[{self.get_name()}] [OK] Found messages with: {msg_selector} ({len(messages)} messages)")
                                break
                        else:
                            print(f"[{self.get_name()}] ✅ Found messages with: {msg_selector}")
                            break
                except Exception as e:
                    error_str = str(e)
                    if self.config.get('handle_navigation_errors'):
                        if "Execution context was destroyed" in error_str or "navigation" in error_str.lower():
                            print(f"[{self.get_name()}] ⚠️ Navigation during extraction, retrying after stabilization...")
                            await asyncio.sleep(2)
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

                # Claude의 UI 정리 작업
                if self.config.get('cleanup_ui_elements'):
                    cleaned_text = response_text
                    ui_elements = self.config.get('ui_elements_to_remove', [])

                    for ui_element in ui_elements:
                        if cleaned_text.endswith(ui_element):
                            cleaned_text = cleaned_text[:-len(ui_element)]
                        cleaned_text = cleaned_text.replace(ui_element, '')

                    response_text = cleaned_text

                # Claude의 코드 헤더 정리
                if self.config.get('cleanup_code_headers'):
                    if response_text.strip().startswith('json\n'):
                        response_text = response_text.strip()[5:]
                    elif response_text.strip().startswith('json'):
                        response_text = response_text.strip()[4:]

                # Claude: 로그인 페이지 텍스트 확인
                if self.ai_type == 'claude':
                    login_indicators = self.config.get('login_indicators', [])
                    if any(indicator in response_text for indicator in login_indicators):
                        print(f"[{self.get_name()}] [ERROR] Login page detected in response!")
                        raise Exception(f"{self.get_name()} login session expired. Response contains login page content. Please run setup_login.py to refresh your session.")

                self.response = response_text.strip()
                print(f"[{self.get_name()}] ✅ Response received ({len(response_text)} chars)")
                print(f"[{self.get_name()}] Preview: {response_text[:100]}...")
                return response_text
            else:
                # Fallback 처리
                fallback_selector = self.config.get('fallback_main_selector')
                if fallback_selector:
                    print(f"[{self.get_name()}] Trying fallback: {fallback_selector}")
                    try:
                        chat_area = await self.page.query_selector(fallback_selector)
                        if chat_area:
                            response_text = await chat_area.inner_text()

                            # Claude는 마지막 부분만 추출
                            if self.ai_type == 'claude':
                                lines = response_text.split('\n')
                                if len(lines) > 5:
                                    response_text = '\n'.join(lines[-20:])

                                # UI 정리
                                if self.config.get('cleanup_ui_elements'):
                                    ui_elements = self.config.get('ui_elements_to_remove', [])
                                    for ui_element in ui_elements:
                                        if response_text.endswith(ui_element):
                                            response_text = response_text[:-len(ui_element)]
                                        response_text = response_text.replace(ui_element, '')

                                if self.config.get('cleanup_code_headers'):
                                    if response_text.strip().startswith('json\n'):
                                        response_text = response_text.strip()[5:]
                                    elif response_text.strip().startswith('json'):
                                        response_text = response_text.strip()[4:]
                            elif self.ai_type == 'chatgpt':
                                # ChatGPT는 마지막 1000자
                                response_text = response_text[-1000:] if len(response_text) > 1000 else response_text

                            self.response = response_text.strip()
                            print(f"[{self.get_name()}] Fallback response ({len(self.response)} chars)")
                            print(f"[{self.get_name()}] Preview: {self.response[:100]}...")
                            return self.response
                    except Exception as e:
                        print(f"[{self.get_name()}] Fallback extraction failed: {str(e)}")

                # Gemini fallback
                if self.ai_type == 'gemini':
                    fallback_msg_selector = self.config.get('fallback_message_selector')
                    if fallback_msg_selector:
                        chat_messages = await self.page.query_selector_all(fallback_msg_selector)
                        if chat_messages and len(chat_messages) > 0:
                            last_msg = chat_messages[-1]
                            response_text = await last_msg.inner_text()
                            self.response = response_text
                            return response_text

                # Claude: 스크린샷 저장
                if self.config.get('take_screenshot_on_error'):
                    print(f"[{self.get_name()}] [ERROR] No response found - taking screenshot for debugging")
                    try:
                        await self.page.screenshot(path=f'{self.ai_type}_no_response_debug.png')
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
        """Send question to AI and get response (complete flow)"""
        await self._send_question_only(question)
        return await self.wait_for_complete_response()
