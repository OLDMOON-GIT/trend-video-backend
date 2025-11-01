from .base_agent import BaseAgent
import asyncio


class ChatGPTAgent(BaseAgent):
    """ChatGPT automation agent"""

    def get_name(self) -> str:
        return "ChatGPT"

    def get_url(self) -> str:
        return "https://chat.openai.com/"

    async def login(self):
        """ChatGPT login handling"""
        if self.skip_login_check:
            print(f"[{self.get_name()}] Skipping login check (assuming already logged in)")
            return

        # Wait for potential login screen or main chat interface
        print(f"[{self.get_name()}] Waiting for page to load...")
        await asyncio.sleep(1.5)

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
            # Try multiple selectors for the textarea
            textarea = None
            selectors = [
                'textarea[id="prompt-textarea"]',
                'textarea[data-id="root"]',
                'textarea[placeholder*="Message"]',
                '#prompt-textarea',
            ]

            for selector in selectors:
                try:
                    textarea = await self.page.wait_for_selector(selector, timeout=5000)
                    if textarea:
                        print(f"[{self.get_name()}] Found input field: {selector}")
                        break
                except:
                    continue

            if not textarea:
                raise Exception("Could not find ChatGPT input field")

            # Type the question immediately
            await textarea.click()
            await asyncio.sleep(0.1)
            await textarea.fill(question)
            await asyncio.sleep(0.2)

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
            # Wait for response to start
            print(f"[{self.get_name()}] Waiting for response to start...")
            await asyncio.sleep(2)

            # Wait for response to complete by monitoring for changes
            print(f"[{self.get_name()}] Waiting for ChatGPT to finish typing...")
            max_wait = 600  # Maximum 10 minutes (no timeout essentially)
            waited = 0
            last_length = 0
            stable_count = 0

            while waited < max_wait:
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
                response_text = await last_message.inner_text()
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
