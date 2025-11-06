#!/usr/bin/env bash
# Renderビルドスクリプト

set -o errexit

# Pythonパッケージをインストール
pip install --upgrade pip
pip install -r requirements.txt

# ログディレクトリを作成
mkdir -p logs

# 進捗管理ファイルが存在しない場合は作成
if [ ! -f learning_progress.json ]; then
    echo '{}' > learning_progress.json
fi

echo "Build completed successfully!"
