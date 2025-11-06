# Python 3.9イメージを使用
FROM python:3.9-slim

# 作業ディレクトリを設定
WORKDIR /app

# 必要なシステムパッケージをインストール
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 依存関係ファイルをコピー
COPY requirements.txt .

# Pythonパッケージをインストール
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションファイルをコピー
COPY . .

# ログディレクトリを作成
RUN mkdir -p logs

# 進捗管理ファイルが存在しない場合は作成
RUN if [ ! -f learning_progress.json ]; then echo '{}' > learning_progress.json; fi

# ポート番号を環境変数から取得（Cloud Runのデフォルトは8080）
ENV PORT=8080

# 本番環境フラグ
ENV FLASK_ENV=production

# gunicornでアプリケーションを起動（JSON形式でOSシグナルを適切に処理）
CMD ["sh", "-c", "exec gunicorn --bind :$PORT --workers 2 --threads 4 --timeout 120 app:app"]
