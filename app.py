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
            
            # stage（学習段階）に応じてtemperatureを設定
            # 予想段階: より創造的な回答 (0.8)
            # 考察段階: より一貫性のある回答 (0.3)
            if stage == 'prediction':
                temperature = 0.8
            elif stage == 'reflection':
                temperature = 0.3
            else:
                temperature = 0.5  # デフォルト
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=2000,
                temperature=temperature,
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
    """プロンプトファイルから最初のAIメッセージを抽出する"""
    try:
        # プロンプトファイルを読み込み
        with open(f'prompts/{unit_name}.md', 'r', encoding='utf-8') as f:
            content = f.read()
        
        import re
        
        if stage == 'prediction':
            # 予想段階の「初めの問いかけ」を探す
            # パターン: ## 初めの問いかけ の後の「...」部分を抽出
            match = re.search(r'# 予想段階での対話.*?## 初めの問いかけ\s*\n「(.+?)」', content, re.DOTALL)
            if match:
                # 「と開かれた質問から始める。」などの説明部分を除去
                question = match.group(1).split('と開かれた質問')[0].split('と子どもの言葉')[0]
                return question.strip()
            
            # 見つからない場合はデフォルト
            return f"{unit_name}について、どう思いますか？"
        
        elif stage == 'reflection':
            # 考察段階の「初めの問いかけ」を探す
            match = re.search(r'# 考察段階での対話.*?## 初めの問いかけ\s*\n「(.+?)」', content, re.DOTALL)
            if match:
                # 「と子どもの言葉で語らせる。」などの説明部分を除去
                question = match.group(1).split('と子どもの言葉')[0].split('と開かれた質問')[0]
                return question.strip()
            
            # 見つからない場合はデフォルト
            return "実験でどのような結果になりましたか？"
        
        else:
            return "あなたの考えを聞かせてください。"
            
    except FileNotFoundError:
        # ファイルが見つからない場合のフォールバック
        if stage == 'prediction':
            return f"{unit_name}について、どう思いますか？"
        elif stage == 'reflection':
            return "実験でどのような結果になりましたか？"
        else:
            return "あなたの考えを聞かせてください。"
    except Exception as e:
        # その他のエラーの場合
        print(f"初期メッセージ抽出エラー: {e}")
        if stage == 'prediction':
            return f"{unit_name}について、どう思いますか？"
        elif stage == 'reflection':
            return "実験でどのような結果になりましたか？"
        else:
            return "あなたの考えを聞かせてください。"

# 単元ごとのプロンプトを読み込む関数
def load_unit_prompt(unit_name):
    """単元専用のプロンプトファイルを読み込む"""
    try:
        with open(f'prompts/{unit_name}.md', 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        return "児童の発言をよく聞いて、適切な質問で考えを引き出してください。"


# 学習ログを保存する関数
def save_learning_log(student_number, unit, log_type, data, class_number=None):
    """学習ログをJSONファイルに保存
    
    Args:
        student_number: 出席番号 (例: "3", "15")
        unit: 単元名
        log_type: ログタイプ
        data: ログデータ
        class_number: クラス番号 (例: "1", "2")
    """
    # クラス番号と出席番号を整数に変換
    try:
        class_num = int(class_number) if class_number else None
        seat_num = int(student_number) if student_number else None
        class_display = f'{class_num}組{seat_num}番' if class_num and seat_num else f'{student_number}'
    except (ValueError, TypeError):
        class_num = None
        seat_num = None
        class_display = str(student_number)
    
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'student_number': student_number,
        'class_num': class_num,
        'seat_num': seat_num,
        'class_display': class_display,
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

def parse_student_info(student_number):
    """生徒番号からクラスと出席番号を取得
    
    Args:
        student_number: 生徒番号 (str) 例: "4103" = 4年1組3番
    
    Returns:
        dict: {'class_num': 1, 'seat_num': 3, 'display': '1組3番'} または None
    """
    try:
        if student_number == '1111':
            return {'class_num': 0, 'seat_num': 0, 'display': 'テスト'}
        
        student_str = str(student_number)
        if len(student_str) == 4 and student_str.startswith('4'):
            class_num = int(student_str[1])  # 2桁目がクラス番号
            seat_num = int(student_str[2:])  # 3-4桁目が出席番号
            return {
                'class_num': class_num,
                'seat_num': seat_num,
                'display': f'{class_num}組{seat_num}番'
            }
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
            },
            class_number=session.get('class_number')
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
        
        # 対話が2回以上あれば、予想のまとめを作成可能
        # user + AI で最低2セット（2往復）= 4メッセージ以上必要
        # ただし、実際のユーザーとの往復回数をカウント(AIの初期メッセージは除外)
        user_messages_count = sum(1 for msg in conversation if msg['role'] == 'user')
        suggest_summary = user_messages_count >= 2  # ユーザーメッセージが2回以上
        
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
これまでの対話内容をもとに、予想をまとめてください。
- 「〜と思う。なぜなら〜だから。」の形式でまとめること
- 子どもが話した内容だけを使うこと
- マークダウン記法（**予想**などの見出し）は使わないこと
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
            },
            class_number=session.get('class_number')
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
            },
            class_number=session.get('class_number')
        )
        
        # 対話が2往復以上あれば、考察のまとめを作成可能
        # ユーザーメッセージが2回以上必要
        user_messages_count = sum(1 for msg in reflection_conversation if msg['role'] == 'user')
        suggest_final_summary = user_messages_count >= 2
        
        return jsonify({
            'response': ai_message,
            'suggest_final_summary': suggest_final_summary
        })
        
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
これまでの対話内容と予想をもとに、考察をまとめてください。
- #要約のサンプルの考察部分と同じ形式で出力すること
- 「話した内容をもとにして，まとめてみるね。」という前置きの後に考察内容を書くこと
- 「〜ことがわかった。〜からだと思う。〜にも言えると思った。」の形式でまとめること
- 実験結果、予想との比較、日常生活とのつながりを含めること
- 子どもが話した内容だけを使うこと
- マークダウン記法（**考察**などの見出し）は使わないこと

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
            },
            class_number=session.get('class_number')
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

@app.route('/teacher')
@require_teacher_auth
def teacher():
    """教員用ダッシュボード"""
    teacher_id = session.get('teacher_id')
    
    return render_template('teacher/dashboard.html', 
                         units=UNITS, 
                         teacher_id=teacher_id)

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
    class_filter = request.args.get('class', '')
    student = request.args.get('student', '')
    
    logs = load_learning_logs(date)
    
    # フィルタリング
    if unit:
        logs = [log for log in logs if log.get('unit') == unit]
    
    # クラスと出席番号でフィルター（両方を組み合わせる）
    if class_filter and student:
        # クラスと出席番号の両方が指定された場合
        logs = [log for log in logs 
                if log.get('class_num') == int(class_filter) 
                and log.get('seat_num') == int(student)]
    elif class_filter:
        # クラスのみ指定された場合
        logs = [log for log in logs 
                if log.get('class_num') == int(class_filter)]
    elif student:
        # 出席番号のみ指定された場合（全クラスから該当番号を検索）
        logs = [log for log in logs 
                if log.get('seat_num') == int(student)]
    
    # 学生ごとにグループ化（クラスと出席番号の組み合わせで識別）
    students_data = {}
    for log in logs:
        class_num = log.get('class_num')
        seat_num = log.get('seat_num')
        student_num = log.get('student_number')
        
        # クラスと出席番号の組み合わせで一意のキーを生成
        student_key = f"{class_num}_{seat_num}" if class_num and seat_num else student_num
        
        if student_key not in students_data:
            # ログから直接クラスと出席番号の情報を取得
            student_info = {
                'class_num': class_num,
                'seat_num': seat_num,
                'display': log.get('class_display', f'{class_num}組{seat_num}番' if class_num and seat_num else str(student_num))
            }
            students_data[student_key] = {
                'student_number': student_num,
                'student_info': student_info,
                'units': {}
            }
        
        unit_name = log.get('unit')
        if unit_name not in students_data[student_key]['units']:
            students_data[student_key]['units'][unit_name] = {
                'prediction_chats': [],
                'prediction_summary': None,
                'reflection_chats': [],
                'final_summary': None
            }
        
        log_type = log.get('log_type')
        if log_type == 'prediction_chat':
            students_data[student_key]['units'][unit_name]['prediction_chats'].append(log)
        elif log_type == 'prediction_summary':
            students_data[student_key]['units'][unit_name]['prediction_summary'] = log
        elif log_type == 'reflection_chat':
            students_data[student_key]['units'][unit_name]['reflection_chats'].append(log)
        elif log_type == 'final_summary':
            students_data[student_key]['units'][unit_name]['final_summary'] = log
    
    # クラスと番号でソート
    students_data = dict(sorted(students_data.items(), 
                                key=lambda x: (x[1]['student_info']['class_num'] if x[1]['student_info'] else 999, 
                                             x[1]['student_info']['seat_num'] if x[1]['student_info'] else 999)))
    
    return render_template('teacher/logs.html', 
                         students_data=students_data, 
                         units=UNITS,
                         current_date=date,
                         current_unit=unit,
                         current_class=class_filter,
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
        fieldnames = ['timestamp', 'class_display', 'student_number', 'class_num', 'seat_num', 'unit', 'log_type', 'content']
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
                'class_display': log.get('class_display', ''),
                'student_number': log.get('student_number', ''),
                'class_num': log.get('class_num', ''),
                'seat_num': log.get('seat_num', ''),
                'unit': log.get('unit', ''),
                'log_type': log.get('log_type', ''),
                'content': content
            })
    
    return jsonify({'message': f'エクスポートが完了しました: {output_file}'})

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

@app.route('/teacher/student_detail')
@require_teacher_auth
def student_detail():
    """学生の詳細ログページ"""
    # クラスと出席番号をクエリパラメータから取得
    class_num = request.args.get('class', type=int)
    seat_num = request.args.get('seat', type=int)
    unit = request.args.get('unit', '')
    
    if not class_num or not seat_num:
        flash('クラスと出席番号が指定されていません。', 'error')
        return redirect(url_for('teacher_logs'))
    
    # デフォルト日付を最新のログがある日付に設定
    available_dates = get_available_log_dates()
    default_date = available_dates[0]['raw'] if available_dates else datetime.now().strftime('%Y%m%d')
    selected_date = request.args.get('date', default_date)
    
    # 学習ログを読み込み
    logs = load_learning_logs(selected_date)
    
    # 該当する学生のログを抽出（クラスと出席番号で絞り込み）
    student_logs = [log for log in logs if 
                   log.get('class_num') == class_num and 
                   log.get('seat_num') == seat_num and 
                   (not unit or log.get('unit') == unit)]
    
    # 学生表示名
    student_display = f"{class_num}組{seat_num}番"
    
    if not student_logs:
        flash(f'{student_display}のログがありません。日付や単元を変更してお試しください。', 'warning')
    
    # 単元一覧を取得（フィルター用）
    all_units = list(set([log.get('unit') for log in logs if log.get('unit')]))
    
    return render_template('teacher/student_detail.html',
                         class_num=class_num,
                         seat_num=seat_num,
                         student_display=student_display,
                         unit=unit,
                         current_unit=unit,
                         current_date=selected_date,
                         logs=student_logs,
                         available_dates=available_dates,
                         units_data={unit_name: {} for unit_name in all_units},
                         teacher_id=session.get('teacher_id', 'teacher'))

if __name__ == '__main__':
    app.run(debug=True, port=5014)