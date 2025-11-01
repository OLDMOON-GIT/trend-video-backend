"""
Multi-step refinement script with email notification
막장드라마 제목을 여러 단계로 정제하여 최종 결과를 이메일로 전송
"""

import asyncio
import sys
import os
import uuid
import shutil
from playwright.async_api import async_playwright
from .agents import ChatGPTAgent, ClaudeAgent, GeminiAgent
from .aggregator import ResponseAggregator
from colorama import Fore, Style, init
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from .queue_manager import QueueManager

# Fix Windows console encoding
if sys.platform == 'win32':
    import io
    # Only wrap if not already wrapped
    if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        except:
            pass
    if not isinstance(sys.stderr, io.TextIOWrapper) or sys.stderr.encoding != 'utf-8':
        try:
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        except:
            pass
    os.system('chcp 65001 > nul')

# Initialize colorama
init(autoreset=True)


def send_email(to_email: str, subject: str, body: str):
    """Send email with results"""
    try:
        # Gmail SMTP 설정 (사용자가 설정해야 함)
        # 앱 비밀번호를 사용해야 합니다: https://myaccount.google.com/apppasswords

        # .env 파일에서 이메일 설정 가져오기
        env_file = os.path.join(os.getcwd(), '.env')
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()

        # 환경 변수에서 이메일 설정 가져오기
        from_email = os.environ.get('GMAIL_USER')
        password = os.environ.get('GMAIL_APP_PASSWORD')

        if not from_email or not password:
            print(f"{Fore.YELLOW}[WARN] Email credentials not found in environment variables{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}[INFO] Set GMAIL_USER and GMAIL_APP_PASSWORD to enable email{Style.RESET_ALL}")

            # 결과를 파일로 저장
            filename = f"final_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"Subject: {subject}\n\n")
                f.write(body)
            print(f"{Fore.GREEN}[OK] Results saved to {filename}{Style.RESET_ALL}")
            return

        # 이메일 생성
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        # Gmail SMTP 서버로 전송
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(from_email, password)
            server.send_message(msg)

        print(f"{Fore.GREEN}[OK] Email sent to {to_email}{Style.RESET_ALL}")

    except Exception as e:
        print(f"{Fore.RED}[ERROR] Failed to send email: {e}{Style.RESET_ALL}")

        # 이메일 전송 실패 시 파일로 저장
        filename = f"final_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"Subject: {subject}\n\n")
            f.write(body)
        print(f"{Fore.GREEN}[OK] Results saved to {filename} instead{Style.RESET_ALL}")


async def run_multi_agent_query(question: str, agents: list, context) -> str:
    """Run a query across multiple agents and collect responses"""
    aggregator = ResponseAggregator()

    print(f"\n{Fore.CYAN}Question:{Style.RESET_ALL} {question}")
    print(f"{Fore.CYAN}Agents:{Style.RESET_ALL} {', '.join([a.get_name() for a in agents])}\n")

    # Phase 1: Send questions sequentially
    print(f"{Fore.CYAN}[*] Sending questions...{Style.RESET_ALL}\n")
    for agent in agents:
        try:
            print(f"{Fore.CYAN}[{agent.get_name()}] Sending question...{Style.RESET_ALL}")
            await agent.send_question_async(question)
            print(f"{Fore.GREEN}[{agent.get_name()}] [OK] Question sent!{Style.RESET_ALL}\n")
        except Exception as e:
            error_msg = f"Failed to send question: {str(e)}"
            print(f"{Fore.RED}[{agent.get_name()}] {error_msg}{Style.RESET_ALL}\n")
            aggregator.add_response(agent.get_name(), f"Error: {error_msg}")

    # Phase 2: Wait for all responses in parallel
    print(f"{Fore.CYAN}[*] Waiting for responses...{Style.RESET_ALL}\n")

    async def wait_for_response(agent):
        try:
            print(f"{Fore.CYAN}[{agent.get_name()}] Waiting...{Style.RESET_ALL}")
            response = await agent.wait_for_complete_response()
            aggregator.add_response(agent.get_name(), response)
            print(f"{Fore.GREEN}[{agent.get_name()}] [OK] Response received!{Style.RESET_ALL}")
        except Exception as e:
            error_msg = f"Failed to get response: {str(e)}"
            print(f"{Fore.RED}[{agent.get_name()}] {error_msg}{Style.RESET_ALL}")
            aggregator.add_response(agent.get_name(), f"Error: {error_msg}")

    wait_tasks = [wait_for_response(agent) for agent in agents if agent.page]
    if wait_tasks:
        await asyncio.gather(*wait_tasks, return_exceptions=True)

    # Combine all responses
    combined_response = "\n\n=== 다음은 여러 AI의 답변입니다 ===\n\n"
    for agent_name, response in aggregator.get_all_responses().items():
        combined_response += f"[{agent_name}]\n{response}\n\n"

    return combined_response


async def main(headless: bool = False, use_queue: bool = True):
    """Main refinement workflow"""

    # Create unique profile for this execution
    execution_id = str(uuid.uuid4())[:8]

    print(f"\n{Fore.YELLOW}{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}{Style.BRIGHT}Multi-Step AI Refinement with Email{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}{Style.BRIGHT}Execution ID: {execution_id}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}{Style.BRIGHT}{'='*80}{Style.RESET_ALL}\n")

    # Configuration
    initial_question = "막장드라마 제목 10개 써줘 (띄어써줘, 공백 제외 30자 이상)"
    refine_question_1 = "여기서 탑 3를 뽑아줘 (번호와 제목만 간단히 나열)"
    refine_question_2 = "여기서 탑 3를 뽑아줘 (번호와 제목만 간단히 나열)"
    recipient_email = "moony75@gmail.com"

    # Use base profile directly with queue system (no copying needed)
    automation_profile = os.path.join(os.getcwd(), '.chrome-automation-profile')

    # Queue management for concurrent requests
    queue_manager = None
    if use_queue:
        queue_manager = QueueManager()
        print(f"{Fore.CYAN}[QUEUE] Waiting for turn...{Style.RESET_ALL}")
        if not queue_manager.acquire_lock(timeout=600):
            print(f"{Fore.RED}[ERROR] Could not acquire queue lock{Style.RESET_ALL}")
            return
        print(f"{Fore.GREEN}[QUEUE] Lock acquired! Starting execution...{Style.RESET_ALL}\n")

    try:
        async with async_playwright() as p:
            import pathlib

            # Create profile directory if not exists
            pathlib.Path(automation_profile).mkdir(exist_ok=True)

            print(f"{Fore.YELLOW}[INFO] Using profile: {automation_profile}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}[INFO] Mode: {'Headless' if headless else 'Visible'}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}[INFO] Queue system ensures only one execution at a time{Style.RESET_ALL}\n")

            try:
                context = await p.chromium.launch_persistent_context(
                    automation_profile,
                    headless=headless,
                    channel='chrome',
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-first-run',
                        '--no-default-browser-check',
                        '--disable-features=IsolateOrigins,site-per-process',
                        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                    ],
                    accept_downloads=True,
                    ignore_https_errors=True,
                    timeout=60000,
                )

                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)

                browser = context
            except Exception as e:
                print(f"{Fore.YELLOW}[WARN] Could not launch Chrome, using Chromium: {e}{Style.RESET_ALL}")
                context = await p.chromium.launch_persistent_context(
                    automation_profile,
                    headless=headless,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-first-run',
                        '--no-default-browser-check',
                        '--disable-features=IsolateOrigins,site-per-process',
                        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                    ],
                    accept_downloads=True,
                    ignore_https_errors=True,
                    timeout=60000,
                )

                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)

                browser = context

            # Close the default blank page that opens automatically
            if len(browser.pages) > 0:
                try:
                    await browser.pages[0].close()
                    print(f"{Fore.YELLOW}[INFO] Closed default blank page{Style.RESET_ALL}\n")
                except:
                    pass

            # Create agent instances (skip_login_check=False to enable login prompt)
            agents = [
                ChatGPTAgent(browser, headless, False),
                ClaudeAgent(browser, headless, False),
                GeminiAgent(browser, headless, False)
            ]

            # Initialize all agents
            print(f"{Fore.CYAN}[*] Initializing agents...{Style.RESET_ALL}\n")
            for agent in agents:
                try:
                    await agent.initialize()
                    print(f"{Fore.GREEN}[{agent.get_name()}] Page loaded{Style.RESET_ALL}")
                    await asyncio.sleep(3)  # Longer wait after page load
                    await agent.login()
                    print(f"{Fore.GREEN}[{agent.get_name()}] [OK] Initialized{Style.RESET_ALL}")
                    await asyncio.sleep(2)  # Longer wait between agents
                except Exception as e:
                    print(f"{Fore.RED}[{agent.get_name()}] Failed to initialize: {e}{Style.RESET_ALL}")

            # Step 1: Initial question
            print(f"\n{Fore.YELLOW}{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}{Style.BRIGHT}STEP 1: Initial Question{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")

            response_1 = await run_multi_agent_query(initial_question, agents, browser)

            # Step 2: First refinement
            print(f"\n{Fore.YELLOW}{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}{Style.BRIGHT}STEP 2: First Refinement{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")

            combined_question_1 = f"{response_1}\n\n{refine_question_1}"
            response_2 = await run_multi_agent_query(combined_question_1, agents, browser)

            # Step 3: Second refinement
            print(f"\n{Fore.YELLOW}{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}{Style.BRIGHT}STEP 3: Second Refinement{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")

            combined_question_2 = f"{response_2}\n\n{refine_question_2}"
            final_response = await run_multi_agent_query(combined_question_2, agents, browser)

            # Send email with final results
            print(f"\n{Fore.YELLOW}{Style.BRIGHT}{'='*80}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}{Style.BRIGHT}SENDING RESULTS{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}{Style.BRIGHT}{'='*80}{Style.RESET_ALL}\n")

            subject = f"막장드라마 제목 최종 결과 - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            body = f"""막장드라마 제목 정제 최종 결과

=== 초기 질문 ===
{initial_question}

=== 1차 정제 ===
{refine_question_1}

=== 2차 정제 ===
{refine_question_2}

=== 최종 결과 ===
{final_response}

---
Generated by Multi-AI Aggregator
Execution ID: {execution_id}
"""

            send_email(recipient_email, subject, body)

            print(f"\n{Fore.GREEN}{Style.BRIGHT}Done!{Style.RESET_ALL}")
            print(f"\n{Fore.YELLOW}Browser will remain open. Close manually or press Ctrl+C to exit.{Style.RESET_ALL}")

            # Keep the script running (browser stays open)
            await asyncio.sleep(999999)  # Sleep indefinitely

    finally:
        # Release queue lock
        if queue_manager:
            queue_manager.release_lock()
            print(f"{Fore.GREEN}[QUEUE] Lock released{Style.RESET_ALL}\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Multi-step AI refinement with email')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode (no visible browser)')
    parser.add_argument('--no-queue', action='store_true', help='Disable queue system (not recommended for server)')
    parser.add_argument('--initial-question', type=str,
                        default="막장드라마 제목 10개 써줘 (띄어써줘, 공백 제외 대략 30자)",
                        help='Initial question to ask')
    parser.add_argument('--email', type=str, default='moony75@gmail.com',
                        help='Recipient email address')

    args = parser.parse_args()

    asyncio.run(main(headless=args.headless, use_queue=not args.no_queue))
