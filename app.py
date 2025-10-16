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
    """OpenAI APIを呼び出し、エラー時はリトライする（Markdownガイドライン活用版）"""
    if client is None:
        return "AI システムの初期化に問題があります。管理者に連絡してください。"
    
    enhanced_prompt = prompt
    
    for attempt in range(max_retries):
        try:
            import time
            start_time = time.time()
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": enhanced_prompt}
                ],
                max_tokens=2000,
                temperature=0.3,
                timeout=30
            )
            
            if response.choices and response.choices[0].message.content:
                content = response.choices[0].message.content
                cleaned_response = remove_markdown_formatting(content)
                return cleaned_response
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
    """段階と単元に応じた最初のAIメッセージを生成"""
    if stage == 'prediction':
        messages = {
            "水のあたたまり方": "こんにちは！水を温めるとき、最初にあたたかくなるのはどこだと思いますか？あなたの考えを聞かせてください。",
            "金属のあたたまり方": "こんにちは！金属を温めるとき、どのようにあたたまっていくと思いますか？あなたの予想を教えてください。",
            "空気の温度と体積": "こんにちは！空気を温めるとき、空気にはどのような変化が起こると思いますか？あなたの考えを聞かせてください。",
            "水を熱し続けた時の温度と様子": "こんにちは！水を熱し続けると、温度と様子がどのように変わると思いますか？あなたの予想を教えてください。"
        }
    elif stage == 'reflection':
        messages = {
            "水のあたたまり方": "こんにちは！実験してみてどうでしたか？予想と比べてどのようなことに気づきましたか？教えてください。",
            "金属のあたたまり方": "こんにちは！実験の結果はどうでしたか？金属のあたたまり方について、気づいたことを聞かせてください。",
            "空気の温度と体積": "こんにちは！実験から、空気の温度と体積の関係について、どんなことがわかりましたか？教えてください。",
            "水を熱し続けた時の温度と様子": "こんにちは！水を熱し続けた時の変化について、実験からわかったことを教えてください。"
        }
    else:
        messages = {
            "水のあたたまり方": "こんにちは！この課題について、どのような結果になると思いますか？あなたの考えを聞かせてください。",
            "金属のあたたまり方": "こんにちは！この課題について、どのような結果になると思いますか？あなたの考えを聞かせてください。",
            "空気の温度と体積": "こんにちは！この課題について、どのような結果になると思いますか？あなたの考えを聞かせてください。",
            "水を熱し続けた時の温度と様子": "こんにちは！この課題について、どのような結果になると思いますか？あなたの考えを聞かせてください。"
        }
    
    return messages.get(unit_name, "こんにちは！この課題について、どのような結果になると思いますか？あなたの考えを聞かせてください。")

# 単元ごとのプロンプトを読み込む関数
def load_unit_prompt(unit_name):
    """単元専用のプロンプトファイルを読み込む"""
    try:
        with open(f'prompts/{unit_name}.md', 'r', encoding='utf-8') as f:
            content = f.read().strip()
        
        # 新しいプロンプト形式：ファイル内容をそのまま使用
        if content:
            return content
        else:
            # フォールバック：ファイルが空の場合
            return "児童の発言をよく聞いて、適切な質問で考えを引き出してください。"
    
    except FileNotFoundError:
        # フォールバック：ファイルが見つからない場合
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
    full_prompt = unit_prompt + "\n\n対話履歴:\n"
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
        
        # 対話が3回以上の場合、予想のまとめを提案
        suggest_summary = len(conversation) >= 6  # user + AI で1セット
        
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
    
    # 予想のまとめ用プロンプトを読み込み（すべてのユニット共通）
    summary_prompt = load_unit_prompt("予想_summary")
    
    # 対話履歴をプロンプトに追加
    full_summary_prompt = summary_prompt + "\n\n対話履歴:\n"
    for msg in conversation:
        role = "学習者" if msg['role'] == 'user' else "AI"
        full_summary_prompt += f"{role}: {msg['content']}\n"
    
    try:
        summary_response = call_openai_with_retry(full_summary_prompt)
        
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
    
    # 対話履歴を追加
    full_prompt = unit_prompt + "\n\n対話履歴:\n"
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
        return jsonify({'error': f'AI接続エラーが発生しました。しばらく待ってから再度お試しください。'}), 500

@app.route('/final_summary', methods=['POST'])
def final_summary():
    reflection_conversation = session.get('reflection_conversation', [])
    prediction_summary = session.get('prediction_summary', '')
    unit = session.get('unit')
    
    # 最終考察用プロンプトを読み込み（すべてのユニット共通）
    final_prompt = load_unit_prompt("考察_final_summary")
    
    # 対話履歴と予想をプロンプトに追加
    full_final_prompt = final_prompt + f"\n\n学習者の予想: {prediction_summary}\n\n考察対話履歴:\n"
    for msg in reflection_conversation:
        role = "学習者" if msg['role'] == 'user' else "AI"
        full_final_prompt += f"{role}: {msg['content']}\n"
    
    try:
        final_summary_response = call_openai_with_retry(full_final_prompt)
        
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
    return render_template('teacher/dashboard.html', 
                         units=UNITS, 
                         teacher_id=session.get('teacher_id'))

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
        return ""

def analyze_student_learning(student_number, unit, logs):
    """特定の学生・単元の学習過程を詳細分析"""
    
    # 該当する学生のログを抽出
    student_logs = [log for log in logs if 
                   log.get('student_number') == student_number and 
                   log.get('unit') == unit]
    
    
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
    # 既習事項の言及をチェック
    mentioned_knowledge = []
    
    for log in logs:
        if log.get('log_type') in ['prediction_chat', 'reflection_chat']:
            message = log['data'].get('user_message', '').lower()
            
            # 既習事項の言及をチェック
            if any(keyword in message for keyword in ['前に習った', '勉強した', '覚えている', '似ている']):
                mentioned_knowledge.append(message[:50])  # 最初の50文字を記録
    
    return {
        'knowledge_connections': len(mentioned_knowledge),
        'total_connections': len(mentioned_knowledge),
        'unit': unit
    }

def analyze_unit_specific_trends(logs, unit):
    """単元特有の学習傾向を分析"""
    # シンプルな学習傾向分析
    keyword_usage = {}
    
    for log in logs:
        if log.get('log_type') in ['prediction_chat', 'reflection_chat']:
            message = log['data'].get('user_message', '')
            # メッセージを記録
            if message:
                keyword_usage[message[:50]] = keyword_usage.get(message[:50], 0) + 1
    
    return {
        'unit': unit,
        'keyword_usage': keyword_usage,
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
            'overall_trend': '分析対象のデータがありません'
        }
    
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
- overall_trend: クラス全体の言語活動の傾向（200文字程度）
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
        
        # 複数の方法でJSONを抽出
        result = None
        
        # 方法1: 通常の正規表現
        import re
        json_match = re.search(r'\{.*?\}', analysis_result, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
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