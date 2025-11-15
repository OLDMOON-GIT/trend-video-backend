from .base_agent import BaseAgent
import asyncio


class GeminiAgent(BaseAgent):
    """Gemini automation agent"""

    def get_name(self) -> str:
        return "Gemini"

    def get_url(self) -> str:
        return "https://gemini.google.com/"

    async def login(self):
        """Gemini login handling"""
        if self.skip_login_check:
            print(f"[{self.get_name()}] Skipping login check (assuming already logged in)")
            return

        print(f"[{self.get_name()}] Waiting for page to load...")
        await asyncio.sleep(1.5)

        try:
            # Try multiple selectors for the input field
            selectors = [
                'rich-textarea',
                'textarea',
                'div[contenteditable="true"]',
                '[role="textbox"]',
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
            # Try multiple input selectors
            input_field = None
            selectors = [
                'rich-textarea',
                'textarea',
                'div[contenteditable="true"]',
                '[role="textbox"]',
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
                raise Exception("Could not find Gemini input field")

            # Click and type using clipboard paste (faster and more reliable)
            print(f"[{self.get_name()}] Copying question to clipboard and pasting...")
            await input_field.click()
            await asyncio.sleep(0.3)

            # Try clipboard paste first
            try:
                # Set clipboard content
                await self.page.evaluate("""
                    (text) => {
                        navigator.clipboard.writeText(text);
                    }
                """, question)
                await asyncio.sleep(0.2)

                # Try to find inner textarea for paste
                textarea = await input_field.query_selector('textarea')
                if textarea:
                    await textarea.focus()
                    await asyncio.sleep(0.1)
                    await self.page.keyboard.press('Control+KeyV')
                else:
                    await self.page.keyboard.press('Control+KeyV')

                await asyncio.sleep(0.3)
                print(f"[{self.get_name()}] Text pasted successfully")
            except Exception as e:
                # Fallback to typing if clipboard doesn't work
                print(f"[{self.get_name()}] Clipboard paste failed, falling back to typing: {e}")
                textarea = await input_field.query_selector('textarea')
                if textarea:
                    await textarea.fill(question)
                else:
                    await self.page.keyboard.type(question)
                await asyncio.sleep(0.2)

            # Look for send button
            send_button = None
            button_selectors = [
                'button[aria-label*="Send"]',
                'button[mattooltip*="Send"]',
                'button[aria-label*="send"]',
                'button[class*="send"]',
                'button svg',
            ]

            for btn_selector in button_selectors:
                try:
                    send_button = await self.page.query_selector(btn_selector)
                    if send_button:
                        print(f"[{self.get_name()}] Found send button: {btn_selector}")
                        await send_button.click()
                        await asyncio.sleep(0.5)
                        print(f"[{self.get_name()}] Send button clicked!")
                        break
                except:
                    continue

            if not send_button:
                print(f"[{self.get_name()}] No send button found, trying Enter key...")
                await self.page.keyboard.press('Enter')
                await asyncio.sleep(0.5)

            print(f"[{self.get_name()}] Question sent!")

        except Exception as e:
            error_msg = f"Error sending question: {str(e)}"
            print(f"[{self.get_name()}] {error_msg}")
            raise

    async def wait_for_complete_response(self) -> str:
        """Wait for Gemini to complete its response"""
        try:
            # Wait for response to start
            print(f"[{self.get_name()}] Waiting for response to start...")
            await asyncio.sleep(2)

            # Wait for response to complete by monitoring for changes
            print(f"[{self.get_name()}] Waiting for Gemini to finish typing...")
            max_wait = 600  # Maximum 10 minutes (no timeout essentially)
            waited = 0
            last_length = 0
            stable_count = 0

            while waited < max_wait:
                # Check if text is stable
                try:
                    messages = await self.page.query_selector_all('.model-response-text')
                    if not messages:
                        messages = await self.page.query_selector_all('[class*="message"]')

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
                except Exception as e:
                    error_str = str(e)
                    # Handle browser/page closed errors - stop immediately
                    if "has been closed" in error_str or "closed" in error_str.lower():
                        print(f"[{self.get_name()}] [ERROR] Browser or page has been closed. Stopping...")
                        self.response = "Browser closed by user"
                        return self.response
                    else:
                        # Other errors, just continue
                        pass

                await asyncio.sleep(1)
                waited += 1

                if waited % 15 == 0:
                    print(f"[{self.get_name()}] Still waiting... ({waited}s)")

            # Extract the response text
            messages = None
            message_selectors = [
                '.model-response-text',
                'message-content',
                '.response-container',
                '[data-test-id*="conversation"]',
                'div[class*="model-response"]',
            ]

            for msg_selector in message_selectors:
                messages = await self.page.query_selector_all(msg_selector)
                if messages and len(messages) > 0:
                    print(f"[{self.get_name()}] Found messages with: {msg_selector}")
                    break

            if messages and len(messages) > 0:
                last_message = messages[-1]
                response_text = await last_message.inner_text()
                self.response = response_text
                print(f"[{self.get_name()}] Response received ({len(response_text)} chars)")
                return response_text
            else:
                # Fallback: get last visible text
                chat_messages = await self.page.query_selector_all('[class*="message"]')
                if chat_messages and len(chat_messages) > 0:
                    last_msg = chat_messages[-1]
                    response_text = await last_msg.inner_text()
                    self.response = response_text
                    return response_text

                self.response = "No response found"
                return self.response

        except Exception as e:
            error_msg = f"Error waiting for response: {str(e)}"
            print(f"[{self.get_name()}] {error_msg}")
            self.response = error_msg
            return error_msg

    async def send_question(self, question: str) -> str:
        """Send question to Gemini and get response (complete flow)"""
        await self._send_question_only(question)
        return await self.wait_for_complete_response()
