# デプロイメントガイド

## 本番環境へのデプロイ方法

### 1. 環境変数の設定

本番環境（Google Cloud Run）にデプロイする際は、以下の環境変数を設定してください。

| 環境変数 | 説明 | 例 |
|---------|------|-----|
| `FLASK_ENV` | Flask環境フラグ | `production` |
| `GCP_PROJECT_ID` | GCPプロジェクトID | `sciencebuddy-478409` |
| `GCS_BUCKET_NAME` | Google Cloud Storageバケット名 | `science-buddy-logs` |
| `OPENAI_API_KEY` | OpenAI APIキー | `sk-...` |

---

### 2. 本番環境デプロイコマンド

#### 方法1: gcloud CLI を使用（推奨）

```bash
# GCPプロジェクトに接続
gcloud auth login
gcloud config set project sciencebuddy-478409

# Cloud Run にデプロイ
gcloud run deploy science-buddy \
  --source . \
  --platform managed \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --set-env-vars \
    FLASK_ENV=production,\
    GCP_PROJECT_ID=sciencebuddy-478409,\
    GCS_BUCKET_NAME=science-buddy-logs,\
    OPENAI_API_KEY=sk-XXXXXXXXXXXXX
```

#### 方法2: Cloud Build を使用

```bash
# Dockerfile をビルド
gcloud builds submit --tag gcr.io/sciencebuddy-478409/science-buddy

# Cloud Run にデプロイ
gcloud run deploy science-buddy \
  --image gcr.io/sciencebuddy-478409/science-buddy \
  --platform managed \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --set-env-vars \
    FLASK_ENV=production,\
    GCP_PROJECT_ID=sciencebuddy-478409,\
    GCS_BUCKET_NAME=science-buddy-logs,\
    OPENAI_API_KEY=sk-XXXXXXXXXXXXX
```

---

### 3. ローカルで本番環境動作をテストする

本番環境にデプロイする前に、ローカルで本番環境の動作をテストできます。

```bash
# 環境変数を設定
export FLASK_ENV=production
export GCP_PROJECT_ID=sciencebuddy-478409
export GCS_BUCKET_NAME=science-buddy-logs
export OPENAI_API_KEY=sk-XXXXXXXXXXXXX

# ローカルサーバーを起動
python app.py

# ブラウザで確認
open http://localhost:5014
```

**注意**: 本番環境テスト時は、FirestoreとGoogle Cloud Storageに実際にアクセスします。

---

### 4. 本番環境での動作確認ポイント

本番環境にデプロイ後、以下を確認してください：

#### ✅ 学習ログ保存の確認

```bash
# Firestore に保存されているか確認
gcloud firestore documents list --collection-id=learning_logs
```

#### ✅ 警告ダイアログの表示

- 予想をやり直す場合に「予想をやり直しますか？」と表示
- 考察から戻る場合に「考察をまとめていません」と表示

#### ✅ 音声入力機能

- マイクボタンをクリック
- 音声入力が正常に機能するか確認

#### ✅ 会話履歴の非復帰

本番環境では、ページをリロードしても**前回の会話履歴は表示されません**。これは仕様です。

- 学習ログとしては記録される
- 進捗状況は保存される
- 新規セッション開始時に会話履歴は初期化される

---

### 5. 環境ごとの動作差

| 機能 | ローカル環境 | 本番環境 |
|-----|-------------|--------|
| **会話履歴保存** | ローカルJSONファイル | Firestore |
| **ログファイル** | `logs/` フォルダ | Google Cloud Storage |
| **会話復帰** | ✅ ページリロード時に復帰 | ❌ 新規セッション開始 |
| **学習ログ記録** | ✅ 記録される | ✅ 記録される |
| **進捗管理** | ✅ 管理される | ✅ 管理される |
| **警告ダイアログ** | ✅ 表示される | ✅ 表示される |
| **音声入力** | ✅ 使用可能 | ✅ 使用可能 |

---

### 6. トラブルシューティング

#### ❌ エラー: `FLASK_ENV is not set`

```bash
# 環境変数が設定されていない
# Cloud Run の環境変数タブで確認
gcloud run services describe science-buddy --platform managed
```

#### ❌ エラー: `Firestore connection failed`

```bash
# Firestore にアクセスできない
# GCPプロジェクトで Firestore が有効になっているか確認
gcloud firestore databases list
```

#### ❌ エラー: `GCS bucket not found`

```bash
# バケットが存在するか確認
gsutil ls gs://science-buddy-logs
```

#### ❌ 音声入力が機能しない

- ブラウザが `https://` でアクセスされているか確認
- Web Speech API は `https://` または `localhost` でのみ動作

---

### 7. デプロイ後のモニタリング

```bash
# ログを確認
gcloud run logs read science-buddy --platform managed --region asia-northeast1

# リアルタイムログを確認
gcloud run logs read science-buddy --tail --platform managed --region asia-northeast1
```

---

### 8. ロールバック方法

前のバージョンにロールバックする場合：

```bash
# 過去のリビジョン一覧
gcloud run revisions list --service=science-buddy --platform managed --region asia-northeast1

# 特定のリビジョンをトラフィック指定
gcloud run traffic-split science-buddy \
  --to-revisions=REVISION_NAME=100 \
  --platform managed \
  --region asia-northeast1
```

---

## まとめ

本番環境では以下が自動的に機能します：

✅ **学習ログ保存** - Firestore に記録  
✅ **進捗管理** - Firestore で管理  
✅ **警告ダイアログ** - ブラウザ標準機能  
✅ **音声入力** - Web Speech API  
❌ **会話履歴復帰** - 本番環境では無効（新規セッション開始）

これにより、本番環境での学習ログ記録とローカル環境での開発効率のバランスが取れます。
