#!/usr/bin/env python
"""
AI Aggregator Runner
백엔드에서 AI Aggregator를 쉽게 실행하기 위한 스크립트
"""
import sys
import os
from pathlib import Path

# Add src to Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir / "src"))

# Import and run the main module
from ai_aggregator.main import main, interactive_mode
import argparse
import asyncio

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Multi-AI Aggregator - Query multiple AI models at once')
    parser.add_argument('-q', '--question', type=str, help='Question to ask all AI models')
    parser.add_argument('-f', '--file', type=str, help='Read question template from file')
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
            file_path = backend_dir / args.file
            with open(file_path, 'r', encoding='utf-8') as f:
                question_template = f.read().strip()

            if args.question:
                question = question_template.replace('{title}', args.question).replace('{question}', args.question)
            else:
                question = question_template

            agents = None
            if args.agents:
                agents = [a.strip().lower() for a in args.agents.split(',')]
            asyncio.run(main(question, args.headless, agents, args.use_chrome_profile))
        except Exception as e:
            print(f"Error reading file: {e}")
    elif args.question:
        agents = None
        if args.agents:
            agents = [a.strip().lower() for a in args.agents.split(',')]
        asyncio.run(main(args.question, args.headless, agents, args.use_chrome_profile))
    else:
        # If no arguments, start interactive mode
        interactive_mode()
