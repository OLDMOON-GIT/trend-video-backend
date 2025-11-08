"""
Setup script to login to all AI services once.
Run this first before using the main program.
"""

import asyncio
from playwright.async_api import async_playwright
from colorama import Fore, Style, init
import os
import pathlib

init(autoreset=True)


async def setup_login(agents_list: list = None):
    """Setup login for all AI services"""

    if agents_list is None:
        agents_list = ['chatgpt', 'claude', 'gemini', 'grok']

    print(f"\n{Fore.YELLOW}{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}{Style.BRIGHT}AI Login Setup{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}{Style.BRIGHT}{'='*80}{Style.RESET_ALL}\n")

    print(f"{Fore.CYAN}This will open browser tabs for you to login to each AI service.{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Your login will be saved for future use.{Style.RESET_ALL}\n")

    # AI service URLs
    ai_urls = {
        'chatgpt': 'https://chat.openai.com/',
        'claude': 'https://claude.ai/',
        'gemini': 'https://gemini.google.com/',
        'grok': 'https://x.com/i/grok',
    }

    async with async_playwright() as p:
        # Use a dedicated profile for automation
        # 스크립트 위치 기준으로 프로젝트 루트 찾기 (trend-video-backend)
        script_dir = os.path.dirname(os.path.abspath(__file__))  # src/ai_aggregator
        project_root = os.path.dirname(os.path.dirname(script_dir))  # trend-video-backend
        automation_profile = os.path.join(project_root, '.chrome-automation-profile')
        pathlib.Path(automation_profile).mkdir(exist_ok=True)

        print(f"{Fore.YELLOW}[INFO] 프로젝트 루트: {project_root}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[INFO] Chrome 프로필 경로: {automation_profile}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[INFO] This profile will save your login sessions{Style.RESET_ALL}\n")

        print(f"{Fore.YELLOW}[INFO] Launching Chrome...{Style.RESET_ALL}")

        try:
            context = await p.chromium.launch_persistent_context(
                automation_profile,
                headless=False,
                channel='chrome',
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                ],
                accept_downloads=True,
                timeout=60000,  # 60 second timeout
            )

            # Remove navigator.webdriver flag
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
        except Exception as e:
            print(f"{Fore.RED}[ERROR] Could not launch Chrome: {e}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}[INFO] Trying with Chromium instead...{Style.RESET_ALL}")
            context = await p.chromium.launch_persistent_context(
                automation_profile,
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                ],
                accept_downloads=True,
                timeout=60000,
            )

            # Remove navigator.webdriver flag
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

        # Open all AI services in tabs
        pages = []
        for agent_name in agents_list:
            if agent_name.lower() in ai_urls:
                url = ai_urls[agent_name.lower()]
                print(f"\n{Fore.CYAN}Opening {agent_name.upper()}...{Style.RESET_ALL}")
                page = await context.new_page()
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                pages.append((agent_name, page))
                await asyncio.sleep(2)

        print(f"\n{Fore.GREEN}{'='*80}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}All AI services opened!{Style.RESET_ALL}")
        print(f"{Fore.GREEN}{'='*80}{Style.RESET_ALL}\n")

        print(f"{Fore.YELLOW}Please login to each AI service in the browser tabs.{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Take your time - there's no rush.{Style.RESET_ALL}\n")

        for agent_name, _ in pages:
            print(f"  - {agent_name.upper()}")

        print(f"\n{Fore.CYAN}When you're done logging in to all services:{Style.RESET_ALL}")
        input(f"{Fore.CYAN}Press ENTER to save and close...{Style.RESET_ALL}")

        print(f"\n{Fore.YELLOW}[INFO] Saving session data...{Style.RESET_ALL}")

        # Close all pages
        for _, page in pages:
            await page.close()

        # Close context to save cookies
        await context.close()
        await asyncio.sleep(1)

        print(f"\n{Fore.GREEN}{'='*80}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}Setup Complete!{Style.RESET_ALL}")
        print(f"{Fore.GREEN}{'='*80}{Style.RESET_ALL}\n")

        print(f"{Fore.CYAN}You can now use the main program:{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}  python main.py -q \"your question\" -a chatgpt,claude{Style.RESET_ALL}\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Setup login for AI services')
    parser.add_argument('-a', '--agents', type=str,
                        help='Comma-separated list of agents (chatgpt,claude,gemini,grok)',
                        default='chatgpt,claude,gemini,grok')

    args = parser.parse_args()
    agents = [a.strip().lower() for a in args.agents.split(',')]

    asyncio.run(setup_login(agents))
