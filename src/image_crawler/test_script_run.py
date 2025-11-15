#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import io

# UTF-8 출력 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

print("=" * 80)
print("🚀 테스트 스크립트 시작")
print("=" * 80)
print("✅ 출력이 정상적으로 동작합니다!")
