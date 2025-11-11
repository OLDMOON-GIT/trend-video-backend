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
        # Just print the raw response without any decoration
        for agent_name, response in self.responses.items():
            print(response)

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
        from pathlib import Path

        # Get the project root directory (where main.py is executed)
        project_root = Path.cwd()

        # Create src/scripts directory if it doesn't exist
        scripts_dir = project_root / "src" / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)

        # Full path to save file
        full_path = scripts_dir / filename

        with open(full_path, 'w', encoding='utf-8') as f:
            # Just write the raw response, nothing else
            for agent_name, response in self.responses.items():
                f.write(response)

        print(f"\n{Fore.GREEN}[OK] Responses saved to {full_path}{Style.RESET_ALL}")

    def get_all_responses(self) -> Dict[str, str]:
        """Get all responses as a dictionary"""
        return self.responses
