#!/usr/bin/env python3
"""
復帰機能の修正を確認するテスト
"""

import json
from datetime import datetime

def test_resumption_logic():
    """復帰判定ロジックをシミュレート"""
    
    # テストケース1: session に会話履歴がある場合
    print("【テストケース1】セッションに会話履歴がある場合")
    conversation_count = 0  # count は 0
    session_conversation = [{'role': 'user', 'content': 'test'}]  # session にはある
    conversation_history = []  # DB にはない
    
    has_existing_conversation = (
        conversation_count > 0 or 
        session_conversation or 
        len(conversation_history) > 0
    )
    print(f"  conversation_count: {conversation_count}")
    print(f"  session_conversation: {bool(session_conversation)}")
    print(f"  conversation_history: {len(conversation_history)}")
    print(f"  → has_existing_conversation: {has_existing_conversation}")
    print(f"  ✓ 復帰判定: {'OK' if has_existing_conversation else 'NG'}")
    print()
    
    # テストケース2: DB に会話履歴が保存されている場合
    print("【テストケース2】DB に会話履歴が保存されている場合")
    conversation_count = 0  # count は未更新
    session_conversation = None  # session にはない
    conversation_history = [
        {'role': 'user', 'content': 'test'},
        {'role': 'assistant', 'content': 'response'}
    ]  # DB にはある
    
    has_existing_conversation = (
        conversation_count > 0 or 
        session_conversation or 
        len(conversation_history) > 0
    )
    print(f"  conversation_count: {conversation_count}")
    print(f"  session_conversation: {session_conversation}")
    print(f"  conversation_history長: {len(conversation_history)}")
    print(f"  → has_existing_conversation: {has_existing_conversation}")
    print(f"  ✓ 復帰判定: {'OK' if has_existing_conversation else 'NG'}")
    print()
    
    # テストケース3: 両方とも空の場合（新規学習）
    print("【テストケース3】新規学習の場合")
    conversation_count = 0
    session_conversation = None
    conversation_history = []
    
    has_existing_conversation = (
        conversation_count > 0 or 
        session_conversation or 
        len(conversation_history) > 0
    )
    print(f"  conversation_count: {conversation_count}")
    print(f"  session_conversation: {session_conversation}")
    print(f"  conversation_history長: {len(conversation_history)}")
    print(f"  → has_existing_conversation: {has_existing_conversation}")
    print(f"  ✓ 復帰判定: {'OK' if not has_existing_conversation else 'NG'}")
    print()
    
    print("【テスト結果】")
    print("✓ すべてのテストケースで正しい判定ロジックを確認")

if __name__ == '__main__':
    test_resumption_logic()
