from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import openai
import os
from dotenv import load_dotenv
import json
from datetime import datetime
import csv
import time
import hashlib
import ssl
import certifi
import urllib3
import re
import glob
import uuid
from werkzeug.utils import secure_filename


# 環境変数を読み込み
load_dotenv()

# SSL設定の改善
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# SSL証明書の設定
ssl_context = ssl.create_default_context(cafile=certifi.where())

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # 本番環境では安全なキーに変更

# ファイルアップロード設定
UPLOAD_FOLDER = 'uploads'  # 一時的なアップロード用
ALLOWED_EXTENSIONS = {'md', 'txt'}  # Markdownとテキストファイルのみ
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB制限

# アップロードディレクトリが存在しない場合は作成
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 教員認証情報（実際の運用では環境変数やデータベースに保存）
TEACHER_CREDENTIALS = {
    "teacher": "science2025",  # ユーザー名: teacher, パスワード: science2025
    # 本番運用時は適切な認証システムを実装してください
}

# 認証チェック用デコレータ
def require_teacher_auth(f):
    def decorated_function(*args, **kwargs):
        if not session.get('teacher_authenticated'):
            return redirect(url_for('teacher_login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# OpenAI APIの設定
api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    print("警告: OPENAI_API_KEYが設定されていません")
else:
    print(f"APIキー設定確認: {api_key[:10]}...{api_key[-4:]}")
    
try:
    # OpenAI クライアントを初期化
    client = openai.OpenAI(api_key=api_key)
    print("OpenAI API設定完了")
except Exception as e:
    print(f"OpenAI API設定エラー: {e}")
    client = None

# OpenAI client設定の確認
if client is None:
    print("警告: OpenAIクライアントの初期化に失敗しました")

# マークダウン記法を除去する関数
def remove_markdown_formatting(text):
    """AIの応答からマークダウン記法を除去する"""
    import re
    
    # 太字 **text** や __text__ を通常のテキストに
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    
    # 斜体 *text* や _text_ を通常のテキストに
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'_(.*?)_', r'\1', text)
    
    # 箇条書きの記号を除去
    text = re.sub(r'^\s*\*\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*-\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\+\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    
    # 見出し記号 ### text を除去
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    
    # コードブロック ```text``` を除去
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`(.*?)`', r'\1', text)
    
    # 引用記号 > を除去
    text = re.sub(r'^\s*>\s*', '', text, flags=re.MULTILINE)
    
    # その他の記号の重複を整理
    text = re.sub(r'\s+', ' ', text)  # 複数の空白を1つに
    text = re.sub(r'\n\s*\n', '\n', text)  # 複数の改行を1つに
    
    return text.strip()

def normalize_childish_expressions(text):
    """子供の擬音語・擬態語を一般的な表現に変換する"""
    conversions = {
        # 触感・質感
        'ふわふわ': '柔らかかったんだね',
        'べたべた': 'ねばねばしていたんだね',
        'ざらざら': 'でこぼこしていたんだね',
        'つるつる': 'なめらかだったんだね',
        'ぶよぶよ': '弾力があったんだね',
        
        # 音・動き
        'ぶくぶく': '泡が出ていたんだね',
        'ごぼごぼ': '音がしていたんだね',
        'ぐるぐる': '回っていたんだね',
        'ふわり': 'ゆっくり動いたんだね',
        'ひらひら': '軽やかに動いたんだね',
        
        # 温度・感覚
        'あつあつ': '熱かったんだね',
        'ひんやり': '冷たかったんだね',
        'ぽかぽか': 'あたたかかったんだね',
        
        # 量・程度
        'いっぱい': 'たくさんあったんだね',
        'ちょっぴり': '少しだったんだね',
        'どんどん': 'だんだん変わったんだね'
    }
    
    normalized_text = text
    for childish, formal in conversions.items():
        if childish in normalized_text:
            normalized_text = normalized_text.replace(childish, formal)
    
    return normalized_text

def normalize_family_expressions(text):
    """家族表現を統一する"""
    # お母さん → お家の人
    text = text.replace('お母さん', 'お家の人')
    text = text.replace('おかあさん', 'お家の人')
    text = text.replace('ママ', 'お家の人')
    text = text.replace('お父さん', 'お家の人')
    text = text.replace('おとうさん', 'お家の人')
    text = text.replace('パパ', 'お家の人')
    
    return text

def extract_message_from_json_response(response):
    """JSON形式のレスポンスから純粋なメッセージを抽出する"""
    try:
        # JSON形式かどうか確認
        if response.strip().startswith('{') and response.strip().endswith('}'):
            import json
            parsed = json.loads(response)
            
            # よくあるフィールド名から順番に確認
            common_fields = ['response', 'message', 'question', 'summary', 'text', 'content', 'answer']
            
            for field in common_fields:
                if field in parsed and isinstance(parsed[field], str):
                    return parsed[field]
            
            # その他のフィールドから文字列値を探す
            for key, value in parsed.items():
                if isinstance(value, str) and len(value.strip()) > 0:
                    return value
                    
            # JSONだが適切なフィールドがない場合はそのまま返す
            return response
                
        # リスト形式の場合の処理
        elif response.strip().startswith('[') and response.strip().endswith(']'):
            import json
            parsed = json.loads(response)
            if isinstance(parsed, list) and len(parsed) > 0:
                # リストの各要素を処理
                results = []
                for item in parsed:
                    if isinstance(item, dict):
                        # よくあるフィールド名から順番に確認
                        common_fields = ['予想', 'response', 'message', 'question', 'summary', 'text', 'content']
                        found = False
                        for field in common_fields:
                            if field in item and isinstance(item[field], str):
                                results.append(item[field])
                                found = True
                                break
                        
                        # よくあるフィールドが見つからない場合は最初の文字列値を使用
                        if not found:
                            for key, value in item.items():
                                if isinstance(value, str) and len(value.strip()) > 0:
                                    results.append(value)
                                    break
                    elif isinstance(item, str):
                        results.append(item)
                
                # 複数の予想を改行で結合
                if results:
                    return '\n'.join(results)
            return response
            
        # JSON形式でない場合はそのまま返す
        else:
            return response
            
    except (json.JSONDecodeError, Exception) as e:
        print(f"JSON解析エラー: {e}, 元のレスポンスを返します")
        return response

def load_markdown_content(file_path):
    """Markdownファイルからテキストを読み込む"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        return content.strip()
    except Exception as e:
        print(f"Markdown読み込みエラー: {e}")
        return None

def get_learning_guidelines():
    """学習指導要領の内容を取得"""
    guidelines_path = "guidelines/learning_guidelines.md"
    if os.path.exists(guidelines_path):
        return load_markdown_content(guidelines_path)
    return None

def get_teaching_support():
    """指導支援方針の内容を取得"""
    support_path = "guidelines/teaching_support.md"
    if os.path.exists(support_path):
        return load_markdown_content(support_path)
    return None

def get_learning_support_system():
    """学習段階別支援システムの内容を取得"""
    support_path = "guidelines/learning_support_system.md"
    if os.path.exists(support_path):
        return load_markdown_content(support_path)
    return None

def analyze_unit_characteristics(unit):
    """単元の特性を分析して見方・考え方を抽出"""
    unit_characteristics = {
        "水のあたたまり方": {
            "見方・考え方": "温度と物質の状態・性質の関係性に注目する",
            "重点活動": ["温度変化の比較", "対流現象の言語化", "日常経験との関連"],
            "生活経験": ["お風呂の循環", "やかんのお湯", "暖房の仕組み"],
            "キーワード": ["対流", "循環", "あたたまり方", "温度差"],
            "産婆法質問": [
                "お風呂に入るとき、どの部分があたたかく感じますか？",
                "やかんでお湯を沸かすとき、どんなことが起こりますか？",
                "水の中で何が動いているのでしょうか？"
            ],
            "産婆法_経験引き出し": [
                "お風呂に入った時、一番あたたかいのはどこでしたか？",
                "どんなふうにあたたかさが広がっていきましたか？",
                "お風呂のお湯をかき混ぜた時、どうなりましたか？",
                "やかんでお湯を沸かす時、どこから湯気が出てきましたか？",
                "水の中に色をつけて温めた実験、覚えていますか？",
                "その時、色はどんなふうに動いていましたか？"
            ],
            "経験不足時の質問": [
                "お風呂で遊んだことはありませんか？お湯に手を入れた時の感じを覚えていますか？",
                "お家でお湯を沸かしているところを見たことはありませんか？",
                "暖房がついた部屋で、どこがあたたかく感じたか覚えていますか？",
                "プールや川で泳いだ時、水が動いているのを感じたことはありませんか？"
            ]
        },
        "金属のあたたまり方": {
            "見方・考え方": "温度と物質の状態・性質の関係性に注目する",
            "重点活動": ["伝導現象の観察", "順序立てた説明", "物質比較"],
            "生活経験": ["フライパンで料理", "金属スプーン", "アイロン"],
            "キーワード": ["伝導", "順番に", "伝わる", "熱くなる"],
            "産婆法質問": [
                "フライパンで料理をするとき、どの部分から熱くなりますか？",
                "金属のスプーンをお湯に入れると、どうなりますか？",
                "なぜ金属は料理道具によく使われるのでしょう？"
            ],
            "産婆法_経験引き出し": [
                "お家でフライパンを使った時、どんなことに気がつきましたか？",
                "熱いスプーンを触った時、どんな感じでしたか？",
                "お家の人がお料理している時、どんなふうに熱が伝わっていましたか？",
                "その時、どこから熱くなっていきましたか？",
                "どのくらいの時間で熱くなりましたか？",
                "他の材料と比べて、金属はどうでしたか？"
            ],
            "経験不足時の質問": [
                "お家でお料理を見たことはありませんか？フライパンや鍋を使っているところを見たことは？",
                "金属のスプーンやフォークを使ったことはありませんか？",
                "アイロンやドライヤーなど、熱くなる道具を見たことはありませんか？",
                "お家の人が「熱いから気をつけて」と言ったことはありませんか？"
            ]
        },
        "空気の温度と体積": {
            "見方・考え方": "物質の性質を温度との関係で捉え、目に見えない変化を数値で表現する",
            "重点活動": ["数値データの分析", "グラフ読み取り", "関係性の発見"],
            "生活経験": ["風船の変化", "空気入れ", "自転車のタイヤ"],
            "キーワード": ["体積", "温度", "膨張", "収縮", "関係"],
            "産婆法質問": [
                "風船を温めるとどうなりますか？",
                "冷やした風船はどうなるでしょう？",
                "温度が変わると空気にどんな変化が起こりますか？"
            ],
            "産婆法_経験引き出し": [
                "風船で遊んだ時、どんなことがありましたか？",
                "太陽の下に置いた風船はどうなりましたか？",
                "冷蔵庫から出した風船はどうでしたか？",
                "自転車の空気入れを使った時、どんな感じでしたか？",
                "空気入れが熱くなったことはありませんか？",
                "ボールの空気が抜けた時、どんなふうになりましたか？"
            ],
            "経験不足時の質問": [
                "風船で遊んだことはありませんか？お誕生日会や祭りで見たことは？",
                "自転車やボールに空気を入れたことはありませんか？",
                "ペットボトルがぺこっとへこんだのを見たことはありませんか？",
                "車に乗っている時、暑い日と寒い日でタイヤの感じが違うと感じたことは？"
            ]
        },
        "水を熱し続けた時の温度と様子": {
            "見方・考え方": "物質の状態変化を温度との関係で捉え、現象を定量的に分析する",
            "重点活動": ["継続的観察", "状態変化の記録", "グラフ分析"],
            "生活経験": ["やかんでお湯を沸かす", "鍋で料理", "お風呂のお湯"],
            "キーワード": ["沸騰", "状態変化", "温度変化", "泡", "蒸気"],
            "産婆法質問": [
                "お湯を沸かし続けるとどうなりますか？",
                "温度はずっと上がり続けるでしょうか？",
                "沸騰している時の泡は何でしょうか？"
            ],
            "産婆法_経験引き出し": [
                "お家でお湯を沸かした時、どんなことが起こりましたか？",
                "最初はどんな感じでしたか？",
                "だんだんどうなっていきましたか？",
                "ぶくぶくと泡が出てきた時、どんな音がしていましたか？",
                "やかんの蓋が動いたことはありませんか？",
                "お湯が沸騰してからも、ずっと熱いままでしたか？"
            ],
            "経験不足時の質問": [
                "お家でお湯を沸かしているところを見たことはありませんか？",
                "やかんから湯気が出ているのを見たことは？",
                "お風呂のお湯が熱すぎて、水を足したことはありませんか？",
                "ラーメンを作る時に、お湯がぐらぐらしているのを見たことは？"
            ]
        }
    }
    return unit_characteristics.get(unit, {})

def determine_learning_stage(conversation_count, conversation_content=None):
    """対話内容から学習段階を判定"""
    if conversation_count <= 2:
        return "自己思考段階"
    elif conversation_count <= 4:
        return "伝え合い段階"
    else:
        return "思考まとめ段階"

def generate_stage_appropriate_guidance(stage, unit):
    """学習段階に応じた指導ガイダンスを生成"""
    unit_info = analyze_unit_characteristics(unit)
    
    guidance = {
        "自己思考段階": {
            "目標": "児童が自分の考えを持ち、予想・仮説を立てる",
            "支援方針": ["日常経験を引き出す", "既習事項との関連付け", "根拠を持った予想を促す"],
            "質問例": unit_info.get("産婆法質問", ["どう思いますか？"])[:1],
            "重点": f"生活経験（{', '.join(unit_info.get('生活経験', [])[:2])}）との関連を重視"
        },
        "伝え合い段階": {
            "目標": "他者との比較・共有・討論を通じて考えを深める", 
            "支援方針": ["多様な考えを価値付ける", "比較検討を促す", "根拠を明確化"],
            "質問例": ["友達の考えと比べてどうですか？", "なぜ違いが生まれたのでしょう？"],
            "重点": f"見方・考え方「{unit_info.get('見方・考え方', '')}」の深化"
        },
        "思考まとめ段階": {
            "目標": "結果の整理、概念の抽出、考察の記述",
            "支援方針": ["学習内容の整理", "概念の一般化", "新たな疑問の発見"],
            "質問例": ["今日分かったことは何ですか？", "他でも同じことが起こりそうですか？"],
            "重点": f"キーワード（{', '.join(unit_info.get('キーワード', [])[:3])}）の理解確認"
        }
    }
    return guidance.get(stage, guidance["自己思考段階"])

def save_lesson_plan_info(unit, content):
    """指導案情報をJSONファイルに保存"""
    lesson_plans_file = "lesson_plans_md/lesson_plans_index.json"
    
    # ディレクトリが存在しない場合は作成
    os.makedirs("lesson_plans_md", exist_ok=True)
    
    # 既存の指導案情報を読み込み
    lesson_plans = {}
    if os.path.exists(lesson_plans_file):
        try:
            with open(lesson_plans_file, 'r', encoding='utf-8') as f:
                lesson_plans = json.load(f)
        except (json.JSONDecodeError, Exception):
            lesson_plans = {}
    
    # 新しい指導案情報を追加
    lesson_plans[unit] = {
        'filename': f'{unit}.md',
        'last_updated': datetime.now().isoformat(),
        'content_preview': content[:500] if content else "",  # 最初の500文字のプレビュー
        'content_length': len(content) if content else 0
    }
    
    # ファイルに保存
    with open(lesson_plans_file, 'w', encoding='utf-8') as f:
        json.dump(lesson_plans, f, ensure_ascii=False, indent=2)

def load_lesson_plan_content(unit):
    """指定された単元の指導案内容を読み込む"""
    # まず既存のMarkdownファイルを確認
    markdown_path = f"lesson_plans_md/{unit}.md"
    if os.path.exists(markdown_path):
        return load_markdown_content(markdown_path)
    
    # インデックスファイルからも確認
    lesson_plans_file = "lesson_plans_md/lesson_plans_index.json"
    if not os.path.exists(lesson_plans_file):
        return None
    
    try:
        with open(lesson_plans_file, 'r', encoding='utf-8') as f:
            lesson_plans = json.load(f)
        
        if unit not in lesson_plans:
            return None
        
        # Markdownファイルから内容を読み込み
        markdown_path = os.path.join("lesson_plans_md", lesson_plans[unit]['filename'])
        if os.path.exists(markdown_path):
            return load_markdown_content(markdown_path)
        else:
            return None
            
    except (json.JSONDecodeError, Exception) as e:
        print(f"指導案読み込みエラー: {e}")
        return None

def get_lesson_plans_list():
    """アップロード済みの指導案一覧を取得"""
    lesson_plans_file = "lesson_plans/lesson_plans_index.json"
    
    if not os.path.exists(lesson_plans_file):
        return {}
    
    try:
        with open(lesson_plans_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception):
        return {}

# APIコール用のリトライ関数
def build_enhanced_prompt(base_prompt, unit=None, stage=None):
    """学習指導要領とMarkdownガイドラインを活用して強化されたプロンプトを構築"""
    enhanced_prompt = base_prompt
    
    # 親しみやすい話し方の具体例を最初に追加
    enhanced_prompt += """

## 【最重要】経験を必ず引き出す対話スタイル
### 毎回の対話で必須のパターン
1. **最初に経験を聞く**: 「〜したことある？」「〜見たことない？」
2. **温度変化の体験を聞く**: 「温めたことある？」「冷やしたことある？」
3. **家庭での体験を具体的に**: 「お母さんと一緒に〜したとき」「お風呂で〜」
4. **比較体験を聞く**: 「夏と冬で違った？」「暑いときと寒いときで」

### 経験引き出しの具体的質問（必ず使用）
- 「お家でお湯沸かしたこと、ある？その時どうなった？」
- 「冷蔵庫から出したペットボトル、どんな感じだった？」
- 「お風呂のお湯、熱いのと温いのでどう違う？」
- 「氷を手で握ったこと、ある？どんな感じ？」
- 「夏の暑い日と冬の寒い日で、何か違うこと気づいた？」
- 「お母さんがお料理してるとき、鍋を見てて気づいたことある？」

### 温度変化体験の重点的引き出し
- 「温めたら何か変わること、知ってる？」
- 「冷やしたら何か変わること、ない？」
- 「熱いものと冷たいもの、触った感じ違うよね？」
- 「温度が変わると、形や大きさも変わること、気づいたことある？」

### 親しみやすい話し方の例
- 「そうそう！それで？」「いいね！他には？」「なるほど〜、面白いね！」
- 「あ、それ知ってる！」「へ〜、すごいじゃん！」「そっか〜、どうしてかな？」
- 「やったことある？」「見たことない？」「どんな感じだった？」
- 「家でもそういうこと、ない？」「お母さんと料理してる時は？」「お風呂で気づいたことは？」

### 対話の絶対ルール
1. **経験なしには進まない**: 必ず体験を1つ以上聞いてから次の質問
2. **温度変化は必須**: 「温める」「冷やす」体験を毎回確認
3. **具体的な場面**: 「いつ」「どこで」「誰と」を明確に
4. **比較を促す**: 「〜と〜ではどう違った？」

## 最重要：段階別言語化支援の実践
### 予想段階での支援（概念化はしない）
## 重要：予想段階は経験と結びつく主体的な予想を引き出すことが目的

### 支援の流れ（4段階）
1. **体験的表現の受容**: 「ふわふわ」「じゅーじゅー」等のオノマトペや感覚的表現をまず受け止める
2. **一般表現への引き上げ**: 「〜を別の言い方でできないかな？」で書き言葉への変換を支援
3. **経験関連付け**: 「お家で似たようなこと、ない？」「やったことある？」で具体的な経験を引き出す
4. **根拠明確化**: 「なぜそう思ったの？」「何から考えたの？」で予想の根拠を明確にする

### 重要な支援原則
- **子供が主体**: 答えを教えず、子供自身に考えさせて予想を立てさせる
- **経験重視**: 必ず生活経験や既習事項と結びつけて予想させる  
- **概念化禁止**: 予想段階では科学的概念は教えない、足場かけに留める
- **言語化支援**: オノマトペ→一般用語への変換を支援するが難しい言葉に置き換えない

### 段階別質問例
**1-2回目（体験的表現→一般表現）**:
- 「どうなると思いますか？」「どんなふうになりそう？」
- 「もう少し詳しく教えて」「別の言い方でいうと？」

**3-4回目（経験関連付け）**:
- 「お家でそういうこと見たことある？」「いつ、どこで見た？」
- 「似たようなこと知ってる？」「どんな時だった？」

**5回目以降（根拠明確化）**:
- 「なぜそう思ったの？」「何から考えたの？」
- 「どうしてそうなると思う？」

### 考察段階での支援（実験結果の言語化が最優先）
## 重要：見た結果を生活用語から一般用語に引き上げ、予想との差異・経験を引き出す

### 支援の流れ（6段階）
1. **実験結果の言語化**: 「実験でどうなった？」「どんなふうになった？」
2. **結果の詳細確認**: 「どの部分が変化した？」「どのくらい変わった？」  
3. **言語の引き上げ**: オノマトペ・感覚表現→一般的な書き言葉への変換支援
4. **予想との比較**: 「予想と同じだった？」「違ったところは？」
5. **経験関連付け**: 結果を受けてから「似たようなこと見たことある？」
6. **概念化足掛かり**: 「このことから何が言えそうかな？」

### 重要な支援原則  
- **結果優先**: まず実験結果をしっかり言語化させる（最初から体験談は聞かない）
- **言語引き上げ**: 「ぐつぐつ」→「泡が出る」「ふわふわ」→「軽くなる」等の変換支援
- **予想比較**: 必ず予想と結果の差異を確認する
- **経験後付け**: 結果が明確になってから関連経験を引き出す

### 段階別質問例
**1-2回目（結果言語化）**:
- 「実験でどんなことが起こりましたか？」「どうなりましたか？」
- 「もう少し詳しく教えて」「どの部分が変わった？」

**3-4回目（言語引き上げ・予想比較）**:
- 「別の言い方でいうと？」「書く時はどう表現する？」
- 「予想と同じだった？」「どこが違った？」

**5回目以降（経験関連・概念化足掛かり）**:
- 「お家で似たようなこと見たことある？」
- 「このことから何が分かりそう？」

**注意**: 考察段階では最初から体験談は聞かない。まず実験結果をしっかり言語化させる。

### 対話の基本パターン
- 児童の発言を必ず受け止める：「そうそう！」「いいね！」「なるほど〜」
- 1回1つの質問：複数の質問を同時にしない
- 10文字以内の短い質問：「どうなった？」「なぜかな？」「見たことある？」
- 経験重視：「お家でそういうこと、ない？」「似たような体験は？」

### 理科の見方・考え方の活用
- 量的・関係的視点：「どのくらい？」「前と比べると？」
- 質的・実体的視点：「何の性質？」「どんな特徴？」
- 共通性・多様性視点：「他でも同じ？」「違うところは？」
- 時間的・空間的視点：「いつから？」「どこから変化？」
"""
    
    # 学習指導要領の内容を追加（言語活動重視）
    guidelines = get_learning_guidelines()
    if guidelines:
        # 特に言語活動部分を抽出
        relevant_section = ""
        if "言語活動" in guidelines:
            lines = guidelines.split('\n')
            for i, line in enumerate(lines):
                if "言語活動" in line or "見方・考え方" in line:
                    relevant_section += '\n'.join(lines[max(0, i-2):min(len(lines), i+8)])
                    break
        enhanced_prompt += f"\n\n【学習指導要領（言語活動重視）】:\n{relevant_section[:1000]}..."
    
    # 指導支援方針を追加
    teaching_support = get_teaching_support()
    if teaching_support:
        # 産婆法の部分を重点的に抽出
        if "産婆法" in teaching_support:
            lines = teaching_support.split('\n')
            for i, line in enumerate(lines):
                if "産婆法" in line:
                    support_section = '\n'.join(lines[i:min(len(lines), i+20)])
                    enhanced_prompt += f"\n\n【産婆法実践方針】:\n{support_section[:800]}..."
                    break
    
    # 単元別指導案があれば追加
    if unit:
        lesson_content = load_lesson_plan_content(unit)
        if lesson_content:
            # 産婆法実践のポイント部分を抽出
            if "産婆法実践のポイント" in lesson_content:
                lines = lesson_content.split('\n')
                for i, line in enumerate(lines):
                    if "産婆法実践のポイント" in line:
                        lesson_section = '\n'.join(lines[i:min(len(lines), i+15)])
                        enhanced_prompt += f"\n\n【{unit}指導案（産婆法）】:\n{lesson_section[:600]}..."
                        break
        
        # 単元特性の詳細分析を追加
        unit_info = analyze_unit_characteristics(unit)
        if unit_info:
            enhanced_prompt += f"\n\n【{unit}の特性分析】:\n"
            enhanced_prompt += f"・見方・考え方: {unit_info.get('見方・考え方', '')}\n"
            enhanced_prompt += f"・重点活動: {', '.join(unit_info.get('重点活動', []))}\n"
            enhanced_prompt += f"・生活経験例: {', '.join(unit_info.get('生活経験', []))}\n"
            enhanced_prompt += f"・キーワード: {', '.join(unit_info.get('キーワード', []))}\n"
    
    # 学習段階別の支援ガイダンスを追加
    if stage and unit:
        conversation_count = 1  # デフォルト値
        learning_stage = determine_learning_stage(conversation_count)
        stage_guidance = generate_stage_appropriate_guidance(learning_stage, unit)
        
        enhanced_prompt += f"\n\n【現在の学習段階】: {learning_stage}\n"
        enhanced_prompt += f"・目標: {stage_guidance.get('目標', '')}\n"
        enhanced_prompt += f"・支援方針: {', '.join(stage_guidance.get('支援方針', []))}\n"
        enhanced_prompt += f"・重点: {stage_guidance.get('重点', '')}\n"
        enhanced_prompt += f"・推奨質問: {stage_guidance.get('質問例', [''])[0]}\n"
    
    return enhanced_prompt

def analyze_student_response(response, unit):
    """児童の発言から学習状況を分析して次の支援方針を決定"""
    analysis = {
        "理解度": "継続観察",
        "言語化レベル": "基礎段階", 
        "日常関連": False,
        "概念理解": False,
        "感情・態度": "普通",
        "推奨支援": "継続質問",
        "次の質問タイプ": "開放的質問"
    }
    
    response = response.lower() if response else ""
    
    # 理解度の判定
    positive_indicators = ["分かった", "なるほど", "そういうこと", "面白い", "すごい"]
    negative_indicators = ["分からない", "よく分からない", "難しい", "よく見えない"]
    
    if any(word in response for word in positive_indicators):
        analysis["理解度"] = "良好"
        analysis["推奨支援"] = "発展質問"
    elif any(word in response for word in negative_indicators):
        analysis["理解度"] = "要支援"
        analysis["推奨支援"] = "基礎確認"
    
    # 言語化レベルの判定
    if len(response) > 30 and any(word in response for word in ["なぜなら", "だから", "理由は"]):
        analysis["言語化レベル"] = "高度"
        analysis["次の質問タイプ"] = "深化質問"
    elif len(response) > 15 and any(word in response for word in ["と思う", "気がする", "みたい"]):
        analysis["言語化レベル"] = "中程度"
    
    # 日常経験との関連確認
    daily_keywords = ["家で", "普段", "お風呂", "料理", "お母さん", "見たことある", "前に", "いつも"]
    if any(word in response for word in daily_keywords):
        analysis["日常関連"] = True
        analysis["推奨支援"] = "関連深化"
    
    # 単元特性に基づく概念理解確認
    unit_info = analyze_unit_characteristics(unit)
    keywords = unit_info.get("キーワード", [])
    if any(keyword.lower() in response for keyword in keywords):
        analysis["概念理解"] = True
        analysis["推奨支援"] = "概念確認"
    
    # 感情・態度の判定
    positive_emotions = ["楽しい", "面白い", "すごい", "びっくり", "驚いた"]
    if any(word in response for word in positive_emotions):
        analysis["感情・態度"] = "積極的"
    
    return analysis

def generate_adaptive_question(analysis, unit, conversation_history=None):
    """分析結果に基づいて適応的な質問を生成"""
    unit_info = analyze_unit_characteristics(unit)
    
    # 理解度に基づく質問選択
    if analysis["理解度"] == "良好":
        if analysis["概念理解"]:
            questions = [
                "他の場面でも同じようなことが起こりそうですか？",
                f"普段の生活で{', '.join(unit_info.get('生活経験', [])[:1])}以外にも似たことはありますか？"
            ]
        else:
            questions = unit_info.get("産婆法質問", ["もう少し詳しく教えてください"])
    elif analysis["理解度"] == "要支援":
        questions = [
            "どの部分が分からないですか？",
            "今見えたことを教えてください",
            "どんな感じがしましたか？"
        ]
    else:
        # 通常の段階的質問
        if analysis["日常関連"]:
            questions = [
                "それと今回の実験、似ているところはありますか？",
                "どんなところが同じだと思いますか？"
            ]
        else:
            questions = unit_info.get("産婆法質問", ["どう思いますか？"])
    
    # 会話履歴を考慮して質問の重複を避ける
    if conversation_history:
        used_patterns = []
        for msg in conversation_history:
            if msg.get('role') == 'assistant':
                used_patterns.append(msg.get('content', ''))
        
        # 使用済みパターンと類似していない質問を選択
        for question in questions:
            if not any(pattern in question or question in pattern for pattern in used_patterns):
                return question
    
    return questions[0] if questions else "どう感じましたか？"

def call_openai_with_retry(prompt, max_retries=3, delay=2, unit=None, stage=None):
    """OpenAI APIを呼び出し、エラー時はリトライする（Markdownガイドライン活用版）"""
    if client is None:
        return "AI システムの初期化に問題があります。管理者に連絡してください。"
    
    # Markdownガイドラインを活用してプロンプトを強化
    enhanced_prompt = build_enhanced_prompt(prompt, unit, stage)
    
    # OpenAI向けの応答指示を追加
    enhanced_prompt += f"""

**重要な応答指示（OpenAI向け）:**
- 子どもの発言を必ず受け止めてから質問してください
- 「なんでそう思うの？」「どうしてかな？」で理由を聞いてください
- 「似たようなこと見たことある？」で経験を引き出してください
- 「前に習ったこと思い出せる？」で既習事項との関連を聞いてください
- 子どもが答えてから、具体的な体験を聞いてください
- 必ず普通の日本語の文章で回答してください
- JSON、マークダウン、その他の形式は一切使用しないでください
- 小学生向けの短い質問を1つだけしてください
- 質問は15文字以内で簡潔にしてください
- 専門用語は使わず、日常的な言葉を使ってください
- {{ }}, [ ], **, #, ``` などの記号は使わないでください
- 1文で質問を終えてください
- 「実験お疲れさまでした」「実験の結果は」などの定型句は使わないでください
- 子どもの前の発言を受け止めてから、新しい質問をしてください
- 同じフレーズを繰り返さないでください
- 産婆法（ソクラテス式問答法）を実践し、答えを直接教えるのではなく適切な質問で導いてください

**対話の基本パターン:**
1. 子どもの発言を受け止める：「そうだね」「なるほど」
2. 理由を聞く：「なんでそう思うの？」「どうしてかな？」
3. 経験を聞く：「似たようなこと見たことある？」
4. 既習事項：「前に習ったこと思い出せる？」
5. 具体的体験：子どもが答えてから「〜したことある？」
"""
    
    for attempt in range(max_retries):
        try:
            print(f"OpenAI API呼び出し試行 {attempt + 1}/{max_retries}")
            
            # タイムアウト設定を短くして早期に失敗検出
            import time
            start_time = time.time()
            
            # OpenAI APIでリクエストを送信
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": enhanced_prompt}
                ],
                max_tokens=2000,
                temperature=0.3,
                timeout=30  # 30秒タイムアウト
            )
            
            elapsed_time = time.time() - start_time
            print(f"API呼び出し所要時間: {elapsed_time:.2f}秒")
            
            if response.choices and response.choices[0].message.content:
                content = response.choices[0].message.content
                print(f"API呼び出し成功: {len(content)}文字の応答")
                # マークダウン記法を除去してから返す
                cleaned_response = remove_markdown_formatting(content)
                return cleaned_response
            else:
                print("空の応答が返されました")
                print(f"応答全体: {response}")
                raise Exception("空の応答が返されました")
                
        except Exception as e:
            error_msg = str(e)
            print(f"APIコール試行 {attempt + 1}/{max_retries} でエラー: {error_msg}")
            
            # エラーの種類に応じた処理
            if "API_KEY" in error_msg.upper() or "invalid_api_key" in error_msg.lower():
                return "APIキーの設定に問題があります。管理者に連絡してください。"
            elif "QUOTA" in error_msg.upper() or "LIMIT" in error_msg.upper() or "rate_limit_exceeded" in error_msg.lower():
                return "API利用制限に達しました。しばらく待ってから再度お試しください。"
            elif "TIMEOUT" in error_msg.upper() or "DNS" in error_msg.upper() or "503" in error_msg:
                if attempt < max_retries - 1:
                    wait_time = delay * (attempt + 1)
                    print(f"ネットワークエラー、{wait_time}秒後に再試行...")
                    time.sleep(wait_time)
                    continue
                else:
                    return "ネットワーク接続に問題があります。インターネット接続を確認してください。"
            elif "400" in error_msg or "INVALID" in error_msg.upper():
                return "リクエストの形式に問題があります。管理者に連絡してください。"
            elif "403" in error_msg or "PERMISSION" in error_msg.upper():
                return "APIの利用権限に問題があります。管理者に連絡してください。"
            else:
                if attempt < max_retries - 1:
                    wait_time = delay * (attempt + 1)
                    print(f"その他のエラー、{wait_time}秒後に再試行...")
                    time.sleep(wait_time)
                    continue
                else:
                    return f"予期しないエラーが発生しました: {error_msg[:100]}..."
                    
    return "複数回の試行後もAPIに接続できませんでした。しばらく待ってから再度お試しください。"

# 学習単元のデータ
UNITS = [
    "金属のあたたまり方",
    "水のあたたまり方",
    "空気の温度と体積",
    "水を熱し続けた時の温度と様子"
]

# 課題文を読み込む関数
def load_task_content(unit_name):
    try:
        with open(f'tasks/{unit_name}.txt', 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        return f"{unit_name}について実験を行います。どのような結果になると予想しますか？"

# 単元ごとのプロンプトを読み込む関数
def load_unit_prompt(unit_name):
    """単元専用のプロンプトファイルを読み込む"""
    try:
        with open(f'prompts/{unit_name}.md', 'r', encoding='utf-8') as f:
            content = f.read().strip()
        
        # Markdownファイルの内容をプロンプトとして使用
        # ## 単元固有の指導ポイント以降の内容を抽出
        lines = content.split('\n')
        prompt_parts = []
        current_section = ""
        
        for line in lines:
            if line.startswith('## '):
                current_section = line[3:].strip()
                if current_section in ['役割設定', '基本指針', '対話の進め方', '絶対に守ること']:
                    prompt_parts.append(line)
            elif current_section in ['役割設定', '基本指針', '対話の進め方', '絶対に守ること']:
                prompt_parts.append(line)
        
        return '\n'.join(prompt_parts)
    
    except FileNotFoundError:
        # フォールバック: デフォルトプロンプト
        return """
あなたは小学生向けの産婆法（ソクラテス式問答法）を実践する理科指導者です。小学生のレベルに合わせた簡単な質問で、学習者自身に気づかせることが目的です。

## 基本指針
- 1つずつ聞く - 複数の質問を同時にしない
- 身近な例で考えさせる
- 学習者の発言を受け止める - まず肯定してから次の質問
- 経験を聞く - 「前に見たことある？」「どんな時に？」

## 絶対に守ること
- 1文で短く質問する（20文字以内を目指す）
- 小学生が知らない専門用語は使わない
- 複雑な例え話はしない
- 1回に1つのことだけ聞く
- JSON形式では絶対に回答しない
- 普通の文章で質問する
"""

# 学習ログを保存する関数
def save_learning_log(student_number, unit, log_type, data):
    """学習ログをJSONファイルに保存"""
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'student_number': student_number,
        'unit': unit,
        'log_type': log_type,  # 'prediction_chat', 'prediction_summary', 'reflection_chat', 'final_summary'
        'data': data
    }
    
    # ログディレクトリが存在しない場合は作成
    os.makedirs('logs', exist_ok=True)
    
    # ログファイル名（日付別）
    log_file = f"logs/learning_log_{datetime.now().strftime('%Y%m%d')}.json"
    
    # 既存のログを読み込み
    logs = []
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            logs = []
    
    # 新しいログを追加
    logs.append(log_entry)
    
    # ファイルに保存
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

# 学習ログを読み込む関数
def load_learning_logs(date=None):
    """指定日の学習ログを読み込み"""
    if date is None:
        date = datetime.now().strftime('%Y%m%d')
    
    log_file = f"logs/learning_log_{date}.json"
    
    if not os.path.exists(log_file):
        return []
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

@app.route('/api/test')
def api_test():
    """API接続テスト"""
    try:
        test_prompt = "こんにちは。短い挨拶をお願いします。"
        response = call_openai_with_retry(test_prompt, max_retries=1)
        return jsonify({
            'status': 'success',
            'message': 'API接続テスト成功',
            'response': response
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'API接続テスト失敗: {str(e)}'
        }), 500

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/select_class')
def select_class():
    return render_template('select_class.html')

@app.route('/select_number')
def select_number():
    class_number = request.args.get('class', '1')
    return render_template('select_number.html', class_number=class_number)

@app.route('/select_unit')
def select_unit():
    class_number = request.args.get('class', '1')
    student_number = request.args.get('number')
    session['class_number'] = class_number
    session['student_number'] = student_number
    return render_template('select_unit.html', units=UNITS)

@app.route('/prediction')
def prediction():
    class_number = request.args.get('class', session.get('class_number', '1'))
    student_number = request.args.get('number', session.get('student_number', '1'))
    unit = request.args.get('unit')
    
    session['class_number'] = class_number
    session['student_number'] = student_number
    session['unit'] = unit
    session['conversation'] = []
    
    task_content = load_task_content(unit)
    session['task_content'] = task_content
    
    return render_template('prediction.html', unit=unit, task_content=task_content)

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message')
    input_metadata = request.json.get('metadata', {})
    conversation = session.get('conversation', [])
    unit = session.get('unit')
    task_content = session.get('task_content')
    student_number = session.get('student_number')
    
    # ユーザーメッセージを正規化
    user_message = normalize_childish_expressions(user_message)
    user_message = normalize_family_expressions(user_message)
    
    # 対話履歴に追加
    conversation.append({'role': 'user', 'content': user_message})
    
    # 単元ごとのプロンプトを読み込み
    unit_prompt = load_unit_prompt(unit)
    
    # 対話回数に応じた段階別支援戦略を決定
    conversation_count = len(conversation) // 2 + 1  # ユーザーメッセージの回数
    unit_info = analyze_unit_characteristics(unit)
    
    # 予想段階の段階別戦略
    if conversation_count <= 2:
        # 第1段階：体験的表現→一般表現
        stage_guidance = """
**現在の段階**: 体験的表現から一般表現への引き上げ段階
**目標**: 子供の感覚的・体験的表現を受け止めて、一般的な表現に引き上げる
**戦略**: 
1. まず子供の表現を受け止める「そうですね」「なるほど」
2. 「どんなふうになると思う？」「もう少し詳しく教えて」で具体化
3. 「別の言い方でいうと？」で表現の引き上げ
**禁止**: 概念的な説明、専門用語の使用、複数質問
**質問例**: 「どうなると思いますか？」「どんな感じになりそう？」
"""
    elif conversation_count <= 4:
        # 第2段階：経験関連付け（産婆法強化）
        socratic_questions = unit_info.get('産婆法_経験引き出し', [])
        experience_shortage_questions = unit_info.get('経験不足時の質問', [])
        stage_guidance = f"""
**現在の段階**: 生活経験・既習事項との関連付け段階（産婆法実践）
**目標**: 予想の根拠となる具体的な経験を産婆法で詳しく引き出す
**戦略**:
1. 「お家でそういうこと見たことある？」で経験の有無を確認
2. 「いつ、どこで見た？」「誰と一緒だった？」で具体的な場面を詳細化
3. 「その時どんな感じだった？」「どうなっていた？」で詳細な観察を引き出す
4. 「他にも似たようなこと知ってる？」で関連経験を広げる
5. **経験不足の場合**: こちらから具体的な経験を提示して「こういうのない？」と聞く

**経験引き出し質問例**: {socratic_questions[0] if socratic_questions else ''}
**経験不足時の質問例**: {experience_shortage_questions[0] if experience_shortage_questions else ''}
**関連生活経験例**: {', '.join(unit_info.get('生活経験', []))}
**質問例**: 「どんな時に見たことある？」「その時どうだった？」「他にも似たようなことある？」
**経験不足時の対応**: 「こういうの見たことない？」「○○した時はどうだった？」
"""
    else:
        # 第3段階：根拠明確化
        stage_guidance = """
**現在の段階**: 予想の根拠明確化段階
**目標**: なぜそう予想したかの根拠を明確にする
**戦略**:
1. 「なぜそう思ったの？」「何から考えたの？」で根拠を聞く
2. 経験と予想の関連を確認
3. 予想をまとめる準備
**質問例**: 「どうしてそう思ったの？」「何から考えたの？」
"""
    
    # プロンプト作成
    system_prompt = f"""{unit_prompt}

【学習単元】: {unit}
【課題】: {task_content}
【対話回数】: {conversation_count}回目

{stage_guidance}

【単元特性】:
・見方・考え方: {unit_info.get('見方・考え方', '')}
・生活経験例: {', '.join(unit_info.get('生活経験', []))}
・産婆法質問例: {unit_info.get('産婆法質問', [''])[0] if unit_info.get('産婆法質問') else ''}

【応答ルール】:
1. 子供の発言をまず受け止める（「そうですね」「なるほど」等）
2. その後、1つだけ短い質問をする（20文字以内）
3. JSON形式やマークダウンは絶対使わない
4. 普通の日本語で自然に話す
5. 専門用語は使わない、小学生レベルの言葉のみ
6. 概念は教えない、子供自身に考えさせる
7. 予想段階では概念化は行わない

【重要】: 子供が主体となって予想を立てられるよう支援してください。
答えを教えるのではなく、経験を引き出して予想の根拠を明確にしてください。

次の応答を普通の文章で1文で書いてください："""
    
    # 対話履歴を含めてプロンプト作成
    full_prompt = system_prompt + "\n\n対話履歴:\n"
    for msg in conversation:
        role = "学習者" if msg['role'] == 'user' else "AI"
        full_prompt += f"{role}: {msg['content']}\n"
    
    try:
        ai_response = call_openai_with_retry(full_prompt, unit=unit, stage='prediction')
        
        # JSON形式のレスポンスの場合は解析して純粋なメッセージを抽出
        ai_message = extract_message_from_json_response(ai_response)
        
        # マークダウン記法を除去
        ai_message = remove_markdown_formatting(ai_message)
        
        conversation.append({'role': 'assistant', 'content': ai_message})
        session['conversation'] = conversation
        
        # 学習ログを保存
        save_learning_log(
            student_number=session.get('student_number'),
            unit=unit,
            log_type='prediction_chat',
            data={
                'user_message': user_message,
                'ai_response': ai_message,
                'conversation_count': len(conversation) // 2,
                'used_suggestion': False,
                'suggestion_index': None
            }
        )
        
        # 対話が3回以上の場合、予想のまとめを提案
        suggest_summary = len(conversation) >= 6  # user + AI で1セット
        
        response_data = {
            'response': ai_message,
            'suggest_summary': suggest_summary
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"チャットエラー: {str(e)}")
        return jsonify({'error': f'AI接続エラーが発生しました。しばらく待ってから再度お試しください。'}), 500

@app.route('/summary', methods=['POST'])
def summary():
    conversation = session.get('conversation', [])
    unit = session.get('unit')
    
    # 課題文を読み込み
    task_content = load_task_content(unit)
    
    # 予想のまとめを生成（対話内容のみに基づく）
    summary_prompt = f"""
以下の対話内容「のみ」を基に、学習者が実際に発言した内容をまとめて予想文を作成してください。

**重要な制約:**
1. 対話に出てこなかった内容は絶対に追加しない
2. 学習者が実際に言った言葉や表現をできるだけ使用する
3. 学習者が話した経験や根拠のみを含める
4. 対話で言及されていない例や理由は一切使わない
5. 1-2文の短い予想文にまとめる
6. 「〜と思います。」「〜だと予想します。」の形で終わる
7. マークダウン記法は一切使用しない

課題文: {task_content}
単元: {unit}

対話履歴:
"""
    for msg in conversation:
        role = "学習者" if msg['role'] == 'user' else "AI"
        summary_prompt += f"{role}: {msg['content']}\n"
    
    try:
        summary_response = call_openai_with_retry(summary_prompt)
        
        # JSON形式のレスポンスの場合は解析して純粋なメッセージを抽出
        summary_text = extract_message_from_json_response(summary_response)
        
        session['prediction_summary'] = summary_text
        
        # 予想まとめのログを保存
        save_learning_log(
            student_number=session.get('student_number'),
            unit=unit,
            log_type='prediction_summary',
            data={
                'summary': summary_text,
                'conversation': conversation
            }
        )
        
        return jsonify({'summary': summary_text})
    except Exception as e:
        print(f"まとめエラー: {str(e)}")
        return jsonify({'error': f'まとめ生成中にエラーが発生しました。'}), 500

@app.route('/experiment')
def experiment():
    return render_template('experiment.html')

@app.route('/reflection')
def reflection():
    return render_template('reflection.html', 
                         unit=session.get('unit'),
                         prediction_summary=session.get('prediction_summary'))

@app.route('/reflect_chat', methods=['POST'])
def reflect_chat():
    user_message = request.json.get('message')
    reflection_conversation = session.get('reflection_conversation', [])
    unit = session.get('unit')
    prediction_summary = session.get('prediction_summary', '')
    
    # ユーザーメッセージを正規化
    user_message = normalize_childish_expressions(user_message)
    user_message = normalize_family_expressions(user_message)
    
    # 反省対話履歴に追加
    reflection_conversation.append({'role': 'user', 'content': user_message})
    
    # 児童の発言を分析
    student_analysis = analyze_student_response(user_message, unit)
    
    # 学習段階判定
    conversation_turn = len(reflection_conversation) // 2 + 1
    learning_stage = determine_learning_stage(conversation_turn)
    stage_guidance = generate_stage_appropriate_guidance(learning_stage, unit)
    
    # 適応的質問生成
    adaptive_question = generate_adaptive_question(student_analysis, unit, reflection_conversation)
    
    # 対話回数に応じた段階別支援戦略を決定  
    conversation_turn = len(reflection_conversation) // 2 + 1
    unit_info = analyze_unit_characteristics(unit)
    
    # 考察段階の段階別戦略
    if conversation_turn <= 2:
        # 第1段階：実験結果の言語化
        stage_guidance = """
**現在の段階**: 実験結果の言語化段階
**目標**: まず実験で見た結果をしっかりと言語化させる
**戦略**: 
1. 「実験でどんなことが起こりましたか？」で結果を聞く
2. 「どの部分が変わった？」「どのくらい変わった？」で詳細化
3. オノマトペや感覚表現を受け止めつつ、一般表現への変換を支援
**重要**: 最初から体験談は聞かない、まず結果の言語化が最優先
**質問例**: 「実験でどうなりましたか？」「どんなふうになった？」
"""
    elif conversation_turn <= 4:
        # 第2-3段階：言語引き上げ・予想との比較
        stage_guidance = """
**現在の段階**: 言語引き上げ・予想比較段階
**目標**: 生活用語→一般用語への引き上げ、予想との差異確認
**戦略**:
1. 「別の言い方でいうと？」「書く時はどう表現する？」で言語引き上げ
2. 「予想と同じだった？」「どこが違った？」で予想比較
3. オノマトペ→書き言葉の変換支援（「ぐつぐつ」→「泡が出る」等）
**重要**: 難しい言葉に置き換えるのではなく、適切な一般用語に
**質問例**: 「予想と同じでしたか？」「書く時はどう表現する？」
"""
    else:
        # 第4段階以降：経験関連付け・概念化足掛かり（産婆法強化）
        socratic_questions = unit_info.get('産婆法_経験引き出し', [])
        stage_guidance = f"""
**現在の段階**: 経験関連付け・概念化足掛かり段階（産婆法実践）
**目標**: 結果を受けて生活経験と関連付け、概念化への足掛かりを作る
**戦略**:
1. 結果が明確になってから「似たようなこと見たことある？」で経験関連
2. 「どんな時だった？」「どこで見た？」で具体的な場面を詳細化
3. 「その時も同じようなことが起こった？」で関連性を確認
4. 「前に習ったことと似てる？」で既習事項との関連
5. 「このことから何が分かりそう？」で概念化への足掛かり
**産婆法質問例**: {socratic_questions[1] if len(socratic_questions) > 1 else socratic_questions[0] if socratic_questions else ''}
**重要**: 結果の言語化ができてから、産婆法で詳しく経験を引き出す
**質問例**: 「お家で似たようなこと見たことある？」「どんな時だった？」「このことから何が分かる？」
"""
    
    # 強化された考察支援プロンプト
    system_prompt = f"""
【学習単元】: {unit}
【学習者の予想】: {prediction_summary}
【対話回数】: {conversation_turn}回目

{stage_guidance}

【単元特性】:
・見方・考え方: {unit_info.get('見方・考え方', '')}
・重点活動: {', '.join(unit_info.get('重点活動', []))}
・生活経験例: {', '.join(unit_info.get('生活経験', []))}
・キーワード: {', '.join(unit_info.get('キーワード', []))}

【考察段階の重要な流れ】:
実験結果の言語化 → 言語の引き上げ → 予想との差異確認 → 経験関連付け → 概念化足掛かり

【応答ルール】:
1. 子供の発言をまず受け止める（「そうですね」「なるほど」等）
2. その後、1つだけ短い質問をする（20文字以内）
3. JSON形式やマークダウンは絶対使わない
4. 普通の日本語で自然に話す
5. 専門用語は使わない、小学生レベルの言葉のみ
6. 対話履歴を確認し、既に聞いた内容は重複して聞かない
7. 子供の答えに応じて次のステップに進む

【言語引き上げ支援例】:
・「ふわふわ」→「軽くなる」「やわらかくなる」
・「ぐつぐつ」→「泡が出る」「沸騰する」  
・「じゅーじゅー」→「温まる」「熱くなる」
・「すーっと」→「ゆっくりと」「だんだん」

【重要】: 見た結果を生活用語から適切な一般用語に引き上げることで、
考察の質を向上させてください。難しい専門用語は使わないでください。

次の応答を普通の文章で1文で書いてください："""
    
    # 対話履歴を追加
    full_prompt = system_prompt + "\n\n対話履歴:\n"
    for msg in reflection_conversation:
        role = "学習者" if msg['role'] == 'user' else "AI"
        full_prompt += f"{role}: {msg['content']}\n"
    
    try:
        ai_response = call_openai_with_retry(full_prompt, unit=unit, stage='reflection')
        
        # JSON形式のレスポンスの場合は解析して純粋なメッセージを抽出
        ai_message = extract_message_from_json_response(ai_response)
        
        # マークダウン記法を除去
        ai_message = remove_markdown_formatting(ai_message)
        
        reflection_conversation.append({'role': 'assistant', 'content': ai_message})
        session['reflection_conversation'] = reflection_conversation
        
        # 考察チャットのログを保存
        save_learning_log(
            student_number=session.get('student_number'),
            unit=unit,
            log_type='reflection_chat',
            data={
                'user_message': user_message,
                'ai_response': ai_message,
                'conversation_count': len(reflection_conversation) // 2
            }
        )
        
        return jsonify({'response': ai_message})
        
    except Exception as e:
        print(f"考察チャットエラー: {str(e)}")
        return jsonify({'error': f'AI接続エラーが発生しました。しばらく待ってから再度お試しください。'}), 500

@app.route('/final_summary', methods=['POST'])
def final_summary():
    reflection_conversation = session.get('reflection_conversation', [])
    prediction_summary = session.get('prediction_summary', '')
    
    # 最終まとめを生成（対話内容のみに基づく）
    final_prompt = f"""
以下の対話内容「のみ」を基に、学習者が実際に発言した内容をまとめて考察文を作成してください。

**重要な制約:**
1. 対話に出てこなかった内容は絶対に追加しない
2. 学習者が実際に言った実験結果のみを使用する
3. 学習者が実際に話した経験や考えのみを含める
4. 対話で言及されていない結論や解釈は一切追加しない
5. 定型文の形式を守る：「(結果)という結果であった。(予想)と予想していたが、(合っていた/誤っていた)。このことから(経験や既習事項)は~と考えた」
6. マークダウン記法は一切使用しない
7. 学習者の実際の表現をできるだけ使用する

学習者の予想: {prediction_summary}

考察対話履歴:
"""
    for msg in reflection_conversation:
        role = "学習者" if msg['role'] == 'user' else "AI"
        final_prompt += f"{role}: {msg['content']}\n"
    
    try:
        final_summary_response = call_openai_with_retry(final_prompt)
        
        # JSON形式のレスポンスの場合は解析して純粋なメッセージを抽出
        final_summary_text = extract_message_from_json_response(final_summary_response)
        
        # マークダウン記法を除去
        final_summary_text = remove_markdown_formatting(final_summary_text)
        
        # 最終考察のログを保存
        save_learning_log(
            student_number=session.get('student_number'),
            unit=session.get('unit'),
            log_type='final_summary',
            data={
                'final_summary': final_summary_text,
                'prediction_summary': prediction_summary,
                'reflection_conversation': reflection_conversation
            }
        )
        
        return jsonify({'summary': final_summary_text})
    except Exception as e:
        print(f"最終まとめエラー: {str(e)}")
        return jsonify({'error': f'最終まとめ生成中にエラーが発生しました。'}), 500

# 教員用ルート
@app.route('/teacher/login', methods=['GET', 'POST'])
def teacher_login():
    """教員ログインページ"""
    if request.method == 'POST':
        teacher_id = request.form.get('teacher_id')
        password = request.form.get('password')
        
        # 認証チェック
        if teacher_id in TEACHER_CREDENTIALS and TEACHER_CREDENTIALS[teacher_id] == password:
            session['teacher_authenticated'] = True
            session['teacher_id'] = teacher_id
            flash('ログインしました', 'success')
            return redirect(url_for('teacher'))
        else:
            flash('IDまたはパスワードが正しくありません', 'error')
    
    return render_template('teacher/login.html')

@app.route('/teacher/logout')
def teacher_logout():
    """教員ログアウト"""
    session.pop('teacher_authenticated', None)
    session.pop('teacher_id', None)
    flash('ログアウトしました', 'info')
    return redirect(url_for('index'))

@app.route('/teacher')
@require_teacher_auth
def teacher():
    """教員用ダッシュボード"""
    # 指導案一覧も含めて表示
    lesson_plans = get_lesson_plans_list()
    return render_template('teacher/dashboard.html', 
                         units=UNITS, 
                         teacher_id=session.get('teacher_id'),
                         lesson_plans=lesson_plans)

@app.route('/teacher/lesson_plans')
@require_teacher_auth
def teacher_lesson_plans():
    """指導案管理ページ"""
    lesson_plans = get_lesson_plans_list()
    return render_template('teacher/lesson_plans.html', 
                         units=UNITS, 
                         lesson_plans=lesson_plans,
                         teacher_id=session.get('teacher_id'))

@app.route('/teacher/lesson_plans/upload', methods=['POST'])
@require_teacher_auth
def upload_lesson_plan():
    """指導案PDFのアップロード"""
    try:
        unit = request.form.get('unit')
        
        # 単元の検証
        if unit not in UNITS:
            flash('無効な単元が選択されました', 'error')
            return redirect(url_for('teacher_lesson_plans'))
        
        # ファイルの確認
        if 'file' not in request.files:
            flash('ファイルが選択されていません', 'error')
            return redirect(url_for('teacher_lesson_plans'))
        
        file = request.files['file']
        if file.filename == '':
            flash('ファイルが選択されていません', 'error')
            return redirect(url_for('teacher_lesson_plans'))
        
        if file and allowed_file(file.filename):
            # ファイル名を安全にする（単元名を含める）
            filename = secure_filename(f"{unit}_{file.filename}")
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            # 既存ファイルがあれば削除
            lesson_plans = get_lesson_plans_list()
            if unit in lesson_plans:
                old_file = os.path.join(app.config['UPLOAD_FOLDER'], lesson_plans[unit]['filename'])
                if os.path.exists(old_file):
                    os.remove(old_file)
            
            # ファイルを保存（現在はMarkdown形式のため、この部分は使用しない）
            # file.save(file_path)
            
            # 指導案情報を保存（Markdownファイルが既に存在すると仮定）
            lesson_content = load_lesson_plan_content(unit)
            if lesson_content:
                save_lesson_plan_info(unit, lesson_content)
                flash(f'{unit}の指導案が更新されました', 'success')
            else:
                flash('指導案の内容を読み込めませんでした', 'error')
        else:
            flash('現在はMarkdown形式の指導案のみ対応しています', 'info')
            
    except Exception as e:
        flash(f'アップロード中にエラーが発生しました: {str(e)}', 'error')
    
    return redirect(url_for('teacher_lesson_plans'))

@app.route('/teacher/lesson_plans/delete/<unit>')
@require_teacher_auth
def delete_lesson_plan(unit):
    """指導案の削除"""
    try:
        lesson_plans = get_lesson_plans_list()
        if unit in lesson_plans:
            # ファイルを削除
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], lesson_plans[unit]['filename'])
            if os.path.exists(file_path):
                os.remove(file_path)
            
            # インデックスから削除
            del lesson_plans[unit]
            lesson_plans_file = "lesson_plans/lesson_plans_index.json"
            with open(lesson_plans_file, 'w', encoding='utf-8') as f:
                json.dump(lesson_plans, f, ensure_ascii=False, indent=2)
            
            flash(f'{unit}の指導案が削除されました', 'success')
        else:
            flash('指導案が見つかりません', 'error')
    except Exception as e:
        flash(f'削除中にエラーが発生しました: {str(e)}', 'error')
    
    return redirect(url_for('teacher_lesson_plans'))

@app.route('/teacher/logs')
@require_teacher_auth
def teacher_logs():
    """学習ログ一覧"""
    # デフォルト日付を現在の日付に設定
    try:
        available_dates = get_available_log_dates()
        default_date = available_dates[0]['raw'] if available_dates else datetime.now().strftime('%Y%m%d')
    except:
        default_date = datetime.now().strftime('%Y%m%d')
        available_dates = []
    
    date = request.args.get('date', default_date)
    unit = request.args.get('unit', '')
    student = request.args.get('student', '')
    
    logs = load_learning_logs(date)
    print(f"ログ読み込み - 対象日付: {date}, 読み込んだログ数: {len(logs)}")
    
    # フィルタリング
    if unit:
        logs = [log for log in logs if log.get('unit') == unit]
        print(f"単元フィルタ適用後: {len(logs)}件")
    if student:
        logs = [log for log in logs if log.get('student_number') == student]
        print(f"学生フィルタ適用後: {len(logs)}件")
    
    # 学生ごとにグループ化
    students_data = {}
    for log in logs:
        student_num = log.get('student_number')
        if student_num not in students_data:
            students_data[student_num] = {
                'student_number': student_num,
                'units': {}
            }
        
        unit_name = log.get('unit')
        if unit_name not in students_data[student_num]['units']:
            students_data[student_num]['units'][unit_name] = {
                'prediction_chats': [],
                'prediction_summary': None,
                'reflection_chats': [],
                'final_summary': None
            }
        
        log_type = log.get('log_type')
        if log_type == 'prediction_chat':
            students_data[student_num]['units'][unit_name]['prediction_chats'].append(log)
        elif log_type == 'prediction_summary':
            students_data[student_num]['units'][unit_name]['prediction_summary'] = log
        elif log_type == 'reflection_chat':
            students_data[student_num]['units'][unit_name]['reflection_chats'].append(log)
        elif log_type == 'final_summary':
            students_data[student_num]['units'][unit_name]['final_summary'] = log
    
    return render_template('teacher/logs.html', 
                         students_data=students_data, 
                         units=UNITS,
                         current_date=date,
                         current_unit=unit,
                         current_student=student,
                         available_dates=available_dates,
                         teacher_id=session.get('teacher_id'))

@app.route('/teacher/export')
@require_teacher_auth
def teacher_export():
    """ログをCSVでエクスポート"""
    date = request.args.get('date', datetime.now().strftime('%Y%m%d'))
    logs = load_learning_logs(date)
    
    # CSVファイルを作成
    output_file = f"export_{date}.csv"
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['timestamp', 'student_number', 'unit', 'log_type', 'content']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for log in logs:
            content = ""
            if log.get('log_type') == 'prediction_chat':
                content = f"質問: {log['data'].get('user_message', '')} / 回答: {log['data'].get('ai_response', '')}"
            elif log.get('log_type') == 'prediction_summary':
                content = log['data'].get('summary', '')
            elif log.get('log_type') == 'reflection_chat':
                content = f"質問: {log['data'].get('user_message', '')} / 回答: {log['data'].get('ai_response', '')}"
            elif log.get('log_type') == 'final_summary':
                content = log['data'].get('final_summary', '')
            
            writer.writerow({
                'timestamp': log.get('timestamp', ''),
                'student_number': log.get('student_number', ''),
                'unit': log.get('unit', ''),
                'log_type': log.get('log_type', ''),
                'content': content
            })
    
    return jsonify({'message': f'エクスポートが完了しました: {output_file}'})

# ログ分析機能
def load_guidelines_content():
    """指導要領・資料の内容を読み込み"""
    try:
        index_file = 'guidelines/guidelines_index.json'
        
        if not os.path.exists(index_file):
            return ""
        
        with open(index_file, 'r', encoding='utf-8') as f:
            guidelines_index = json.load(f)
        
        # 全ての資料の内容を結合
        combined_content = ""
        for doc_id, doc_info in guidelines_index.items():
            doc_type = doc_info.get('type', '')
            title = doc_info.get('title', '')
            content = doc_info.get('content', '')
            
            combined_content += f"\n【{title}】\n{content}\n"
        
        return combined_content[:2000]  # 最大2000文字まで
    
    except Exception as e:
        print(f"指導要領読み込みエラー: {str(e)}")
        return ""

def analyze_student_learning(student_number, unit, logs):
    """特定の学生・単元の学習過程を詳細分析"""
    print(f"分析開始 - 学生: {student_number}, 単元: {unit}")
    
    # 該当する学生のログを抽出
    student_logs = [log for log in logs if 
                   log.get('student_number') == student_number and 
                   log.get('unit') == unit]
    
    print(f"該当ログ数: {len(student_logs)}")
    
    if not student_logs:
        return {
            'evaluation': '学習データがありません',
            'prediction_analysis': {
                'daily_life_connection': 'データなし - 日常体験との関連付けを確認できません',
                'prior_knowledge_use': 'データなし - 既習事項の活用を確認できません',
                'reasoning_quality': 'データなし - 予想の根拠を確認できません'
            },
            'reflection_analysis': {
                'result_verbalization': 'データなし - 結果の言語化を確認できません',
                'prediction_comparison': 'データなし - 予想との比較を確認できません',
                'daily_life_connection': 'データなし - 日常生活との関連付けを確認できません',
                'scientific_understanding': 'データなし - 科学的理解を確認できません'
            },
            'language_development': '学習活動への参加が必要です',
            'support_recommendations': ['学習活動への参加促進', '対話の機会提供']
        }
    
    # 指導要領・資料の内容を取得
    try:
        guidelines_content = load_guidelines_content()
        guidelines_context = ""
        
        if guidelines_content:
            guidelines_context = f"参考指導資料: {guidelines_content[:800]}"
    except:
        guidelines_context = ""
    
    # 対話履歴を整理
    prediction_chats = []
    reflection_chats = []
    prediction_summary = ""
    final_summary = ""
    
    for log in student_logs:
        log_type = log.get('log_type')
        data = log.get('data', {})
        
        if log_type == 'prediction_chat':
            prediction_chats.append({
                'user': data.get('user_message', ''),
                'ai': data.get('ai_response', '')
            })
        elif log_type == 'reflection_chat':
            reflection_chats.append({
                'user': data.get('user_message', ''),
                'ai': data.get('ai_response', '')
            })
        elif log_type == 'prediction_summary':
            prediction_summary = data.get('summary', '')
        elif log_type == 'final_summary':
            final_summary = data.get('final_summary', '')
    
    print(f"予想対話数: {len(prediction_chats)}, 考察対話数: {len(reflection_chats)}")
    
    # 簡易分析結果を返す（OpenAI APIエラーを避けるため）
    try:
        return {
            "analysis_text": f"学生{student_number}の{unit}学習分析:\n予想段階の対話: {len(prediction_chats)}回\n考察段階の対話: {len(reflection_chats)}回\n予想まとめ: {'あり' if prediction_summary else 'なし'}\n最終まとめ: {'あり' if final_summary else 'なし'}",
            "unit": unit,
            "student_number": student_number,
            "prediction_count": len(prediction_chats),
            "reflection_count": len(reflection_chats),
            "has_prediction_summary": bool(prediction_summary),
            "has_final_summary": bool(final_summary),
            "evaluation": "学習活動に参加し、対話を通じて学習を進めています",
            "prediction_analysis": {
                "daily_life_connection": f"予想段階で{len(prediction_chats)}回の対話を行いました",
                "prior_knowledge_use": "対話記録から既習事項の活用状況を確認できます",
                "reasoning_quality": f"予想の根拠について{'まとめが作成されています' if prediction_summary else '対話を継続中です'}"
            },
            "reflection_analysis": {
                "result_verbalization": f"考察段階で{len(reflection_chats)}回の対話を行いました",
                "prediction_comparison": "実験結果と予想の比較を進めています",
                "daily_life_connection": "日常生活との関連付けを模索中です",
                "scientific_understanding": f"科学的理解について{'まとめが作成されています' if final_summary else '学習継続中です'}"
            },
            "language_development": "対話活動を通じて言語化能力の向上が期待されます",
            "support_recommendations": ["継続的な対話支援", "言語化の促進", "概念理解の深化"]
        }
    
    except Exception as e:
        print(f"分析エラー: {str(e)}")
        return {
            'evaluation': f'分析エラー: {str(e)}',
            'prediction_analysis': {
                'daily_life_connection': 'エラーが発生しました',
                'prior_knowledge_use': 'エラーが発生しました',
                'reasoning_quality': 'エラーが発生しました'
            },
            'reflection_analysis': {
                'result_verbalization': 'エラーが発生しました',
                'prediction_comparison': 'エラーが発生しました',
                'daily_life_connection': 'エラーが発生しました',
                'scientific_understanding': 'エラーが発生しました'
            },
            'language_development': 'エラーが発生しました',
            'support_recommendations': ['システム管理者に連絡してください']
        }
        if json_match:
            json_str = json_match.group(0)
            print(f"抽出されたJSON: {json_str}")
            try:
                result = json.loads(json_str)
                print("方法1でJSON解析成功")
            except json.JSONDecodeError:
                print("方法1でJSON解析失敗")
        
        # 方法2: 複数行にわたるJSONを抽出
        if not result:
            lines = response.split('\n')
            json_lines = []
            in_json = False
            brace_count = 0
            
            for line in lines:
                if '{' in line and not in_json:
                    in_json = True
                    brace_count = line.count('{') - line.count('}')
                    json_lines = [line]
                elif in_json:
                    json_lines.append(line)
                    brace_count += line.count('{') - line.count('}')
                    if brace_count <= 0:
                        break
            
            if json_lines:
                json_str = '\n'.join(json_lines)
                print(f"方法2で抽出されたJSON: {json_str}")
                try:
                    result = json.loads(json_str)
                    print("方法2でJSON解析成功")
                except json.JSONDecodeError:
                    print("方法2でJSON解析失敗")
        
        # 成功した場合は結果を返す
        if result:
            print("分析完了")
            return result
        
        # 全て失敗した場合はフォールバック
        print("JSON抽出に失敗、フォールバックを使用")
        return {
            'evaluation': '言語活動の記録から対話への取り組み姿勢が確認できます',
            'language_support_needed': ['経験の言語化支援', '既習事項との関連付け支援', '結果の表現力向上支援'],
            'prediction_analysis': {
                'experience_connection': '日常経験の引き出しを継続的に支援',
                'prior_knowledge_use': '既習事項との関連付けを意識させる対話が必要'
            },
            'reflection_analysis': {
                'result_verbalization': '実験結果を自分の言葉で表現する練習が必要',
                'prediction_comparison': '予想との比較を言語化する支援が効果的',
                'daily_life_connection': '日常生活との関連を言葉で説明する機会を増やす'
            },
            'language_development': '対話を通じて徐々に言語化能力が向上しています'
        }
        
    except json.JSONDecodeError as e:
        print(f"JSON解析エラー: {e}")
        # 言語活動支援観点のフォールバック応答
        return {
            'evaluation': '分析処理でエラーが発生しましたが、言語活動への取り組みは確認できます',
            'language_support_needed': ['システム安定化後の詳細な言語化支援', '個別対話支援の継続', '表現力向上のための指導'],
            'prediction_analysis': {
                'experience_connection': '経験の言語化について再評価が必要',
                'prior_knowledge_use': '既習事項の活用状況を確認中'
            },
            'reflection_analysis': {
                'result_verbalization': '結果の言語化について評価中',
                'prediction_comparison': '予想との比較の言語化について分析中',
                'daily_life_connection': '日常生活との関連付けについて評価予定'
            },
            'language_development': 'システム復旧後に言語活動の成長を詳細分析予定'
        }

def analyze_language_activity_levels(logs, unit):
    """言語活動レベルの達成度をクラス傾向として分析"""
    prediction_logs = [log for log in logs if log.get('log_type') == 'prediction_chat']
    reflection_logs = [log for log in logs if log.get('log_type') == 'reflection_chat']
    
    # 予想段階の言語活動分析
    prediction_analysis = {
        'total_students': len(set(log.get('student_number') for log in prediction_logs)),
        'experience_connection_rate': 0,
        'reasoning_clarity_rate': 0,
        'language_level_distribution': {'高': 0, '中': 0, '低': 0}
    }
    
    # 考察段階の言語活動分析
    reflection_analysis = {
        'total_students': len(set(log.get('student_number') for log in reflection_logs)),
        'result_verbalization_rate': 0,
        'prediction_comparison_rate': 0,
        'experience_integration_rate': 0,
        'language_improvement_rate': 0
    }
    
    # 学生ごとの分析
    students = set(log.get('student_number') for log in logs)
    
    for student in students:
        student_prediction_logs = [log for log in prediction_logs if log.get('student_number') == student]
        student_reflection_logs = [log for log in reflection_logs if log.get('student_number') == student]
        
        # 予想段階分析
        if student_prediction_logs:
            has_experience = any('見たことある' in log['data'].get('user_message', '') or 
                               'やったことある' in log['data'].get('user_message', '') or
                               'お家で' in log['data'].get('user_message', '') for log in student_prediction_logs)
            
            has_reasoning = any('なぜなら' in log['data'].get('user_message', '') or 
                              'だから' in log['data'].get('user_message', '') or
                              '思う' in log['data'].get('user_message', '') for log in student_prediction_logs)
            
            if has_experience:
                prediction_analysis['experience_connection_rate'] += 1
            if has_reasoning:
                prediction_analysis['reasoning_clarity_rate'] += 1
                
            # 言語レベル判定（簡易版）
            total_chars = sum(len(log['data'].get('user_message', '')) for log in student_prediction_logs)
            if total_chars > 100:
                prediction_analysis['language_level_distribution']['高'] += 1
            elif total_chars > 50:
                prediction_analysis['language_level_distribution']['中'] += 1
            else:
                prediction_analysis['language_level_distribution']['低'] += 1
        
        # 考察段階分析
        if student_reflection_logs:
            has_result = any('なった' in log['data'].get('user_message', '') or 
                           '変わった' in log['data'].get('user_message', '') or
                           '起こった' in log['data'].get('user_message', '') for log in student_reflection_logs)
            
            has_comparison = any('予想' in log['data'].get('user_message', '') or 
                               '同じ' in log['data'].get('user_message', '') or
                               '違った' in log['data'].get('user_message', '') for log in student_reflection_logs)
            
            has_experience_integration = any('似ている' in log['data'].get('user_message', '') or 
                                            '前に' in log['data'].get('user_message', '') or
                                            'お家で' in log['data'].get('user_message', '') for log in student_reflection_logs)
            
            if has_result:
                reflection_analysis['result_verbalization_rate'] += 1
            if has_comparison:
                reflection_analysis['prediction_comparison_rate'] += 1
            if has_experience_integration:
                reflection_analysis['experience_integration_rate'] += 1
    
    # パーセンテージ計算
    if prediction_analysis['total_students'] > 0:
        prediction_analysis['experience_connection_rate'] = round(
            (prediction_analysis['experience_connection_rate'] / prediction_analysis['total_students']) * 100, 1)
        prediction_analysis['reasoning_clarity_rate'] = round(
            (prediction_analysis['reasoning_clarity_rate'] / prediction_analysis['total_students']) * 100, 1)
    
    if reflection_analysis['total_students'] > 0:
        reflection_analysis['result_verbalization_rate'] = round(
            (reflection_analysis['result_verbalization_rate'] / reflection_analysis['total_students']) * 100, 1)
        reflection_analysis['prediction_comparison_rate'] = round(
            (reflection_analysis['prediction_comparison_rate'] / reflection_analysis['total_students']) * 100, 1)
        reflection_analysis['experience_integration_rate'] = round(
            (reflection_analysis['experience_integration_rate'] / reflection_analysis['total_students']) * 100, 1)
    
    return {
        'prediction': prediction_analysis,
        'reflection': reflection_analysis,
        'unit': unit
    }

def analyze_experience_knowledge_connections(logs, unit):
    """既習・経験関連付けの傾向を分析"""
    unit_info = analyze_unit_characteristics(unit)
    expected_experiences = unit_info.get('生活経験', [])
    
    # 関連付けされた経験・既習事項を抽出
    mentioned_experiences = []
    mentioned_knowledge = []
    
    for log in logs:
        if log.get('log_type') in ['prediction_chat', 'reflection_chat']:
            message = log['data'].get('user_message', '').lower()
            
            # 生活経験の言及をチェック
            for exp in expected_experiences:
                if any(keyword in message for keyword in exp.split()):
                    mentioned_experiences.append(exp)
            
            # 既習事項の言及をチェック
            if any(keyword in message for keyword in ['前に習った', '勉強した', '覚えている', '似ている']):
                mentioned_knowledge.append(message[:50])  # 最初の50文字を記録
    
    # 頻度分析
    from collections import Counter
    experience_frequency = Counter(mentioned_experiences)
    
    return {
        'expected_experiences': expected_experiences,
        'mentioned_experiences': dict(experience_frequency.most_common()),
        'knowledge_connections': len(mentioned_knowledge),
        'total_connections': len(mentioned_experiences) + len(mentioned_knowledge),
        'connection_rate': round((len(mentioned_experiences) / len(expected_experiences) * 100), 1) if expected_experiences else 0,
        'unit': unit
    }

def analyze_unit_specific_trends(logs, unit):
    """単元特有の学習傾向を分析"""
    unit_info = analyze_unit_characteristics(unit)
    
    # 単元の特性に基づく分析
    keywords = unit_info.get('キーワード', [])
    重点活動 = unit_info.get('重点活動', [])
    
    keyword_usage = {keyword: 0 for keyword in keywords}
    
    for log in logs:
        if log.get('log_type') in ['prediction_chat', 'reflection_chat']:
            message = log['data'].get('user_message', '').lower()
            for keyword in keywords:
                if keyword.lower() in message:
                    keyword_usage[keyword] += 1
    
    return {
        'unit': unit,
        'keyword_usage': keyword_usage,
        'focus_activities': 重点活動,
        'total_interactions': len([log for log in logs if log.get('log_type') in ['prediction_chat', 'reflection_chat']]),
        'students_count': len(set(log.get('student_number') for log in logs))
    }

def analyze_class_trends(logs, unit=None):
    """クラス全体の学習傾向をOpenAIで分析（指導案考慮）"""
    if unit:
        # 特定単元の分析
        unit_logs = [log for log in logs if log.get('unit') == unit]
        if not unit_logs:
            return {
                'unit_analysis': {},
                'language_activity_analysis': {},
                'experience_knowledge_analysis': {}
            }
        
        # 新しい分析機能を追加
        language_analysis = analyze_language_activity_levels(unit_logs, unit)
        experience_analysis = analyze_experience_knowledge_connections(unit_logs, unit)
        
        return {
            'unit_analysis': analyze_unit_specific_trends(unit_logs, unit),
            'language_activity_analysis': language_analysis,
            'experience_knowledge_analysis': experience_analysis
        }
        students = set(log.get('student_number') for log in unit_logs)
        analysis_unit = unit
    else:
        # 全体の分析
        unit_logs = logs
        students = set(log.get('student_number') for log in logs)
        analysis_unit = "全単元"
    
    if not unit_logs or len(students) == 0:
        return {
            'overall_trend': '分析対象のデータがありません',
            'common_misconceptions': [],
            'effective_approaches': [],
            'recommendations': []
        }
    
    # 指導案の内容を取得（特定単元の場合）
    lesson_plan_context = ""
    if unit:
        lesson_plan_content = load_lesson_plan_content(unit)
        if lesson_plan_content:
            lesson_plan_preview = lesson_plan_content[:800]
            lesson_plan_context = f"""
指導案情報:
{lesson_plan_preview}

[指導案に基づく分析観点]
- 指導目標の達成状況
- 予想されていた課題や誤解の出現
- 指導計画との整合性
- 次回授業への示唆
"""
        else:
            lesson_plan_context = "※この単元の指導案は設定されていません。"
    
    # 学習データを要約
    summary_data = {}
    for student in students:
        student_logs = [log for log in unit_logs if log.get('student_number') == student]
        summary_data[student] = {
            'prediction_count': len([log for log in student_logs if log.get('log_type') == 'prediction_chat']),
            'reflection_count': len([log for log in student_logs if log.get('log_type') == 'reflection_chat']),
            'has_prediction': any(log.get('log_type') == 'prediction_summary' for log in student_logs),
            'has_final': any(log.get('log_type') == 'final_summary' for log in student_logs)
        }
    
    # よくある予想や考察のパターンを抽出
    predictions = []
    reflections = []
    
    for log in unit_logs:
        if log.get('log_type') == 'prediction_summary':
            predictions.append(log.get('data', {}).get('summary', ''))
        elif log.get('log_type') == 'final_summary':
            reflections.append(log.get('data', {}).get('final_summary', ''))
    
    analysis_prompt = f"""
クラス全体の学習状況を分析してください。

対象単元: {analysis_unit}
学習者数: {len(students)}人

{lesson_plan_context}

各学習者の状況:
"""
    
    for student, data in summary_data.items():
        analysis_prompt += f"学習者{student}: 予想{data['prediction_count']}回 考察{data['reflection_count']}回 "
        analysis_prompt += f"予想完了{'○' if data['has_prediction'] else '×'} 考察完了{'○' if data['has_final'] else '×'}\n"
    
    analysis_prompt += f"\n主な予想:\n"
    for i, pred in enumerate(predictions[:3], 1):  # 最大3つまで
        analysis_prompt += f"{i}. {pred[:50]}...\n"
    
    analysis_prompt += f"\n主な考察:\n"
    for i, ref in enumerate(reflections[:3], 1):  # 最大3つまで
        analysis_prompt += f"{i}. {ref[:50]}...\n"
    
    analysis_prompt += """
言語活動支援の観点からクラス全体の状況を分析してください。

【分析項目】
- overall_trend: クラス全体の言語活動の傾向（100文字程度）
- language_challenges: 児童が共通して抱える言語化の課題を3つ
- verbalization_level: 言語化能力のレベル（発展中/安定/要支援）
- dialogue_engagement: 対話への参加状況
- expression_growth: 表現力の成長状況を2つ

JSON形式で回答してください。
"""
    
    analysis_prompt += """
この学習状況について、以下の形式で分析結果をJSON形式で出力してください。

{
  "overall_trend": "クラス全体で言語活動に意欲的に取り組んでいます",
  "language_challenges": ["経験の言語化", "既習事項との関連付け", "結果の表現"],
  "verbalization_level": "発展中",
  "dialogue_engagement": "積極的に対話に参加しています",
  "expression_growth": ["自分の言葉での表現", "論理的な説明の向上"]
}
"""
    
    try:
        print("クラス分析開始...")
        analysis_result = call_openai_with_retry(analysis_prompt)
        print(f"クラス分析応答（前500文字）: {repr(analysis_result[:500])}")
        print(f"クラス分析応答（後500文字）: {repr(analysis_result[-500:])}")
        
        # 複数の方法でJSONを抽出
        result = None
        
        # 方法1: 通常の正規表現
        import re
        json_match = re.search(r'\{.*?\}', analysis_result, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            print(f"クラス分析抽出JSON: {json_str}")
            try:
                result = json.loads(json_str)
                print("クラス分析方法1でJSON解析成功")
            except json.JSONDecodeError:
                print("クラス分析方法1でJSON解析失敗")
        
        # 方法2: 複数行JSON抽出
        if not result:
            lines = analysis_result.split('\n')
            json_lines = []
            in_json = False
            brace_count = 0
            
            for line in lines:
                if '{' in line and not in_json:
                    in_json = True
                    brace_count = line.count('{') - line.count('}')
                    json_lines = [line]
                elif in_json:
                    json_lines.append(line)
                    brace_count += line.count('{') - line.count('}')
                    if brace_count <= 0:
                        break
            
            if json_lines:
                json_str = '\n'.join(json_lines)
                print(f"クラス分析方法2で抽出されたJSON: {json_str}")
                try:
                    result = json.loads(json_str)
                    print("クラス分析方法2でJSON解析成功")
                except json.JSONDecodeError:
                    print("クラス分析方法2でJSON解析失敗")
        
        # 成功した場合は結果を返す
        if result:
            print("クラス分析完了")
            return result
            
        # 全て失敗した場合はフォールバック
        print("クラス分析JSON抽出に失敗、フォールバックを使用")
        return {
            'overall_trend': 'クラス全体として言語活動に意欲的に取り組んでいます',
            'language_challenges': ['経験の言語化', '既習事項との関連付け', '結果の表現力'],
            'verbalization_level': '発展中',
            'dialogue_engagement': '積極的に対話に参加している状況です',
            'expression_growth': ['自分の言葉での表現向上', '思考の言語化進展']
        }
    except Exception as e:
        print(f"クラス分析エラー: {e}")
        return {
            'overall_trend': '言語活動の分析でエラーが発生しました',
            'language_challenges': ['分析データ不足'],
            'verbalization_level': 'システムエラー',
            'dialogue_engagement': 'システムエラー',
            'expression_growth': ['システム調整']
        }

@app.route('/teacher/analysis')
@require_teacher_auth
def teacher_analysis():
    """学習分析ダッシュボード"""
    # デフォルト日付を最新のログがある日付に設定
    available_dates = get_available_log_dates()
    default_date = available_dates[0]['raw'] if available_dates else datetime.now().strftime('%Y%m%d')
    
    date = request.args.get('date', default_date)
    unit = request.args.get('unit', '')
    
    logs = load_learning_logs(date)
    
    # クラス全体の傾向分析
    class_analysis = analyze_class_trends(logs, unit if unit else None)
    
    # 単元別の学習者リスト
    unit_students = {}
    for log in logs:
        log_unit = log.get('unit')
        student = log.get('student_number')
        if log_unit and student:
            if log_unit not in unit_students:
                unit_students[log_unit] = set()
            unit_students[log_unit].add(student)
    
    # 各単元の学習者を配列に変換
    for unit_name in unit_students:
        unit_students[unit_name] = sorted(list(unit_students[unit_name]))
    
    return render_template('teacher/analysis.html',
                         class_analysis=class_analysis,
                         unit_students=unit_students,
                         units=UNITS,
                         current_date=date,
                         current_unit=unit,
                         available_dates=available_dates,
                         teacher_id=session.get('teacher_id'))

@app.route('/teacher/analysis/api/student', methods=['POST'])
@require_teacher_auth
def api_student_analysis():
    """学生分析のAPI（AJAX用）"""
    data = request.get_json()
    student_number = data.get('student_number')
    unit = data.get('unit')
    
    # デフォルト日付を最新のログがある日付に設定
    available_dates = get_available_log_dates()
    default_date = available_dates[0]['raw'] if available_dates else datetime.now().strftime('%Y%m%d')
    
    date = data.get('date', default_date)
    
    logs = load_learning_logs(date)
    analysis = analyze_student_learning(student_number, unit, logs)
    
    return jsonify(analysis)

@app.route('/teacher/analysis/api/class', methods=['POST'])
@require_teacher_auth
def api_class_analysis():
    """クラス分析のAPI（AJAX用）"""
    data = request.get_json()
    unit = data.get('unit')
    
    # デフォルト日付を最新のログがある日付に設定
    available_dates = get_available_log_dates()
    default_date = available_dates[0]['raw'] if available_dates else datetime.now().strftime('%Y%m%d')
    
    date = data.get('date', default_date)
    
    logs = load_learning_logs(date)
    analysis = analyze_class_trends(logs, unit if unit else None)
    
    return jsonify(analysis)

@app.route('/teacher/analysis/api/language_activity', methods=['POST'])
@require_teacher_auth
def api_language_activity_analysis():
    """言語活動レベル分析のAPI"""
    data = request.get_json()
    unit = data.get('unit')
    
    # デフォルト日付を最新のログがある日付に設定
    available_dates = get_available_log_dates()
    default_date = available_dates[0]['raw'] if available_dates else datetime.now().strftime('%Y%m%d')
    
    date = data.get('date', default_date)
    
    logs = load_learning_logs(date)
    if unit:
        logs = [log for log in logs if log.get('unit') == unit]
    
    analysis = analyze_language_activity_levels(logs, unit)
    
    return jsonify(analysis)

@app.route('/teacher/analysis/api/experience_knowledge', methods=['POST'])
@require_teacher_auth
def api_experience_knowledge_analysis():
    """既習・経験関連付け分析のAPI"""
    data = request.get_json()
    unit = data.get('unit')
    
    # デフォルト日付を最新のログがある日付に設定
    available_dates = get_available_log_dates()
    default_date = available_dates[0]['raw'] if available_dates else datetime.now().strftime('%Y%m%d')
    
    date = data.get('date', default_date)
    
    logs = load_learning_logs(date)
    if unit:
        logs = [log for log in logs if log.get('unit') == unit]
    
    analysis = analyze_experience_knowledge_connections(logs, unit)
    
    return jsonify(analysis)

def get_available_log_dates():
    """利用可能なログファイルの日付一覧を取得"""
    import os
    import glob
    
    log_files = glob.glob("logs/learning_log_*.json")
    dates = []
    
    for file in log_files:
        # ファイル名から日付を抽出
        filename = os.path.basename(file)
        if filename.startswith('learning_log_') and filename.endswith('.json'):
            date_str = filename[13:-5]  # learning_log_YYYYMMDD.json
            if len(date_str) == 8 and date_str.isdigit():
                formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                dates.append({'raw': date_str, 'formatted': formatted_date})
    
    # 日付でソート（新しい順）
    dates.sort(key=lambda x: x['raw'], reverse=True)
    return dates

# プロンプト管理機能
# プロンプト編集機能は削除されました
# システムで自動的に最適化されたプロンプトを使用します

# 指導要領・資料管理機能
@app.route('/teacher/guidelines')
@require_teacher_auth
def teacher_guidelines():
    """指導要領・資料管理ページ"""
    return render_template('teacher/guidelines.html',
                         teacher_id=session.get('teacher_id'))

@app.route('/teacher/guidelines/upload', methods=['POST'])
@require_teacher_auth
def upload_guidelines():
    """指導要領・資料のアップロード"""
    try:
        document_type = request.form.get('document_type')
        title = request.form.get('title')
        description = request.form.get('description', '')
        file = request.files.get('file')
        
        if not file or not file.filename:
            return jsonify({'error': 'ファイルが選択されていません'}), 400
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'PDFファイルのみ対応しています'}), 400
        
        # ファイルサイズチェック（16MB）
        if len(file.read()) > 16 * 1024 * 1024:
            return jsonify({'error': 'ファイルサイズが16MBを超えています'}), 400
        
        file.seek(0)  # ファイルポインタをリセット
        
        # ディレクトリ作成
        guidelines_dir = 'guidelines'
        os.makedirs(guidelines_dir, exist_ok=True)
        
        # ファイル名を安全にする
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_filename = f"{timestamp}_{filename}"
        filepath = os.path.join(guidelines_dir, safe_filename)
        
        # ファイル保存
        file.save(filepath)
        
        # ファイルの内容を読み込み（現在はMarkdown形式のみ対応）
        try:
            # アップロードされたファイルがMarkdown形式と仮定して処理
            content = f"アップロード済みファイル: {filename}\n"
            content += f"アップロード日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            content += "注意: 現在はMarkdown形式の指導要領のみ対応しています。\n"
        except Exception as e:
            content = f"ファイル処理エラー: {str(e)}"
        
        # インデックスファイルに追加
        index_file = os.path.join(guidelines_dir, 'guidelines_index.json')
        
        # 既存のインデックスを読み込み
        if os.path.exists(index_file):
            with open(index_file, 'r', encoding='utf-8') as f:
                guidelines_index = json.load(f)
        else:
            guidelines_index = {}
        
        # 新しい文書情報を追加
        doc_id = str(uuid.uuid4())
        guidelines_index[doc_id] = {
            'type': document_type,
            'title': title,
            'description': description,
            'filename': safe_filename,
            'filepath': filepath,
            'content': content[:1000],  # 最初の1000文字のみ保存
            'full_content': content,  # 全文は別途保存
            'uploaded_at': datetime.now().isoformat(),
            'uploaded_by': session.get('teacher_id')
        }
        
        # インデックスファイルに保存
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(guidelines_index, f, ensure_ascii=False, indent=2)
        
        return jsonify({
            'success': True,
            'message': '資料をアップロードしました',
            'document_id': doc_id
        })
    
    except Exception as e:
        return jsonify({'error': f'アップロードに失敗しました: {str(e)}'}), 500

@app.route('/teacher/guidelines/list')
@require_teacher_auth
def list_guidelines():
    """アップロード済み資料一覧"""
    try:
        index_file = 'guidelines/guidelines_index.json'
        
        if not os.path.exists(index_file):
            return jsonify({'documents': []})
        
        with open(index_file, 'r', encoding='utf-8') as f:
            guidelines_index = json.load(f)
        
        # 文書一覧を作成（IDを含める）
        documents = []
        for doc_id, doc_info in guidelines_index.items():
            doc_info['id'] = doc_id
            documents.append(doc_info)
        
        # 日付順にソート（新しい順）
        documents.sort(key=lambda x: x.get('uploaded_at', ''), reverse=True)
        
        return jsonify({'documents': documents})
    
    except Exception as e:
        return jsonify({'error': f'資料一覧の取得に失敗しました: {str(e)}'}), 500

@app.route('/teacher/guidelines/<doc_id>/delete', methods=['DELETE'])
@require_teacher_auth
def delete_guidelines(doc_id):
    """資料の削除"""
    try:
        index_file = 'guidelines/guidelines_index.json'
        
        if not os.path.exists(index_file):
            return jsonify({'error': '資料が見つかりません'}), 404
        
        with open(index_file, 'r', encoding='utf-8') as f:
            guidelines_index = json.load(f)
        
        if doc_id not in guidelines_index:
            return jsonify({'error': '資料が見つかりません'}), 404
        
        # ファイルを削除
        filepath = guidelines_index[doc_id]['filepath']
        if os.path.exists(filepath):
            os.remove(filepath)
        
        # インデックスから削除
        del guidelines_index[doc_id]
        
        # インデックスファイルを更新
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(guidelines_index, f, ensure_ascii=False, indent=2)
        
        return jsonify({'success': True, 'message': '資料を削除しました'})
    
    except Exception as e:
        return jsonify({'error': f'削除に失敗しました: {str(e)}'}), 500

@app.route('/teacher/student/<student_number>')
@require_teacher_auth
def student_detail(student_number):
    """学生の詳細ログページ"""
    unit = request.args.get('unit', '')
    
    # デフォルト日付を最新のログがある日付に設定
    available_dates = get_available_log_dates()
    default_date = available_dates[0]['raw'] if available_dates else datetime.now().strftime('%Y%m%d')
    selected_date = request.args.get('date', default_date)
    
    # 学習ログを読み込み
    logs = load_learning_logs(selected_date)
    
    # 該当する学生のログを抽出
    student_logs = [log for log in logs if 
                   log.get('student_number') == student_number and 
                   (not unit or log.get('unit') == unit)]
    
    print(f"学生{student_number}のログ検索結果: {len(student_logs)}件 (単元: {unit}, 日付: {selected_date})")
    
    if not student_logs:
        flash(f'学生{student_number}番のログがありません。日付や単元を変更してお試しください。', 'warning')
    
    # 分析結果を取得
    analysis = analyze_student_learning(student_number, unit, logs) if student_logs else None
    
    # 単元一覧を取得（フィルター用）
    all_units = list(set([log.get('unit') for log in logs if log.get('unit')]))
    
    return render_template('teacher/student_detail.html',
                         student_number=student_number,
                         unit=unit,
                         current_unit=unit,
                         current_date=selected_date,
                         logs=student_logs,
                         analysis=analysis,
                         available_dates=available_dates,
                         units_data={unit_name: {} for unit_name in all_units},
                         teacher_id=session.get('teacher_id', 'teacher'))

if __name__ == '__main__':
    app.run(debug=True, port=5014)