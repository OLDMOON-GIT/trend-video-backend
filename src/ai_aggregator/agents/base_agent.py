from abc import ABC, abstractmethod
from playwright.async_api import Page, Browser, BrowserContext
from typing import Union
import asyncio


class BaseAgent(ABC):
    """Base class for all AI agents"""

    def __init__(self, browser: Union[Browser, BrowserContext], headless: bool = False, skip_login_check: bool = False):
        self.browser = browser
        self.headless = headless
        self.skip_login_check = skip_login_check
        self.page: Page = None
        self.response = ""

    @abstractmethod
    async def login(self):
        """Login to the AI service if needed"""
        pass

    @abstractmethod
    async def send_question(self, question: str) -> str:
        """Send question and get response (complete flow)"""
        pass

    async def send_question_async(self, question: str):
        """Send question without waiting for response"""
        # Default implementation - subclasses can override
        await self._send_question_only(question)

    @abstractmethod
    async def _send_question_only(self, question: str):
        """Just send the question, don't wait for response"""
        pass

    @abstractmethod
    async def wait_for_complete_response(self) -> str:
        """Wait for and return the complete response"""
        pass

    @abstractmethod
    def get_url(self) -> str:
        """Get the URL of the AI service"""
        pass

    async def initialize(self):
        """Initialize browser page"""
        print(f"[{self.get_name()}] Creating new page...")
        self.page = await self.browser.new_page()
        url = self.get_url()
        print(f"[{self.get_name()}] Navigating to {url}...")
        await self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await self.wait_for_page_load()
        print(f"[{self.get_name()}] Page loaded successfully")

    async def wait_for_page_load(self):
        """Wait for page to fully load"""
        await asyncio.sleep(5)  # Wait longer for page elements to render

    async def close(self):
        """Close the page"""
        if self.page:
            await self.page.close()

    def get_response(self) -> str:
        """Get the last response"""
        return self.response

    @abstractmethod
    def get_name(self) -> str:
        """Get the name of the AI agent"""
        pass
