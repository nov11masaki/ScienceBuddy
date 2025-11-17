# Python 3.9スリムイメージを使用
FROM python:3.9-slim

# 作業ディレクトリを設定
WORKDIR /app

# システムパッケージの更新とインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 依存関係ファイルをコピーしてインストール
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# アプリケーションファイルをコピー
COPY . .

# ログディレクトリを作成
RUN mkdir -p logs

# 本番環境用ユーザーを作成（セキュリティ向上）
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# ポート番号を環境変数から取得（Cloud Runのデフォルトは8080）
ENV PORT=8080
ENV FLASK_ENV=production

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/ || exit 1

# gunicornでアプリケーションを起動
CMD exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 2 --worker-class gthread --timeout 60 --access-logfile - --error-logfile - app:app
