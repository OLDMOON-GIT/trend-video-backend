from .base_agent import BaseAgent
import asyncio


class ChatGPTAgent(BaseAgent):
    """ChatGPT automation agent"""

    def get_name(self) -> str:
        return "ChatGPT"

    def get_url(self) -> str:
        return "https://chatgpt.com/"

    async def login(self):
        """ChatGPT login handling"""
        if self.skip_login_check:
            print(f"[{self.get_name()}] Skipping login check (assuming already logged in)")
            return

        # Wait for potential login screen or main chat interface
        print(f"[{self.get_name()}] Waiting for page to load...")
        await asyncio.sleep(0.5)

        try:
            # Try multiple selectors for the input field
            selectors = [
                'textarea[id="prompt-textarea"]',
                'textarea[data-id="root"]',
                'textarea[placeholder*="Message"]',
                '#prompt-textarea',
                'textarea',
            ]

            found = False
            for selector in selectors:
                try:
                    await self.page.wait_for_selector(selector, timeout=1500)
                    print(f"[{self.get_name()}] Already logged in (found: {selector})")
                    found = True
                    break
                except:
                    continue

            if not found:
                print(f"[{self.get_name()}] Login required - Please log in manually in the browser window")
                print(f"[{self.get_name()}] Waiting 40 seconds for manual login...")
                await asyncio.sleep(40)
                # Extra wait to ensure cookies are saved
                print(f"[{self.get_name()}] Ensuring session is saved...")
                await asyncio.sleep(3)
        except Exception as e:
            print(f"[{self.get_name()}] Login check error: {str(e)}")

    async def _send_question_only(self, question: str):
        """Just send the question without waiting for response"""
        try:
            # Try multiple selectors for the textarea
            textarea = None
            selectors = [
                'textarea[id="prompt-textarea"]',
                '#prompt-textarea',
                'textarea[data-id="root"]',
                'textarea[placeholder*="Message"]',
            ]

            for selector in selectors:
                try:
                    textarea = await self.page.wait_for_selector(selector, timeout=1500)
                    if textarea:
                        print(f"[{self.get_name()}] Found input field: {selector}")
                        break
                except:
                    continue

            if not textarea:
                raise Exception("Could not find ChatGPT input field")

            # Click and use clipboard paste (faster and more reliable for long prompts)
            print(f"[{self.get_name()}] Copying question to clipboard and pasting...")
            await textarea.click()
            await asyncio.sleep(0.1)

            # Try clipboard paste first (much faster for long prompts)
            try:
                # Set clipboard content
                await self.page.evaluate("""
                    (text) => {
                        navigator.clipboard.writeText(text);
                    }
                """, question)
                await asyncio.sleep(0.1)

                # Paste using Ctrl+V
                await self.page.keyboard.press('Control+KeyV')
                await asyncio.sleep(0.2)
                print(f"[{self.get_name()}] Text pasted successfully")
            except Exception as e:
                # Fallback to fill if clipboard doesn't work
                print(f"[{self.get_name()}] Clipboard paste failed, falling back to fill: {e}")
                await textarea.fill(question)
                await asyncio.sleep(0.1)

            # Press Enter to send
            await textarea.press('Enter')
            print(f"[{self.get_name()}] Question sent!")

        except Exception as e:
            error_msg = f"Error sending question: {str(e)}"
            print(f"[{self.get_name()}] {error_msg}")
            raise

    async def wait_for_complete_response(self) -> str:
        """Wait for ChatGPT to complete its response"""
        try:
            # Wait for response to start - give it more time
            print(f"[{self.get_name()}] Waiting for response to start...")
            await asyncio.sleep(3)

            # First, wait for the stop button to appear (means ChatGPT is typing)
            print(f"[{self.get_name()}] Waiting for ChatGPT to start typing...")
            response_started = False
            for i in range(30):  # Wait up to 30 seconds for response to start
                stop_button = await self.page.query_selector('button[aria-label*="Stop"]')
                if stop_button:
                    print(f"[{self.get_name()}] Response started! ChatGPT is now typing...")
                    response_started = True
                    break

                # Also check if there's already content (response might be very fast)
                try:
                    messages = await self.page.query_selector_all('article[data-testid^="conversation-turn-"]')
                    if not messages:
                        messages = await self.page.query_selector_all('[data-message-author-role="assistant"]')

                    if messages and len(messages) > 0:
                        text = await messages[-1].inner_text()
                        if len(text) > 50:  # If there's substantial content
                            print(f"[{self.get_name()}] Response found (fast response)")
                            response_started = True
                            break
                except:
                    pass

                await asyncio.sleep(1)

            if not response_started:
                print(f"[{self.get_name()}] Warning: Response didn't start in 30s, continuing anyway...")

            # Wait for response to complete by monitoring for changes
            print(f"[{self.get_name()}] Waiting for ChatGPT to finish typing...")
            max_wait = 600  # Maximum 10 minutes
            waited = 0
            last_length = 0
            stable_count = 0

            while waited < max_wait:
                try:
                    # Check if stop button exists (ChatGPT is still typing)
                    stop_button = await self.page.query_selector('button[aria-label*="Stop"]')

                    if not stop_button:
                        # No stop button, might be done - check if text is stable
                        try:
                            messages = await self.page.query_selector_all('article[data-testid^="conversation-turn-"]')
                            if not messages:
                                messages = await self.page.query_selector_all('[data-message-author-role="assistant"]')

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
                    else:
                        # Still typing, reset stability counter
                        stable_count = 0

                except Exception as e:
                    error_str = str(e)
                    # Handle browser/page closed errors - stop immediately
                    if "has been closed" in error_str or "closed" in error_str.lower():
                        print(f"[{self.get_name()}] [ERROR] Browser or page has been closed. Stopping...")
                        self.response = "Browser closed by user"
                        return self.response
                    else:
                        print(f"[{self.get_name()}] Query error (continuing): {error_str}")

                await asyncio.sleep(1)
                waited += 1

                if waited % 15 == 0:
                    print(f"[{self.get_name()}] Still waiting... ({waited}s)")

            # Extract the response text from the last message
            # Try multiple selectors for messages
            messages = None
            message_selectors = [
                'article[data-testid^="conversation-turn-"]',
                '[data-message-author-role="assistant"]',
                '.group.w-full',
                'div[class*="markdown"]',
            ]

            for msg_selector in message_selectors:
                messages = await self.page.query_selector_all(msg_selector)
                if messages and len(messages) > 0:
                    print(f"[{self.get_name()}] Found messages with: {msg_selector}")
                    break

            if messages and len(messages) > 0:
                last_message = messages[-1]

                # Try to find the actual content within the message
                # ChatGPT often wraps the content in specific elements
                content_selectors = [
                    'div[class*="markdown"]',
                    'div[class*="prose"]',
                    'div[class*="text-base"]',
                    'div[data-message-author-role="assistant"]',
                    '.whitespace-pre-wrap',
                    'div.flex.flex-grow',
                ]

                response_text = None
                for content_selector in content_selectors:
                    try:
                        content_elem = await last_message.query_selector(content_selector)
                        if content_elem:
                            text = await content_elem.inner_text()
                            if len(text) > 20:  # Make sure we got actual content
                                response_text = text
                                print(f"[{self.get_name()}] Found content using: {content_selector}")
                                break
                    except:
                        continue

                # If no content found with specific selectors, use the whole message
                if not response_text:
                    response_text = await last_message.inner_text()

                # Remove the "ChatGPT의 말:" header if present
                if response_text.startswith("ChatGPT의 말:"):
                    response_text = response_text.replace("ChatGPT의 말:", "", 1).strip()
                elif response_text.startswith("ChatGPT said:"):
                    response_text = response_text.replace("ChatGPT said:", "", 1).strip()

                self.response = response_text
                print(f"[{self.get_name()}] Response received ({len(response_text)} chars)")
                return response_text
            else:
                # Fallback: get all visible text
                body_text = await self.page.inner_text('body')
                self.response = body_text[-1000:] if len(body_text) > 1000 else body_text
                return self.response

        except Exception as e:
            error_msg = f"Error waiting for response: {str(e)}"
            print(f"[{self.get_name()}] {error_msg}")
            self.response = error_msg
            return error_msg

    async def send_question(self, question: str) -> str:
        """Send question to ChatGPT and get response (complete flow)"""
        await self._send_question_only(question)
        return await self.wait_for_complete_response()
