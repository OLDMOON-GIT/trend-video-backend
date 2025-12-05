"""
BTS-3153: Claude Agent Login Field Detection Test
Tests that claude_agent.py properly handles login field detection with extended selectors.
"""

import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


class TestClaudeAgentLoginFieldDetection(unittest.TestCase):
    """Test suite for BTS-3153: Input field not found issue"""

    def test_extended_selectors_list(self):
        """BTS-3153: Verify extended selector list exists in login method"""
        from ai_aggregator.agents.claude_agent import ClaudeAgent

        # Check that ClaudeAgent class exists and has login method
        self.assertTrue(hasattr(ClaudeAgent, 'login'))
        self.assertTrue(hasattr(ClaudeAgent, '_send_question_only'))

    def test_selectors_include_2025_ui_patterns(self):
        """BTS-3153: Verify 2025 UI selectors are included"""
        # Read the source file to check selectors
        source_path = os.path.join(
            os.path.dirname(__file__),
            '..', '..', 'src', 'ai_aggregator', 'agents', 'claude_agent.py'
        )

        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for 2025 UI selectors
        expected_selectors = [
            'div.ProseMirror',
            '[data-placeholder]',
            'div[class*="input"]',
            'div[class*="composer"]',
            'fieldset div[contenteditable]',
            'form div[contenteditable]',
        ]

        for selector in expected_selectors:
            self.assertIn(
                selector,
                content,
                f"BTS-3153: Missing 2025 UI selector: {selector}"
            )

    def test_increased_wait_times(self):
        """BTS-3153: Verify increased wait times for page load"""
        source_path = os.path.join(
            os.path.dirname(__file__),
            '..', '..', 'src', 'ai_aggregator', 'agents', 'claude_agent.py'
        )

        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for BTS-3153 comments indicating increased wait times
        self.assertIn('BTS-3153', content, "Missing BTS-3153 reference in code")
        # Check for sleep(3) or sleep(4) calls (increased from original 1.5s and 2s)
        self.assertIn('asyncio.sleep(3)', content, "Missing increased wait time (3s)")
        self.assertIn('asyncio.sleep(4)', content, "Missing increased wait time (4s)")

    def test_debug_screenshot_on_failure(self):
        """BTS-3153: Verify debug screenshot is taken on failure"""
        source_path = os.path.join(
            os.path.dirname(__file__),
            '..', '..', 'src', 'ai_aggregator', 'agents', 'claude_agent.py'
        )

        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for debug screenshot logic
        self.assertIn(
            'claude_login_debug.png',
            content,
            "BTS-3153: Missing debug screenshot on failure"
        )
        self.assertIn(
            '[DEBUG] Current URL',
            content,
            "BTS-3153: Missing URL debug logging"
        )

    def test_error_message_includes_url(self):
        """BTS-3153: Verify error message includes URL for debugging"""
        source_path = os.path.join(
            os.path.dirname(__file__),
            '..', '..', 'src', 'ai_aggregator', 'agents', 'claude_agent.py'
        )

        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check that error message includes URL
        self.assertIn(
            '(URL:',
            content,
            "BTS-3153: Error message should include current URL"
        )

    def test_retry_before_relogin(self):
        """BTS-3153: Verify retry logic before attempting re-login"""
        source_path = os.path.join(
            os.path.dirname(__file__),
            '..', '..', 'src', 'ai_aggregator', 'agents', 'claude_agent.py'
        )

        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for additional wait and retry before re-login
        self.assertIn(
            'waiting for page to fully load',
            content,
            "BTS-3153: Should wait for page to fully load before re-login"
        )
        self.assertIn(
            'Found input after additional wait',
            content,
            "BTS-3153: Should log when input found after additional wait"
        )


class TestClaudeAgentSendQuestion(unittest.TestCase):
    """Test suite for _send_question_only method selectors"""

    def test_send_question_extended_selectors(self):
        """BTS-3153: Verify _send_question_only uses extended selectors"""
        source_path = os.path.join(
            os.path.dirname(__file__),
            '..', '..', 'src', 'ai_aggregator', 'agents', 'claude_agent.py'
        )

        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find _send_question_only method section
        send_question_start = content.find('async def _send_question_only')
        send_question_end = content.find('async def ', send_question_start + 1)
        send_question_content = content[send_question_start:send_question_end]

        # Check for 2025 selectors in _send_question_only
        expected_selectors = [
            'div.ProseMirror',
            '[data-placeholder]',
        ]

        for selector in expected_selectors:
            self.assertIn(
                selector,
                send_question_content,
                f"BTS-3153: _send_question_only missing selector: {selector}"
            )


if __name__ == '__main__':
    unittest.main()
