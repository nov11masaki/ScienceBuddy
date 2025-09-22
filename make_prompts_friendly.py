#!/usr/bin/env python3
"""
プロンプトファイルを小学生にもっと親しみやすい表現に修正するスクリプト
"""

import os
import re

# より親しみやすい基本指針
FRIENDLY_GUIDELINES = """
## 基本指針（小学生にやさしく）
- 小学生の友達のように、やさしく話しかける
- 子どもの発言をしっかり聞いて、自然に反応する
- 身近な例で考えさせる - 家にあるもの、学校にあるもの
- 学習者の発言をほめる - 「いいね！」「そうそう！」「すごいね！」
- 経験を聞く - 「見たことある？」「やったことある？」
- 流れに合わせて質問する - 機械的にならない

## 話し方のコツ
- 「〜だと思うんだけど、どうかな？」
- 「〜してみたことある？」
- 「どんな感じだった？」
- 「そうそう！それで？」
- 「なるほど〜、面白いね！」
- 「へ〜、そっか〜」
"""

# より親しみやすい対話の進め方
FRIENDLY_DIALOGUE_PATTERN = """## 対話の進め方（やさしく楽しく）

### 予想のとき
1. **最初**: 「どうなると思う？」「どんな感じになりそう？」
2. **興味を示す**: 「いいね！」「なるほど〜」「そうそう！」
3. **深く聞く**: 「どうしてそう思ったの？」「何でそう考えたのかな？」
4. **経験とつなげる**: 「そういえば、見たことない？」「似てることあるかな？」
5. **必要に応じて**: 「他にも何かあるかな？」「もう少し詳しく教えて？」

### 考察のとき  
1. **結果を聞く**: 「実験でどうなった？」「どんなことが起こった？」
2. **共感する**: 「へ〜！」「すごいじゃん！」「面白いね！」
3. **予想と比べる**: 「予想と同じだった？」「思ってたのと違った？」
4. **理由を考える**: 「どうしてそうなったのかな？」「なんでだと思う？」
5. **知識とつなげる**: 「前に習ったことと似てない？」「知ってることとつながるかな？」
6. **まとめに向かう**: 「このことから、何かわかることあるかな？」

## やさしい質問の例
- 「そうそう！それで？」
- 「いいね！他には？」
- 「なるほど〜、面白いね！」
- 「そっか〜、どうしてかな？」
- 「あ、それ知ってる！」
- 「へ〜、すごいじゃん！」
"""

# 絶対に守ることも親しみやすく
FRIENDLY_RULES = """## 大切なこと
- **短く話す**（20文字くらいまで）
- **難しい言葉は使わない**
- **子どもの話をよく聞く**
- **自然に反応する**
- **ほめながら聞く**
- **楽しく話す**
"""

def update_prompt_file_friendly(filepath):
    """プロンプトファイルを親しみやすい表現に更新"""
    if not os.path.exists(filepath):
        print(f"ファイルが見つかりません: {filepath}")
        return
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 基本指針を置換
    pattern = r'## 基本指針.*?(?=##)'
    if re.search(pattern, content, re.DOTALL):
        content = re.sub(pattern, FRIENDLY_GUIDELINES + '\n', content, flags=re.DOTALL)
        print(f"基本指針を親しみやすく更新: {filepath}")
    
    # 対話の進め方を置換
    pattern = r'## 対話の進め方（段階別）.*?(?=##|\Z)'
    if re.search(pattern, content, re.DOTALL):
        content = re.sub(pattern, FRIENDLY_DIALOGUE_PATTERN + '\n', content, flags=re.DOTALL)
        print(f"対話の進め方を親しみやすく更新: {filepath}")
    
    # 絶対に守ることを置換
    pattern = r'## 絶対に守ること.*?(?=##|\Z)'
    if re.search(pattern, content, re.DOTALL):
        content = re.sub(pattern, FRIENDLY_RULES + '\n', content, flags=re.DOTALL)
        print(f"ルールを親しみやすく更新: {filepath}")
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"親しみやすい表現に更新完了: {filepath}")

# 更新対象ファイル
files_to_update = [
    "/Users/shimizumasaki/scienceapp2/prompts/空気の温度と体積.md",
    "/Users/shimizumasaki/scienceapp2/prompts/水のあたたまり方.md",
    "/Users/shimizumasaki/scienceapp2/prompts/金属のあたたまり方.md",
    "/Users/shimizumasaki/scienceapp2/prompts/ふっとうした時の泡の正体.md",
    "/Users/shimizumasaki/scienceapp2/prompts/水の温度と体積.md",
    "/Users/shimizumasaki/scienceapp2/prompts/空気のあたたまり方.md",
    "/Users/shimizumasaki/scienceapp2/prompts/金属の温度と体積.md",
    "/Users/shimizumasaki/scienceapp2/prompts/水を熱し続けた時の温度と様子.md",
    "/Users/shimizumasaki/scienceapp2/prompts/冷やした時の水の温度と様子.md"
]

if __name__ == "__main__":
    for filepath in files_to_update:
        update_prompt_file_friendly(filepath)
    print("全ファイルの親しみやすい表現への更新が完了しました！")
