# Gunicorn設定ファイル
import multiprocessing

# ワーカー数（CPUコア数 * 2 + 1）
workers = multiprocessing.cpu_count() * 2 + 1

# ワーカークラス（非同期処理用）
worker_class = 'sync'

# バインドアドレス（Renderが自動設定するPORTを使用）
bind = '0.0.0.0:10000'

# タイムアウト（OpenAI APIのレスポンス待ちを考慮）
timeout = 120

# ログレベル
loglevel = 'info'

# アクセスログ
accesslog = '-'
errorlog = '-'

# プロセス名
proc_name = 'sciencebuddy'

# 最大リクエスト数（メモリリーク対策）
max_requests = 1000
max_requests_jitter = 50
