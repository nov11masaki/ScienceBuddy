# Science3 サーバー管理ガイド

## 🚀 サーバーの起動・停止方法

### 方法1: スクリプトを使う（推奨）

プロジェクトフォルダ内の `start_server.sh` を使用します。

```bash
# サーバーを起動
./start_server.sh start

# サーバーを停止
./start_server.sh stop

# サーバーを再起動
./start_server.sh restart

# サーバーの状態を確認
./start_server.sh status

# ログを表示（リアルタイム）
./start_server.sh logs
```

### 方法2: 直接起動

```bash
python app.py
```

---

## 🔄 macOS起動時に自動起動する設定（オプション）

システムを起動するたびに自動的にサーバーを起動したい場合：

### 1. LaunchAgentにplistファイルをコピー

```bash
cp com.science3.flaskserver.plist ~/Library/LaunchAgents/
```

### 2. サービスを有効化

```bash
launchctl load ~/Library/LaunchAgents/com.science3.flaskserver.plist
```

### 3. サービスの管理

```bash
# サービスを開始
launchctl start com.science3.flaskserver

# サービスを停止
launchctl stop com.science3.flaskserver

# サービスを無効化（自動起動を解除）
launchctl unload ~/Library/LaunchAgents/com.science3.flaskserver.plist
```

---

## 📊 アクセス方法

サーバーが起動したら、以下のURLにアクセスできます：

- **メインページ**: http://127.0.0.1:5014
- **チャットボット**: http://127.0.0.1:5014/chatbot/login
- **教員ページ**: http://127.0.0.1:5014/teacher/login

---

## 📝 ログの確認

### スクリプト起動の場合

```bash
tail -f app.log
```

または

```bash
./start_server.sh logs
```

### LaunchAgent起動の場合

```bash
tail -f launchd.log
tail -f launchd.error.log
```

---

## 🛠️ トラブルシューティング

### サーバーが起動しない場合

1. ポート5014が使用されているか確認
```bash
lsof -i :5014
```

2. 既存のプロセスを停止
```bash
./start_server.sh stop
```

3. 再起動
```bash
./start_server.sh start
```

### ログに何も表示されない場合

Pythonのパスが正しいか確認：
```bash
which python
```

plistファイル内のPythonパスと一致させてください。

---

## 📦 必要なパッケージ

```bash
pip install -r requirements.txt
```

必須パッケージ：
- Flask
- google-generativeai
- その他（requirements.txtを参照）

---

## 🔐 セキュリティ

- このサーバーはローカル開発専用です（127.0.0.1）
- 本番環境では使用しないでください
- 外部からのアクセスを許可する場合は、適切なセキュリティ対策を講じてください

---

## 📞 サポート

問題が発生した場合は、以下を確認してください：

1. サーバーのステータス: `./start_server.sh status`
2. ログの確認: `./start_server.sh logs`
3. Pythonのバージョン: `python --version` (3.7以上推奨)
4. 必要なパッケージがインストールされているか確認
