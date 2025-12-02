"""
AI Aggregator package
- Provides helpers to run multiple AI agents and collect responses.
"""

# Avoid eagerly importing main to prevent runpy RuntimeWarning when
# executing `python -m src.ai_aggregator.main`.
def main(*args, **kwargs):
    from .main import main as _main
    return _main(*args, **kwargs)


def interactive_mode(*args, **kwargs):
    from .main import interactive_mode as _interactive_mode
    return _interactive_mode(*args, **kwargs)


from .aggregator import ResponseAggregator
from .queue_manager import QueueManager

__all__ = ['main', 'interactive_mode', 'ResponseAggregator', 'QueueManager']
__version__ = '1.0.0'
