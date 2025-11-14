# 本番環境セットアップガイド

## ✅ クリーンな状態でのデプロイ

本ログは新しい状態で本番環境へ移行します。

### 完了した作業

- ✅ ローカルログファイルを全削除
  - `logs/learning_log_*.json` 削除済み
  - バックアップ: `backup/logs_backup_20251114_192544.tar.gz`

- ✅ GCS/Firestore 対応を app.py に実装
  - `USE_GCS` フラグを追加
  - `USE_FIRESTORE` で環境判定

### 本番環境デプロイ手順

#### 1. 環境変数設定（Cloud Run）

Cloud Run の環境変数に以下を設定：

```
FLASK_ENV=production
OPENAI_API_KEY=sk-proj-xxxxx (既存)
GCP_PROJECT_ID=your-gcp-project-id
GCS_BUCKET_NAME=science-buddy-logs
```

#### 2. GCS バケット作成

```bash
gsutil mb -b on gs://science-buddy-logs
```

#### 3. サービスアカウント権限設定

Cloud Run のサービスアカウントに以下の権限を付与：
- `roles/storage.objectAdmin` (GCS)
- `roles/datastore.user` (Firestore)

#### 4. デプロイ

```bash
gcloud run deploy science-buddy \
  --source . \
  --platform managed \
  --region asia-northeast1 \
  --allow-unauthenticated
```

### ログの保存先

| 環境 | 保存先 | 形式 |
|-----|-------|------|
| 開発 | `logs/learning_log_YYYYMMDD.json` | JSON |
| 本番 | Firestore `learning_logs` collection + GCS `science-buddy-logs/logs/` | JSON |

### ログ削除機能（本番環境）

Teacher ページ → ログ管理 → ログ削除

- 特定日付のすべてのログを削除可能
- GCS/Firestore から自動削除

### バージョン情報

- コミット: `dd69b48` - 研究室ユーザ対応
- 前コミット: `6c9356e` - プロンプト管理統一
- ログ初期化日: 2025-11-14

---

**本番環境でクリーンなログから記録開始されます。**
