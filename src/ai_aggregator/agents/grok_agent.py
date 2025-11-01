from .base_agent import BaseAgent
import asyncio


class GrokAgent(BaseAgent):
    """Grok (X.AI) automation agent"""

    def get_name(self) -> str:
        return "Grok"

    def get_url(self) -> str:
        return "https://x.com/i/grok"

    async def login(self):
        """Grok login handling"""
        try:
            # Check if we're already logged in
            # Grok is part of X (Twitter), so login state is shared
            await self.page.wait_for_selector('[data-testid="tweetTextarea_0"], textarea, div[contenteditable="true"]', timeout=5000)
            print(f"[{self.get_name()}] Already logged in or no login required")
        except:
            print(f"[{self.get_name()}] Login may be required - please log in manually")
            # Wait for user to log in manually
            await asyncio.sleep(10)

    async def _send_question_only(self, question: str):
        """Just send the question without waiting for response"""
        try:
            # Find the input field
            input_field = await self.page.wait_for_selector(
                '[data-testid="tweetTextarea_0"], textarea, div[contenteditable="true"], [role="textbox"]',
                timeout=10000
            )

            await input_field.click()
            await asyncio.sleep(0.1)
            await input_field.fill(question)
            await asyncio.sleep(0.2)

            # Look for send button
            send_button = await self.page.query_selector('button[data-testid*="send"], button[aria-label*="Send"]')
            if send_button:
                await send_button.click()
            else:
                # Try alternative selectors
                send_buttons = await self.page.query_selector_all('button')
                for btn in send_buttons:
                    text = await btn.inner_text()
                    if 'send' in text.lower() or 'submit' in text.lower():
                        await btn.click()
                        break
                else:
                    # Fallback: press Enter
                    await input_field.press('Enter')

            print(f"[{self.get_name()}] Question sent!")

        except Exception as e:
            error_msg = f"Error sending question: {str(e)}"
            print(f"[{self.get_name()}] {error_msg}")
            raise

    async def wait_for_complete_response(self) -> str:
        """Wait for Grok to complete its response"""
        try:
            # Wait for response to start
            print(f"[{self.get_name()}] Waiting for response to start...")
            await asyncio.sleep(2)

            # Wait for response to complete by monitoring for changes
            print(f"[{self.get_name()}] Waiting for Grok to finish typing...")
            max_wait = 600  # Maximum 10 minutes (no timeout essentially)
            waited = 0
            last_length = 0
            stable_count = 0

            while waited < max_wait:
                # Check if text is stable
                try:
                    messages = await self.page.query_selector_all('[data-testid*="messageContent"], [class*="message"], article')
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

            # Extract the response text
            # Grok uses X's message structure
            messages = await self.page.query_selector_all('[data-testid*="messageContent"], [class*="message"], article')
            if messages:
                # Get the last message (should be Grok's response)
                last_message = messages[-1]
                response_text = await last_message.inner_text()
                self.response = response_text
                print(f"[{self.get_name()}] Response received")
                return response_text
            else:
                # Fallback: try to get any chat content
                chat_area = await self.page.query_selector('main, [role="main"]')
                if chat_area:
                    response_text = await chat_area.inner_text()
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
        """Send question to Grok and get response (complete flow)"""
        await self._send_question_only(question)
        return await self.wait_for_complete_response()
