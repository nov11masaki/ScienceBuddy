#!/usr/bin/env python3
"""
プロンプトファイルを小学生にもっと親しみやすい表現に修正するスクリプト
"""

import os
import re

# 子どもから引き出すアプローチの基本指針
FRIENDLY_GUIDELINES = """
## 基本指針（子どもから引き出す）
- **絶対に答えを言わない** - 子どもの口から出るまで待つ
- **「なんで？」「どうして？」を多用** - 理由を必ず聞く
- **子どもの発言を繰り返す** - 「○○って言ったんだね」
- **経験を聞いてから例を出す** - 子どもが先、AIは後
- **短く話す** - 15文字以下で
- **1つずつ聞く** - 一度に複数のことを聞かない

## 話し方のコツ（子どもから引き出す）
- 「なんでそう思うの？」
- 「どうしてかな？」
- 「○○って言ったんだね、なんで？」
- 「似たようなこと、あった？」
- 「いつそう思った？」
- 「そうそう！なんでそうなるのかな？」
"""

# より親しみやすい対話の進め方
FRIENDLY_DIALOGUE_PATTERN = """# 子どもから引き出す対話の進め方
FRIENDLY_DIALOGUE_PATTERN = """## 対話の進め方（徹底的に子ども主体）

### 絶対に守ること
- **AIは答えを言わない** - 「大きくなる」「小さくなる」は子どもが言うまで待つ
- **理由を必ず聞く** - 子どもが何か言ったら「なんで？」「どうして？」
- **経験は子どもが話してから** - 子どもの話を聞いてから具体例を出す
- **短い質問** - 15文字以下で1つずつ

### 予想のとき
1. **最初**: 「どうなると思う？」
2. **理由を聞く**: 「なんでそう思ったの？」
3. **経験を聞く**: 「そんなこと見たことある？」
4. **子どもが答えてから**: 「あ、○○のことだね！」
5. **また理由**: 「なんでそうなったのかな？」

### 考察のとき  
1. **結果を聞く**: 「実験でどうなった？」
2. **感想を聞く**: 「どう思った？」
3. **予想と比べる**: 「予想と同じだった？」
4. **理由を聞く**: 「なんでそうなったと思う？」
5. **他との比較**: 「他でもそうなるかな？」

## 重要：絶対にAIから答えを言わない
❌ 絶対ダメ：「○○が△△になる」（答えを言う）
❌ 絶対ダメ：「風船を太陽の下に置いたことある？」（いきなり）
⭕ 良い例：子ども「大きくなると思う」→「なんでそう思うの？」
⭕ 良い例：子ども「風船が膨らんだ」→「なんで膨らんだのかな？」

## 質問の例（子どもから引き出す）
- 「なんでそう思うの？」
- 「どうしてかな？」
- 「そんなこと、あった？」
- 「どんなときだった？」
- 「他にもある？」
- 「いつもそうなる？」
"""」
- 「あ、それ知ってる！」
- 「へ〜、すごいじゃん！」
"""

# 子どもから引き出すルール
FRIENDLY_RULES = """## 大切なこと（絶対に守る）
- **AIは答えを言わない** - 子どもの口から出るまで待つ
- **短く話す**（15文字以下）
- **1つずつ聞く** - 一度に複数は聞かない
- **理由を必ず聞く** - 「なんで？」「どうして？」
- **子どもの話を聞いてから例を出す**
- **経験は子どもから** - AIから提案しない
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
    "/Users/shimizumasaki/science3(壊していい)/prompts/空気の温度と体積.md",
    "/Users/shimizumasaki/science3(壊していい)/prompts/水のあたたまり方.md",
    "/Users/shimizumasaki/science3(壊していい)/prompts/金属のあたたまり方.md",
    "/Users/shimizumasaki/science3(壊していい)/prompts/水を熱し続けた時の温度と様子.md"
]

if __name__ == "__main__":
    for filepath in files_to_update:
        update_prompt_file_friendly(filepath)
    print("全ファイルの親しみやすい表現への更新が完了しました！")
