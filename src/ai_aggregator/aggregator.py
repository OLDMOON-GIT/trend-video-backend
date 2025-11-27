from typing import List, Dict
from colorama import Fore, Style, init

# Initialize colorama for colored output
init(autoreset=True)


class ResponseAggregator:
    """Aggregates and summarizes responses from multiple AI agents"""

    def __init__(self):
        self.responses: Dict[str, str] = {}

    def add_response(self, agent_name: str, response: str):
        """Add a response from an agent"""
        self.responses[agent_name] = response

    def display_responses(self):
        """Display all responses in a formatted way"""
        # 응답 전체 대신 요약만 출력
        import json
        for agent_name, response in self.responses.items():
            try:
                # JSON인 경우 요약 정보 추출
                data = json.loads(response)
                title = data.get('title', '제목 없음')[:50]
                scene_count = len(data.get('scenes', []))
                version = data.get('version', 'unknown')
                print(f"[{agent_name}] ✅ JSON 응답 ({len(response)}자) - 제목: {title}, 씬: {scene_count}개, 버전: {version}")
            except:
                # JSON이 아닌 경우 길이만 표시
                print(f"[{agent_name}] 📝 텍스트 응답 ({len(response)}자)")

    def _display_single_response(self, agent_name: str, response: str):
        """Display a single agent's response"""
        # Color mapping for different agents
        colors = {
            'ChatGPT': Fore.GREEN,
            'Claude': Fore.YELLOW,
            'Gemini': Fore.BLUE,
            'Grok': Fore.MAGENTA
        }

        color = colors.get(agent_name, Fore.WHITE)

        print(f"{color}{Style.BRIGHT}┌─ {agent_name} {Style.RESET_ALL}")
        print(f"{color}│{Style.RESET_ALL}")

        # Print response with line wrapping
        lines = response.split('\n')
        for line in lines:
            # Wrap long lines
            if len(line) > 75:
                words = line.split()
                current_line = ""
                for word in words:
                    if len(current_line) + len(word) + 1 <= 75:
                        current_line += word + " "
                    else:
                        print(f"{color}│{Style.RESET_ALL} {current_line.strip()}")
                        current_line = word + " "
                if current_line:
                    print(f"{color}│{Style.RESET_ALL} {current_line.strip()}")
            else:
                print(f"{color}│{Style.RESET_ALL} {line}")

        print(f"{color}└{'─'*78}{Style.RESET_ALL}\n")

    def generate_summary(self) -> str:
        """Generate a summary of all responses"""
        # Don't print anything, just return empty string
        return ""

    def _analyze_common_themes(self, responses: List[str]):
        """Analyze common themes across responses (simplified)"""
        # This is a simple implementation
        # For a more sophisticated analysis, you could use NLP libraries

        # Count common significant words
        from collections import Counter
        import re

        # Combine all responses
        all_text = " ".join(responses).lower()

        # Extract words (simple tokenization)
        words = re.findall(r'\b\w{4,}\b', all_text)  # Words with 4+ characters

        # Common stop words to exclude
        stop_words = {
            'that', 'this', 'with', 'from', 'have', 'been', 'were', 'their',
            'there', 'would', 'could', 'about', 'which', 'when', 'where',
            'these', 'those', 'they', 'what', 'your', 'more', 'some', 'into',
            'such', 'than', 'them', 'then', 'only', 'other', 'also', 'very',
            'here', 'just', 'even', 'much', 'make', 'made', 'well', 'back',
            'through', 'should', 'being', 'error'
        }

        # Filter out stop words
        filtered_words = [w for w in words if w not in stop_words]

        # Get most common words
        word_counts = Counter(filtered_words)
        common_words = word_counts.most_common(5)

        if common_words:
            print(f"\n{Fore.CYAN}Common themes across responses:{Style.RESET_ALL}")
            for word, count in common_words:
                if count >= 2:  # Only show if mentioned multiple times
                    print(f"  - {word} (mentioned {count} times)")

    def save_to_file(self, filename: str = "ai_responses.txt"):
        """Save all responses to a file"""
        import os
        import json
        from pathlib import Path

        # Save responses under repo-local ai_response directory (stable across environments)
        ai_response_dir = Path(__file__).resolve().parents[2] / "ai_response"
        ai_response_dir.mkdir(parents=True, exist_ok=True)

        # Full path to save file
        full_path = ai_response_dir / filename

        # Find the first valid JSON response
        valid_json = None
        for agent_name, response in self.responses.items():
            if response and not response.startswith("Error:"):
                # Try to extract JSON from the response
                cleaned = response.strip()
                # Remove code fences if present
                cleaned = cleaned.replace('```json', '').replace('```', '').strip()

                # Find JSON boundaries
                json_start = cleaned.find('{')
                json_end = cleaned.rfind('}')

                if json_start != -1 and json_end != -1:
                    json_str = cleaned[json_start:json_end+1]
                    try:
                        # Validate it's proper JSON
                        parsed = json.loads(json_str)
                        valid_json = json_str
                        print(f"{Fore.GREEN}[OK] Valid JSON response found from {agent_name}{Style.RESET_ALL}")
                        break
                    except json.JSONDecodeError:
                        print(f"{Fore.YELLOW}[WARN] Invalid JSON from {agent_name}, trying next agent...{Style.RESET_ALL}")
                        continue

        if valid_json:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(valid_json)
            print(f"\n{Fore.GREEN}[OK] Valid JSON response saved to {full_path}{Style.RESET_ALL}")
        else:
            # Fallback: save first non-error response
            for agent_name, response in self.responses.items():
                if response and not response.startswith("Error:"):
                    with open(full_path, 'w', encoding='utf-8') as f:
                        f.write(response)
                    print(f"\n{Fore.YELLOW}[WARN] No valid JSON found, saved raw response from {agent_name} to {full_path}{Style.RESET_ALL}")
                    break
            else:
                print(f"\n{Fore.RED}[ERROR] No valid responses to save{Style.RESET_ALL}")

    def get_all_responses(self) -> Dict[str, str]:
        """Get all responses as a dictionary"""
        return self.responses
