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

# 学習進行状況管理用のファイルパス
LEARNING_PROGRESS_FILE = 'learning_progress.json'

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
    "teacher": "science",  # 全クラス管理者
    "4100": "science",  # 1組担任
    "4200": "science",  # 2組担任
    "4300": "science",  # 3組担任
    "4400": "science",  # 4組担任
}

# 教員IDとクラスの対応
TEACHER_CLASS_MAPPING = {
    "teacher": ["class1", "class2", "class3", "class4"],  # 全クラス管理可能
    "4100": ["class1"],  # 1組のみ
    "4200": ["class2"],  # 2組のみ
    "4300": ["class3"],  # 3組のみ
    "4400": ["class4"],  # 4組のみ
}

# 生徒IDとクラスの対応
STUDENT_CLASS_MAPPING = {
    "class1": list(range(4101, 4131)),  # 4101-4130
    "class2": list(range(4201, 4231)),  # 4201-4230
    "class3": list(range(4301, 4331)),  # 4301-4330
    "class4": list(range(4401, 4431)),  # 4401-4430
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
try:
    client = openai.OpenAI(api_key=api_key)
except Exception as e:
    client = None

# Gemini APIの設定（チャットボット用）
import google.generativeai as genai
gemini_api_key = os.getenv('GEMINI_API_KEY')
if gemini_api_key:
    genai.configure(api_key=gemini_api_key)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')  # 最新の利用可能なモデル
else:
    gemini_model = None

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

# 学習進行状況管理機能
def load_learning_progress():
    """学習進行状況を読み込み"""
    if os.path.exists(LEARNING_PROGRESS_FILE):
        try:
            with open(LEARNING_PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            return {}
    return {}

def save_learning_progress(progress_data):
    """学習進行状況を保存"""
    try:
        with open(LEARNING_PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def get_student_progress(class_number, student_number, unit):
    """特定の学習者の単元進行状況を取得"""
    progress_data = load_learning_progress()
    student_id = f"{class_number}_{student_number}"
    
    if student_id not in progress_data:
        progress_data[student_id] = {}
    
    if unit not in progress_data[student_id]:
        progress_data[student_id][unit] = {
            "current_stage": "prediction",
            "last_access": datetime.now().isoformat(),
            "stage_progress": {
                "prediction": {
                    "started": False,
                    "conversation_count": 0,
                    "summary_created": False,
                    "last_message": ""
                },
                "experiment": {
                    "started": False,
                    "completed": False
                },
                "reflection": {
                    "started": False,
                    "conversation_count": 0,
                    "summary_created": False
                }
            },
            "conversation_history": []
        }
    
    return progress_data[student_id][unit]

def update_student_progress(class_number, student_number, unit, stage=None, **kwargs):
    """学習者の進行状況を更新"""
    progress_data = load_learning_progress()
    student_id = f"{class_number}_{student_number}"
    
    # 現在の進行状況を取得
    current_progress = get_student_progress(class_number, student_number, unit)
    
    # 最終アクセス時刻を更新
    current_progress["last_access"] = datetime.now().isoformat()
    
    # 現在の段階を更新（指定された場合）
    if stage:
        current_progress["current_stage"] = stage
    
    # 段階別の進行状況を更新
    current_stage = current_progress["current_stage"]
    if current_stage in current_progress["stage_progress"]:
        stage_data = current_progress["stage_progress"][current_stage]
        
        # 引数で渡された情報で更新
        for key, value in kwargs.items():
            if key in stage_data:
                stage_data[key] = value
    
    # 進行状況を保存
    if student_id not in progress_data:
        progress_data[student_id] = {}
    progress_data[student_id][unit] = current_progress
    
    save_learning_progress(progress_data)
    return current_progress

def check_resumption_needed(class_number, student_number, unit):
    """復帰が必要かチェック"""
    progress = get_student_progress(class_number, student_number, unit)
    
    # 予想段階で対話がある場合
    if progress["stage_progress"]["prediction"]["conversation_count"] > 0:
        return True
    
    # 実験段階が開始されている場合
    if progress["stage_progress"]["experiment"]["started"]:
        return True
    
    # 考察段階で対話がある場合  
    if progress["stage_progress"]["reflection"]["conversation_count"] > 0:
        return True
    
    return False

def get_progress_summary(progress):
    """進行状況の要約を生成"""
    stage_progress = progress.get('stage_progress', {})
    current_stage = progress.get('current_stage', 'prediction')
    
    if current_stage == 'prediction':
        conv_count = stage_progress.get('prediction', {}).get('conversation_count', 0)
        if conv_count > 0:
            return f"予想段階（対話{conv_count}回）"
        else:
            return "未開始"
    elif current_stage == 'experiment':
        if stage_progress.get('experiment', {}).get('started', False):
            return "実験段階"
        else:
            return "予想完了"
    elif current_stage == 'reflection':
        conv_count = stage_progress.get('reflection', {}).get('conversation_count', 0)
        if conv_count > 0:
            return f"考察段階（対話{conv_count}回）"
        else:
            return "実験完了"
    else:
        return "学習完了"

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
        return response

def load_markdown_content(file_path):
    """Markdownファイルからテキストを読み込む"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        return content.strip()
    except Exception as e:
        return None

# APIコール用のリトライ関数
def call_openai_with_retry(prompt, max_retries=3, delay=2, unit=None, stage=None):
    """OpenAI APIを呼び出し、エラー時はリトライする
    
    Args:
        prompt: 文字列またはメッセージリスト
        max_retries: リトライ回数
        delay: リトライ間隔（秒）
        unit: 単元名
        stage: 学習段階
    """
    if client is None:
        return "AI システムの初期化に問題があります。管理者に連絡してください。"
    
    # promptがリストの場合（メッセージフォーマット）
    if isinstance(prompt, list):
        messages = prompt
    else:
        # promptが文字列の場合（従来フォーマット）
        messages = [{"role": "user", "content": prompt}]
    
    for attempt in range(max_retries):
        try:
            import time
            start_time = time.time()
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=2000,
                temperature=0.3,
                timeout=30
            )
            
            if response.choices and response.choices[0].message.content:
                content = response.choices[0].message.content
                # マークダウン除去を削除（MDファイルのプロンプトに従う）
                return content
            else:
                raise Exception("空の応答が返されました")
                
        except Exception as e:
            error_msg = str(e)
            
            if "API_KEY" in error_msg.upper() or "invalid_api_key" in error_msg.lower():
                return "APIキーの設定に問題があります。管理者に連絡してください。"
            elif "QUOTA" in error_msg.upper() or "LIMIT" in error_msg.upper() or "rate_limit_exceeded" in error_msg.lower():
                return "API利用制限に達しました。しばらく待ってから再度お試しください。"
            elif "TIMEOUT" in error_msg.upper() or "DNS" in error_msg.upper() or "503" in error_msg:
                if attempt < max_retries - 1:
                    wait_time = delay * (attempt + 1)
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

def get_initial_ai_message(unit_name, stage='prediction'):
    """段階と単元に応じた最初のAIメッセージを生成（プロンプトMDに従う）"""
    if stage == 'prediction':
        # プロンプトMDの指示に従った最初の質問
        if unit_name == "空気の温度と体積":
            return "空気を温めると体積はどうなると思いますか？"
        elif unit_name == "金属のあたたまり方":
            return "金属を温めたとき、どのようにあたたまっていくと思いますか？"
        elif unit_name == "水のあたたまり方":
            return "水を温めたとき、どのようにあたたまっていくと思いますか？"
        elif unit_name == "水を熱し続けた時の温度と様子":
            return "水を熱し続けると、温度や様子はどうなると思いますか？"
        else:
            # デフォルト
            task_content = load_task_content(unit_name)
            return f"{task_content.split('。')[0]}と思いますか？"
    
    elif stage == 'reflection':
        # 考察段階では実験結果について問う
        return "実験でどのような結果になりましたか？"
    
    else:
        # その他の段階
        return "あなたの考えを聞かせてください。"

# ソクラテス問答法ガイドを読み込む関数
def load_socratic_method_guide():
    """ソクラテス問答法のガイドを読み込む"""
    try:
        with open('docs/ソクラテス問答法とは.md', 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        # ガイドファイルが見つからない場合は空文字を返す
        return ""

# 単元ごとのプロンプトを読み込む関数
def load_unit_prompt(unit_name):
    """単元専用のプロンプトファイルを読み込み、ソクラテス問答法ガイドと統合する"""
    # 1. ソクラテス問答法の共通ガイドを読み込み
    socratic_guide = load_socratic_method_guide()
    
    # 2. 単元固有のプロンプトを読み込み
    try:
        with open(f'prompts/{unit_name}.md', 'r', encoding='utf-8') as f:
            unit_content = f.read().strip()
    except FileNotFoundError:
        unit_content = ""
    
    # 3. 統合プロンプトを作成
    if socratic_guide and unit_content:
        # 両方が存在する場合：統合して返す
        integrated_prompt = f"""{socratic_guide}

---

# 単元固有の指示

{unit_content}

---

# 統合指針

上記のソクラテス問答法の原則と単元固有の知識を統合して、児童との対話を行ってください。

- ソクラテス問答法の基本原則（答えを教えない、質問で導く、自分で気づかせる）を常に守る
- 単元MDの経験例や質問手順を活用する
- 自然な言い換えを適用し、小学生が理解できる表現を使う
- 児童の発言に応じて柔軟に対応する"""
        return integrated_prompt
    
    elif unit_content:
        # 単元プロンプトのみ存在する場合
        return unit_content
    
    elif socratic_guide:
        # ソクラテスガイドのみ存在する場合
        return socratic_guide
    
    else:
        # どちらも存在しない場合：フォールバック
        return "児童の発言をよく聞いて、適切な質問で考えを引き出してください。"


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

# チャットボット設定管理
CHATBOT_CONFIG_FILE = 'chatbot_config.json'

def get_chatbot_status(class_name=None):
    """チャットボットの有効/無効状態を取得
    
    Args:
        class_name: クラス名 ("class1", "class2", "class3", "class4")
                   Noneの場合は全体の状態を返す
    """
    if os.path.exists(CHATBOT_CONFIG_FILE):
        try:
            with open(CHATBOT_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
                # クラス指定がある場合
                if class_name:
                    return config.get('classes', {}).get(class_name, {}).get('enabled', True)
                
                # 全体の状態を返す（後方互換性）
                return config.get('enabled', True)
        except:
            return True
    return True  # デフォルトは有効

def set_chatbot_status(enabled, class_name=None):
    """チャットボットの有効/無効状態を設定
    
    Args:
        enabled: 有効/無効フラグ
        class_name: クラス名 ("class1", "class2", "class3", "class4")
                   Noneの場合は全体の設定を変更
    """
    try:
        # 既存の設定を読み込み
        config = {'enabled': True, 'classes': {}}
        if os.path.exists(CHATBOT_CONFIG_FILE):
            try:
                with open(CHATBOT_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except:
                pass
        
        # クラス構造を初期化
        if 'classes' not in config:
            config['classes'] = {
                'class1': {'enabled': True},
                'class2': {'enabled': True},
                'class3': {'enabled': True},
                'class4': {'enabled': True}
            }
        
        # クラス指定がある場合
        if class_name:
            if class_name not in config['classes']:
                config['classes'][class_name] = {}
            config['classes'][class_name]['enabled'] = enabled
            config['classes'][class_name]['updated_at'] = datetime.now().isoformat()
        else:
            # 全体の設定を変更
            config['enabled'] = enabled
            config['updated_at'] = datetime.now().isoformat()
        
        # 保存
        with open(CHATBOT_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving chatbot config: {e}")
        return False

def get_student_class(student_number):
    """生徒番号からクラスを特定
    
    Args:
        student_number: 生徒番号 (int or str)
    
    Returns:
        クラス名 ("class1", "class2", "class3", "class4") または None
    """
    try:
        student_num = int(student_number)
        
        # テストID 1111は全クラス利用可能
        if student_num == 1111:
            return "all"
        
        # 各クラスの範囲をチェック
        for class_name, student_ids in STUDENT_CLASS_MAPPING.items():
            if student_num in student_ids:
                return class_name
        
        return None
    except (ValueError, TypeError):
        return None

def get_teacher_classes(teacher_id):
    """教員IDから管理可能なクラス一覧を取得
    
    Args:
        teacher_id: 教員ID
    
    Returns:
        クラス名のリスト ["class1", "class2", ...]
    """
    return TEACHER_CLASS_MAPPING.get(teacher_id, [])

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
    # チャットボットの表示状態を取得
    chatbot_enabled = get_chatbot_status()
    return render_template('index.html', chatbot_enabled=chatbot_enabled)

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
    
    # 各単元の進行状況をチェック
    unit_progress = {}
    for unit in UNITS:
        progress = get_student_progress(class_number, student_number, unit)
        needs_resumption = check_resumption_needed(class_number, student_number, unit)
        unit_progress[unit] = {
            'current_stage': progress['current_stage'],
            'needs_resumption': needs_resumption,
            'last_access': progress.get('last_access', ''),
            'progress_summary': get_progress_summary(progress)
        }
    
    return render_template('select_unit.html', units=UNITS, unit_progress=unit_progress)

@app.route('/prediction')
def prediction():
    class_number = request.args.get('class', session.get('class_number', '1'))
    student_number = request.args.get('number', session.get('student_number', '1'))
    unit = request.args.get('unit')
    resume = request.args.get('resume', 'false').lower() == 'true'
    
    session['class_number'] = class_number
    session['student_number'] = student_number
    session['unit'] = unit
    
    task_content = load_task_content(unit)
    session['task_content'] = task_content
    
    # 進行状況をチェック
    progress = get_student_progress(class_number, student_number, unit)
    
    if resume and progress['stage_progress']['prediction']['conversation_count'] > 0:
        # 対話履歴を復元
        session['conversation'] = progress.get('conversation_history', [])
        resumption_info = {
            'is_resumption': True,
            'last_conversation_count': progress['stage_progress']['prediction']['conversation_count'],
            'last_access': progress.get('last_access', '')
        }
    else:
        # 新規開始
        session['conversation'] = []
        resumption_info = {'is_resumption': False}
        
        # 予想段階開始を記録
        update_student_progress(class_number, student_number, unit, 
                              stage='prediction', started=True)
    
    # 単元に応じた最初のAIメッセージを取得
    initial_ai_message = get_initial_ai_message(unit, stage='prediction')
    
    return render_template('prediction.html', unit=unit, task_content=task_content, 
                         resumption_info=resumption_info, initial_ai_message=initial_ai_message)

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message')
    input_metadata = request.json.get('metadata', {})
    conversation = session.get('conversation', [])
    unit = session.get('unit')
    task_content = session.get('task_content')
    student_number = session.get('student_number')
    
    # 対話履歴に追加
    conversation.append({'role': 'user', 'content': user_message})
    
    # 単元ごとのプロンプトを読み込み
    unit_prompt = load_unit_prompt(unit)
    
    # 対話履歴を含めてプロンプト作成
    # OpenAI APIに送信するためにメッセージ形式で構築
    messages = [
        {"role": "system", "content": unit_prompt}
    ]
    
    # 対話履歴をメッセージフォーマットで追加
    for msg in conversation:
        messages.append({
            "role": msg['role'],
            "content": msg['content']
        })
    
    try:
        ai_response = call_openai_with_retry(messages, unit=unit, stage='prediction')
        
        # JSON形式のレスポンスの場合は解析して純粋なメッセージを抽出
        ai_message = extract_message_from_json_response(ai_response)
        
        # 予想・考察段階ではマークダウン除去をスキップ（MDファイルのプロンプトに従う）
        # ai_message = remove_markdown_formatting(ai_message)
        
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
        
        # 進行状況を更新
        conversation_count = len(conversation) // 2
        update_student_progress(
            session.get('class_number', '1'),
            session.get('student_number'),
            unit,
            conversation_count=conversation_count,
            last_message=user_message,
            conversation_history=conversation[-10:]  # 最新10件のみ保存
        )
        
        # 対話が1回以上あれば、いつでも予想のまとめを作成可能
        suggest_summary = len(conversation) >= 2  # user + AI で最低1セット
        
        response_data = {
            'response': ai_message,
            'suggest_summary': suggest_summary
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'error': f'AI接続エラーが発生しました。しばらく待ってから再度お試しください。'}), 500

@app.route('/summary', methods=['POST'])
def summary():
    conversation = session.get('conversation', [])
    unit = session.get('unit')
    
    # 単元のプロンプトを読み込み、要約指示を追加
    unit_prompt = load_unit_prompt(unit)
    
    # 要約専用のプロンプトを作成
    summary_instruction = f"""{unit_prompt}

#重要な指示
これまでの対話内容をもとに、#要約フォーマットに従って予想をまとめてください。
- 「話した内容をもとにして，まとめてみるね。」という前置きをつけること
- 「〜と思う。なぜなら〜だから。」の形式でまとめること
- 子どもが話した内容だけを使うこと
- #要約のサンプルを参考にすること
"""
    
    # メッセージフォーマットで構築
    messages = [
        {"role": "system", "content": summary_instruction}
    ]
    
    # 対話履歴をメッセージフォーマットで追加
    for msg in conversation:
        messages.append({
            "role": msg['role'],
            "content": msg['content']
        })
    
    # 最後に要約を促すメッセージを追加
    messages.append({
        "role": "user",
        "content": "これまでの話をもとに、予想をまとめてください。"
    })
    
    try:
        summary_response = call_openai_with_retry(messages)
        
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
        return jsonify({'error': f'まとめ生成中にエラーが発生しました。'}), 500

@app.route('/experiment')
def experiment():
    return render_template('experiment.html')

@app.route('/reflection')
def reflection():
    unit = session.get('unit')
    prediction_summary = session.get('prediction_summary')
    
    # 単元に応じた最初のAIメッセージを取得
    initial_ai_message = get_initial_ai_message(unit, stage='reflection')
    
    return render_template('reflection.html', 
                         unit=unit,
                         prediction_summary=prediction_summary,
                         initial_ai_message=initial_ai_message)

@app.route('/reflect_chat', methods=['POST'])
def reflect_chat():
    user_message = request.json.get('message')
    reflection_conversation = session.get('reflection_conversation', [])
    unit = session.get('unit')
    prediction_summary = session.get('prediction_summary', '')
    
    # 反省対話履歴に追加
    reflection_conversation.append({'role': 'user', 'content': user_message})
    
    # プロンプトファイルからベースプロンプトを取得
    unit_prompt = load_unit_prompt(unit)
    
    # メッセージフォーマットで対話履歴を構築
    messages = [
        {"role": "system", "content": unit_prompt}
    ]
    
    # 対話履歴をメッセージフォーマットで追加
    for msg in reflection_conversation:
        messages.append({
            "role": msg['role'],
            "content": msg['content']
        })
    
    try:
        ai_response = call_openai_with_retry(messages, unit=unit, stage='reflection')
        
        # JSON形式のレスポンスの場合は解析して純粋なメッセージを抽出
        ai_message = extract_message_from_json_response(ai_response)
        
        # 予想・考察段階ではマークダウン除去をスキップ（MDファイルのプロンプトに従う）
        # ai_message = remove_markdown_formatting(ai_message)
        
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
        return jsonify({'error': f'AI接続エラーが発生しました。しばらく待ってから再度お試しください。'}), 500

@app.route('/final_summary', methods=['POST'])
def final_summary():
    reflection_conversation = session.get('reflection_conversation', [])
    prediction_summary = session.get('prediction_summary', '')
    unit = session.get('unit')
    
    # 単元のプロンプトを読み込み、考察の要約指示を追加
    unit_prompt = load_unit_prompt(unit)
    
    # 考察要約専用のプロンプトを作成
    final_instruction = f"""{unit_prompt}

#重要な指示
これまでの対話内容と予想をもとに、#要約フォーマットに従って考察をまとめてください。
- 「話した内容をもとにして，まとめてみるね。」という前置きをつけること
- 「〜ことがわかった。〜からだと思う。〜にも言えると思った。」の形式でまとめること
- 実験結果、予想との比較、日常生活とのつながりを含めること
- 子どもが話した内容だけを使うこと
- #要約のサンプル（考察）を参考にすること

学習者の予想: {prediction_summary}
"""
    
    # メッセージフォーマットで構築
    messages = [
        {"role": "system", "content": final_instruction}
    ]
    
    # 対話履歴をメッセージフォーマットで追加
    for msg in reflection_conversation:
        messages.append({
            "role": msg['role'],
            "content": msg['content']
        })
    
    # 最後に要約を促すメッセージを追加
    messages.append({
        "role": "user",
        "content": "これまでの話と予想をもとに、考察をまとめてください。"
    })
    
    try:
        final_summary_response = call_openai_with_retry(messages)
        
        # JSON形式のレスポンスの場合は解析して純粋なメッセージを抽出
        final_summary_text = extract_message_from_json_response(final_summary_response)
        
        # 要約段階ではマークダウン除去をスキップ（MDファイルのプロンプトに従う）
        # final_summary_text = remove_markdown_formatting(final_summary_text)
        
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

@app.route('/teacher/chatbot/toggle', methods=['POST'])
@require_teacher_auth
def toggle_chatbot():
    """チャットボットの表示制御（クラス別）"""
    data = request.json
    enabled = data.get('enabled', True)
    class_name = data.get('class_name')  # "class1", "class2", etc.
    
    # 教員が該当クラスを管理できるかチェック
    teacher_id = session.get('teacher_id')
    teacher_classes = get_teacher_classes(teacher_id)
    
    if class_name and class_name not in teacher_classes:
        return jsonify({'success': False, 'error': '権限がありません'}), 403
    
    if set_chatbot_status(enabled, class_name):
        return jsonify({'success': True, 'enabled': enabled, 'class_name': class_name})
    else:
        return jsonify({'success': False, 'error': '設定の保存に失敗しました'}), 500

@app.route('/teacher')
@require_teacher_auth
def teacher():
    """教員用ダッシュボード"""
    teacher_id = session.get('teacher_id')
    teacher_classes = get_teacher_classes(teacher_id)
    
    # 各クラスのチャットボット設定を読み込み
    chatbot_settings = {}
    for class_name in ['class1', 'class2', 'class3', 'class4']:
        chatbot_settings[class_name] = {
            'enabled': get_chatbot_status(class_name),
            'can_edit': class_name in teacher_classes
        }
    
    return render_template('teacher/dashboard.html', 
                         units=UNITS, 
                         teacher_id=teacher_id,
                         teacher_classes=teacher_classes,
                         chatbot_settings=chatbot_settings)

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
    
    # フィルタリング
    if unit:
        logs = [log for log in logs if log.get('unit') == unit]
    if student:
        logs = [log for log in logs if log.get('student_number') == student]
    
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

# チャットボットのログ保存関数
def save_chatbot_log(student_id, user_message, ai_response):
    """チャットボットの会話ログを保存"""
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'student_id': student_id,
        'user_message': user_message,
        'ai_response': ai_response
    }
    
    log_file = f"logs/chatbot_log_{datetime.now().strftime('%Y%m%d')}.json"
    
    # 既存のログを読み込み
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            logs = json.load(f)
    else:
        logs = []
    
    logs.append(log_entry)
    
    # ログを保存
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

def is_inappropriate_content(message):
    """学習に関係ない内容かどうかをチェック"""
    # 小文字に変換
    msg_lower = message.lower()
    
    # 学習関連のキーワード（これらが含まれていればOK）
    learning_keywords = [
        '作文', '読書', '感想', '日記', '文章', '書く', 'かんそう', 'さくぶん',
        '理科', '実験', '観察', 'じっけん', 'かんさつ',
        '算数', '計算', '問題', 'さんすう', 'けいさん',
        '国語', '漢字', 'こくご', 'かんじ',
        '社会', 'しゃかい',
        '係', 'かかり', 'キャッチコピー',
        '学級会', 'がっきゅうかい', 'クラス会', '話し合い', 'はなしあい',
        '宿題', 'しゅくだい', '課題', 'かだい',
        '教科', 'きょうか', '勉強', 'べんきょう', '学習', 'がくしゅう',
        'テスト', 'しけん', '試験',
        '発表', 'はっぴょう', 'スピーチ',
        '調べる', 'しらべる', '研究', 'けんきゅう',
        'どうして', 'なぜ', 'なんで', 'どうやって',
        '教えて', 'おしえて', 'わからない', 'むずかしい',
        'ヒント', 'アイデア', '考え', 'かんがえ',
        '植物', '動物', '天気', '星', '月', '太陽',
        'しょくぶつ', 'どうぶつ', 'てんき', 'ほし', 'つき', 'たいよう',
        '水', '空気', '温度', '金属', 'きんぞく',
        'まとめ', '要約', 'ようやく'
    ]
    
    # 学習関連キーワードが含まれているかチェック
    for keyword in learning_keywords:
        if keyword in msg_lower or keyword in message:
            return False  # 学習関連なのでOK
    
    # 不適切なキーワード（雑談や学習に無関係な内容）
    inappropriate_keywords = [
        'ゲーム', 'げーむ', 'game',
        'アニメ', 'あにめ', 'anime',
        'マンガ', 'まんが', '漫画', 'manga',
        'youtube', 'ユーチューブ', 'ゆーちゅーぶ',
        'tiktok', 'ティックトック',
        '芸能', 'げいのう', 'アイドル', 'あいどる',
        '恋', 'こい', '好き', 'すき' '彼氏', '彼女',
        'お金', 'おかね', 'かね',
        '買い物', 'かいもの', 'ショッピング',
        '遊び', 'あそび', '遊ぶ', 'あそぶ'
    ]
    
    # 不適切キーワードチェック
    for keyword in inappropriate_keywords:
        if keyword in msg_lower or keyword in message:
            return True  # 不適切
    
    # 短すぎるメッセージ（「こんにちは」「hi」など）
    if len(message.strip()) < 3:
        return True
    
    # どちらにも該当しない場合は、メッセージの長さで判断
    # あまりにも短い挨拶のみは不適切とする
    greetings_only = ['こんにちは', 'おはよう', 'こんばんは', 'やあ', 'hi', 'hello', 'へろー']
    if message.strip() in greetings_only:
        return True
    
    return False  # その他は許可

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
    
    
    if not student_logs:
        flash(f'学生{student_number}番のログがありません。日付や単元を変更してお試しください。', 'warning')
    
    # 単元一覧を取得（フィルター用）
    all_units = list(set([log.get('unit') for log in logs if log.get('unit')]))
    
    return render_template('teacher/student_detail.html',
                         student_number=student_number,
                         unit=unit,
                         current_unit=unit,
                         current_date=selected_date,
                         logs=student_logs,
                         available_dates=available_dates,
                         units_data={unit_name: {} for unit_name in all_units},
                         teacher_id=session.get('teacher_id', 'teacher'))

# ========================================
# チャットボット機能（Gemini API使用）
# ========================================

@app.route('/chatbot/login')
def chatbot_login():
    """チャットボットログイン画面"""
    # チャットボットが無効の場合はホームにリダイレクト
    if not get_chatbot_status():
        flash('チャットボットは現在利用できません', 'warning')
        return redirect(url_for('index'))
    
    return render_template('chatbot_login.html')

@app.route('/chatbot/verify', methods=['POST'])
def chatbot_verify():
    """学生IDの検証"""
    # チャットボットが無効の場合はアクセス拒否
    if not get_chatbot_status():
        flash('チャットボットは現在利用できません', 'error')
        return redirect(url_for('index'))
    
    student_id = request.form.get('student_id', '').strip()
    
    # IDのバリデーション
    if not student_id or len(student_id) != 4 or not student_id.isdigit():
        flash('4桁の数字を入力してください（例：4103）', 'error')
        return redirect(url_for('chatbot_login'))
    
    # 有効なIDリストを定義
    valid_ids = set()
    
    # 教員用ID
    valid_ids.add('1111')
    
    # 4年1組～4組（各1～30番）
    for class_num in range(1, 5):  # 1, 2, 3, 4組
        for seat_num in range(1, 31):  # 1～30番
            valid_ids.add(f"4{class_num}{seat_num:02d}")
    
    # IDの有効性チェック
    if student_id not in valid_ids:
        flash('無効なIDです。正しいIDを入力してください', 'error')
        return redirect(url_for('chatbot_login'))
    
    # IDをパース
    if student_id == '1111':
        # 教員用
        session['chatbot_student_id'] = student_id
        session['chatbot_grade'] = '教員'
        session['chatbot_class'] = ''
        session['chatbot_number'] = ''
    else:
        # 学生用: 4103 = 学年:4, クラス:1, 出席番号:03
        grade = student_id[0]
        class_num = student_id[1]
        seat_num = student_id[2:4]
        
        session['chatbot_student_id'] = student_id
        session['chatbot_grade'] = grade
        session['chatbot_class'] = class_num
        session['chatbot_number'] = seat_num
    
    session['chatbot_history'] = []
    
    return redirect(url_for('chatbot'))

@app.route('/chatbot')
def chatbot():
    """小学生総合学習支援チャットボット"""
    # ログインチェック
    if 'chatbot_student_id' not in session:
        return redirect(url_for('chatbot_login'))
    
    # 生徒のクラスを特定
    student_id = session.get('chatbot_student_id')
    student_class = get_student_class(student_id)
    
    # チャットボットの表示状態をチェック
    if student_class and student_class != "all":
        # 通常の生徒：クラスごとの設定を確認
        if not get_chatbot_status(student_class):
            flash('現在、チャットボットは利用できません。', 'warning')
            return redirect(url_for('select_number'))
    elif student_class != "all":
        # クラスが特定できない場合
        flash('無効な生徒番号です。', 'error')
        return redirect(url_for('chatbot_login'))
    # student_class == "all" の場合（テストID 1111）は常に利用可能
    
    # セッションにチャット履歴がない場合は初期化
    if 'chatbot_history' not in session:
        session['chatbot_history'] = []
    
    return render_template('chatbot.html')

@app.route('/chatbot/chat', methods=['POST'])
def chatbot_chat():
    """チャットボットとの対話処理（Gemini API使用）"""
    # ログインチェック
    student_id = session.get('chatbot_student_id')
    if not student_id:
        return jsonify({'error': 'ログインしてください'}), 401
    
    # クラス別の表示制御チェック
    student_class = get_student_class(student_id)
    if student_class and student_class != "all":
        if not get_chatbot_status(student_class):
            return jsonify({'error': '現在、チャットボットは利用できません'}), 403
    elif student_class != "all":
        return jsonify({'error': '無効な生徒番号です'}), 403
    
    user_message = request.json.get('message', '')
    
    if not user_message:
        return jsonify({'error': '質問を入力してください'}), 400
    
    # フィルタリング: 学習に関係ない内容をチェック
    if is_inappropriate_content(user_message):
        return jsonify({
            'response': 'ごめんね。学しゅうに関けいのある、しつもんをしてね。作文、理科、算数、国語、社会、がっきゅう活動など、学校の勉強について聞いてね！',
            'filtered': True
        })
    
    # チャット履歴を取得
    chat_history = session.get('chatbot_history', [])
    
    # システムプロンプト（小学生総合学習支援）
    system_prompt = """あなたは小学生の学しゅうをたすける、やさしいAIアシスタントです。

【ぜったいに守るルール】
1. **学しゅうのサポートのみ**: 学校の勉強に関けいすることだけ答える
   - ゲーム、アニメ、ざつだんには答えない
   - 「学しゅうについて聞いてね」と、やさしく言う

2. **かんたんな言葉を使う**: 小学生がわかる言葉ではなす
   - むずかしい漢字は使わない（ひらがなを多く使う）
   - かんたんな言葉で、わかりやすく

3. **みじかい文ではなす**: 1つの文は、とてもみじかく
   - 1回に1つか2つのことだけ言う
   - 長い文は、2〜3つにわける

4. **考える力をのばす**: こたえを教えるだけでなく、考えるヒントを出す
   - 「どう思う？」「なぜだと思う？」と問いかける
   - 自分で考えられるように、サポートする
   - 作文は、ぜんぶ書いてあげない。考えるヒントを出す

5. **はげます言葉を入れる**:
   - 「いいね！」「すごいね！」「よく気づいたね！」
   - 「おもしろい考えだね！」「がんばっているね！」

【できること】
小学生の学しゅう全はんを、サポートします：

**1. 作文・文しょうのサポート**
- 作文のテーマやアイデアを考える
- 文しょうの組み立てをたすける
- かん想文や、日記のアドバイス
- 【重要】ぜんぶ書いてあげるのではなく、考えるヒントを出す

**2. がっきゅう活動のサポート**
- 係のキャッチコピーを考える
- がっきゅう会のないようを、まとめる（文字で入力されたもの）
- クラスのもくひょうを考える
- グループ活動のアイデア出し

**3. 理科の学しゅう**
- 実けんの予そうや、考察のサポート
- 理科のしつもんに答える
- しぜんのふしぎを、いっしょに考える

**4. その他の学しゅう**
- 国語、算数、社会などの、しつもん
- じゅぎょうでわからなかったことの、説明
- しゅくだいのヒント（こたえは教えない）
- 読書かんそうのサポート

【やってはいけないこと】
❌ ゲームやアニメの話
❌ ざつだん
❌ 学しゅうに関けいのない話
❌ 作文をぜんぶ書いてあげる
❌ しゅくだいの答えを教える

【音声データについて】
- がっきゅう会の音声データは、みんなの許可をもらってから使うこと
- 先生がOKと言ったら、文字にして入力してもらう

【返とうの例】
質問「作文のテーマが思いつかない」
返答「どんなことを書きたいかな？さいきん、楽しかったことや、びっくりしたことはあった？それを教えてくれる？」

質問「係のキャッチコピーを考えたい」  
返答「どんな係かな？その係は、クラスのために、どんないいことをしているか教えてくれる？」

質問「学級会の内容をまとめたい」
返答「どんなことについて話し合ったの？どんな意見が出たか、教えてくれる？」

質問「ゲームについて教えて」
返答「ごめんね。学しゅうに関けいすることを聞いてね。作文や、理科、算数など、学校の勉強について、なんでも聞いてね！」"""
    
    try:
        # Gemini APIが利用可能かチェック
        if not gemini_model:
            # Gemini APIが使えない場合はOpenAI APIにフォールバック
            return fallback_to_openai(system_prompt, user_message, chat_history)
        
        # Gemini APIで応答を生成
        # チャット履歴を含めたコンテキストを作成
        full_context = system_prompt + "\n\n"
        for msg in chat_history[-6:]:  # 最新3往復のみ使用
            role = "ユーザー" if msg['role'] == 'user' else "AI"
            full_context += f"{role}: {msg['content']}\n"
        full_context += f"ユーザー: {user_message}\nAI: "
        
        response = gemini_model.generate_content(full_context)
        ai_response = response.text
        
        # チャット履歴を更新
        chat_history.append({'role': 'user', 'content': user_message})
        chat_history.append({'role': 'assistant', 'content': ai_response})
        
        # 履歴が長くなりすぎないように制限（最新10往復まで）
        if len(chat_history) > 20:
            chat_history = chat_history[-20:]
        
        session['chatbot_history'] = chat_history
        
        # チャットログを保存
        save_chatbot_log(student_id, user_message, ai_response)
        
        return jsonify({'response': ai_response})
        
    except Exception as e:
        print(f"Gemini API Error: {e}")
        # エラー時はOpenAI APIにフォールバック
        return fallback_to_openai(system_prompt, user_message, chat_history, student_id)

@app.route('/chatbot/reset', methods=['POST'])
def chatbot_reset():
    """チャットボットの会話履歴をリセット"""
    session['chatbot_history'] = []
    return jsonify({'status': 'success'})

def fallback_to_openai(system_prompt, user_message, chat_history, student_id):
    """Gemini APIが使えない場合のOpenAI APIフォールバック"""
    try:
        if not client:
            return jsonify({'error': 'APIが利用できません'}), 500
        
        # OpenAI API用のメッセージ形式に変換
        messages = [{"role": "system", "content": system_prompt}]
        
        # チャット履歴を追加（最新3往復）
        for msg in chat_history[-6:]:
            messages.append({
                "role": msg['role'],
                "content": msg['content']
            })
        
        # ユーザーメッセージを追加
        messages.append({"role": "user", "content": user_message})
        
        # OpenAI APIで応答を生成
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )
        
        ai_response = response.choices[0].message.content
        
        # チャット履歴を更新
        chat_history.append({'role': 'user', 'content': user_message})
        chat_history.append({'role': 'assistant', 'content': ai_response})
        
        if len(chat_history) > 20:
            chat_history = chat_history[-20:]
        
        session['chatbot_history'] = chat_history
        
        # チャットログを保存
        save_chatbot_log(student_id, user_message, ai_response)
        
        return jsonify({'response': ai_response})
        
    except Exception as e:
        print(f"OpenAI API Error: {e}")
        return jsonify({'error': 'エラーが発生しました。もう一度試してください。'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5014)