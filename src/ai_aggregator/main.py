import asyncio
import sys
import os
from playwright.async_api import async_playwright
from .agents import ChatGPTAgent, ClaudeAgent, GeminiAgent, GrokAgent
from .aggregator import ResponseAggregator
from colorama import Fore, Style, init
import argparse

# Fix Windows console encoding - use environment variables instead of wrapping streams
if sys.platform == 'win32':
    # Set UTF-8 encoding via environment variables (safer than wrapping streams)
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['PYTHONUTF8'] = '1'

    # Set console to UTF-8
    try:
        os.system('chcp 65001 > nul 2>&1')
    except:
        pass

# Initialize colorama
init(autoreset=True)


async def wait_for_response(agent, aggregator: ResponseAggregator):
    """Wait for agent's response and collect it"""
    try:
        print(f"{Fore.CYAN}[{agent.get_name()}] Waiting for complete response...{Style.RESET_ALL}")
        response = await agent.wait_for_complete_response()
        aggregator.add_response(agent.get_name(), response)
        print(f"{Fore.GREEN}[{agent.get_name()}] [OK] Response received!{Style.RESET_ALL}")
    except Exception as e:
        error_msg = f"Failed to get response: {str(e)}"
        print(f"{Fore.RED}[{agent.get_name()}] {error_msg}{Style.RESET_ALL}")
        aggregator.add_response(agent.get_name(), f"Error: {error_msg}")


async def main(question: str, headless: bool = False, agents_to_use: list = None, use_real_chrome: bool = True):
    """Main function to run all agents"""

    print(f"\n{Fore.YELLOW}{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}{Style.BRIGHT}Multi-AI Aggregator{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}{Style.BRIGHT}{'='*80}{Style.RESET_ALL}\n")

    print(f"{Fore.GREEN}Question:{Style.RESET_ALL} {question}\n")
    print(f"{Fore.CYAN}Mode:{Style.RESET_ALL} {'Headless' if headless else 'Headful (visible browser)'}\n")

    aggregator = ResponseAggregator()

    async with async_playwright() as p:
        import os
        import pathlib

        print(f"{Fore.GREEN}[INFO] Launching browser...{Style.RESET_ALL}\n")

        # Launch browser without persistent context to avoid profile lock issues
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-features=IsolateOrigins,site-per-process',
                '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            ],
            timeout=60000,
        )

        # Create a new context
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            ignore_https_errors=True,
        )

        # Remove navigator.webdriver flag
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        # Default to all agents if none specified
        if agents_to_use is None:
            agents_to_use = ['chatgpt', 'claude', 'gemini', 'grok']

        # Create agent instances based on selection
        agents = []
        agent_map = {
            'chatgpt': ChatGPTAgent,
            'claude': ClaudeAgent,
            'gemini': GeminiAgent,
            'grok': GrokAgent
        }

        # No skip login - always check login status
        skip_login = False

        for agent_name in agents_to_use:
            if agent_name.lower() in agent_map:
                agents.append(agent_map[agent_name.lower()](context, headless, skip_login))

        if not agents:
            print(f"{Fore.RED}No valid agents selected!{Style.RESET_ALL}")
            await context.close()
            await browser.close()
            return

        print(f"{Fore.YELLOW}Selected agents:{Style.RESET_ALL} {', '.join([a.get_name() for a in agents])}\n")

        # Phase 1: Open tabs sequentially and send questions
        print(f"{Fore.CYAN}[*] Opening tabs and sending questions sequentially...{Style.RESET_ALL}\n")
        for agent in agents:
            try:
                print(f"{Fore.CYAN}[{agent.get_name()}] Opening tab...{Style.RESET_ALL}")
                await agent.initialize()

                print(f"{Fore.CYAN}[{agent.get_name()}] Checking login...{Style.RESET_ALL}")
                await agent.login()

                print(f"{Fore.CYAN}[{agent.get_name()}] Sending question...{Style.RESET_ALL}")
                # Just send the question, don't wait for response yet
                await agent.send_question_async(question)

                print(f"{Fore.GREEN}[{agent.get_name()}] [OK] Question sent! Moving to next agent...{Style.RESET_ALL}\n")

            except Exception as e:
                error_msg = f"Failed to send question: {str(e)}"
                print(f"{Fore.RED}[{agent.get_name()}] {error_msg}{Style.RESET_ALL}\n")
                aggregator.add_response(agent.get_name(), f"Error: {error_msg}")

        # Phase 2: Now wait for all responses in parallel
        print(f"{Fore.CYAN}[*] All questions sent! Now waiting for all responses in parallel...{Style.RESET_ALL}\n")

        wait_tasks = []
        for agent in agents:
            if agent.page:  # Only if the agent was successfully initialized
                wait_tasks.append(wait_for_response(agent, aggregator))

        if wait_tasks:
            await asyncio.gather(*wait_tasks, return_exceptions=True)

        # Properly close the context to save cookies
        print(f"\n{Fore.YELLOW}[INFO] All agents completed! Saving session data...{Style.RESET_ALL}")

        # Give user a moment to see the results
        print(f"{Fore.CYAN}[TIP] Check the browser tabs to see all responses!{Style.RESET_ALL}")

        # Display results (inside async with block)
        aggregator.display_responses()
        aggregator.generate_summary()

        # Auto-save to file with timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ai_responses_{timestamp}.txt"
        aggregator.save_to_file(filename)

        print(f"\n{Fore.GREEN}{Style.BRIGHT}Done!{Style.RESET_ALL}")
        print(f"\n{Fore.YELLOW}Browser will remain open. Close manually or press Ctrl+C to exit.{Style.RESET_ALL}")

        # Keep the script running (browser stays open)
        # User can close browser manually or terminate script
        await asyncio.sleep(999999)  # Sleep indefinitely


def interactive_mode():
    """Interactive mode for continuous questions"""
    print(f"\n{Fore.YELLOW}{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}{Style.BRIGHT}Multi-AI Aggregator - Interactive Mode{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}{Style.BRIGHT}{'='*80}{Style.RESET_ALL}\n")

    print("Type your questions and get answers from multiple AI models.")
    print(f"{Fore.CYAN}Commands:{Style.RESET_ALL}")
    print("  - Type 'quit' or 'exit' to stop")
    print("  - Type 'agents' to select which AI agents to use")
    print("  - Type 'mode' to toggle headless/headful mode")
    print()

    headless = False
    agents_to_use = ['chatgpt', 'claude', 'gemini', 'grok']

    while True:
        question = input(f"{Fore.GREEN}Your question:{Style.RESET_ALL} ").strip()

        if question.lower() in ['quit', 'exit']:
            print(f"{Fore.YELLOW}Goodbye!{Style.RESET_ALL}")
            break

        if question.lower() == 'agents':
            print(f"\n{Fore.CYAN}Available agents:{Style.RESET_ALL} chatgpt, claude, gemini, grok")
            print(f"{Fore.CYAN}Current selection:{Style.RESET_ALL} {', '.join(agents_to_use)}")
            selection = input(f"{Fore.GREEN}Enter agents (comma-separated, or 'all'):{Style.RESET_ALL} ").strip()

            if selection.lower() == 'all':
                agents_to_use = ['chatgpt', 'claude', 'gemini', 'grok']
            else:
                agents_to_use = [a.strip().lower() for a in selection.split(',') if a.strip()]

            print(f"{Fore.GREEN}[OK] Agents updated:{Style.RESET_ALL} {', '.join(agents_to_use)}\n")
            continue

        if question.lower() == 'mode':
            headless = not headless
            mode = 'headless' if headless else 'headful'
            print(f"{Fore.GREEN}[OK] Mode switched to:{Style.RESET_ALL} {mode}\n")
            continue

        if not question:
            print(f"{Fore.RED}Please enter a question!{Style.RESET_ALL}\n")
            continue

        # Run the query
        asyncio.run(main(question, headless, agents_to_use))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Multi-AI Aggregator - Query multiple AI models at once')
    parser.add_argument('-q', '--question', type=str, help='Question to ask all AI models, or variable to substitute in template file (use with -f)')
    parser.add_argument('-f', '--file', type=str, help='Read question template from file. Use {title} or {question} as placeholder')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode (no visible browser)')
    parser.add_argument('-a', '--agents', type=str, help='Comma-separated list of agents (chatgpt,claude,gemini,grok)')
    parser.add_argument('-i', '--interactive', action='store_true', help='Run in interactive mode')
    parser.add_argument('--use-chrome-profile', action='store_true', default=True, help='Use your real Chrome profile (default: True)')
    parser.add_argument('--no-chrome-profile', dest='use_chrome_profile', action='store_false', help='Do not use real Chrome profile')

    args = parser.parse_args()

    if args.interactive:
        interactive_mode()
    elif args.file:
        # Read question template from file
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                question_template = f.read().strip()

            # If -q is provided with -f, treat -q as the variable to substitute
            if args.question:
                # Replace {title} and {question} placeholders with the provided value
                question = question_template.replace('{title}', args.question).replace('{question}', args.question)
                print(f"{Fore.CYAN}[INFO] Using template from file with title/question: {args.question}{Style.RESET_ALL}\n")
            else:
                # Just use the template as-is
                question = question_template

            agents = None
            if args.agents:
                agents = [a.strip().lower() for a in args.agents.split(',')]
            asyncio.run(main(question, args.headless, agents, args.use_chrome_profile))
        except Exception as e:
            print(f"{Fore.RED}Error reading file: {e}{Style.RESET_ALL}")
    elif args.question:
        agents = None
        if args.agents:
            agents = [a.strip().lower() for a in args.agents.split(',')]
        asyncio.run(main(args.question, args.headless, agents, args.use_chrome_profile))
    else:
        # If no arguments, start interactive mode
        interactive_mode()
