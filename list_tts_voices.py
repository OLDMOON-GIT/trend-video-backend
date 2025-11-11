#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""List available Edge TTS voices"""

import asyncio
import edge_tts
import sys
import io

# UTF-8 출력 설정
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

async def main():
    voices = await edge_tts.list_voices()

    # Filter Korean voices
    korean_voices = [v for v in voices if 'ko-KR' in v['Locale']]

    print("=" * 80)
    print("Available Korean TTS Voices (Edge TTS)")
    print("=" * 80)
    print()

    for i, voice in enumerate(korean_voices, 1):
        print(f"{i}. {voice.get('ShortName', voice.get('Name', 'Unknown'))}")
        print(f"   Gender: {voice.get('Gender', 'Unknown')}")
        print(f"   Locale: {voice.get('Locale', 'Unknown')}")
        if 'FriendlyName' in voice:
            print(f"   Friendly Name: {voice['FriendlyName']}")
        print()

    print("=" * 80)
    print(f"Total: {len(korean_voices)} Korean voices")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
