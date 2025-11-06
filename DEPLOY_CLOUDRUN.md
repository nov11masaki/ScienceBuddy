# Google Cloud Run デプロイ完全ガイド

## 📋 目次
1. [事前準備](#事前準備)
2. [初回デプロイ（手動）](#初回デプロイ手動)
3. [環境変数の設定](#環境変数の設定)
4. [テスト方法](#テスト方法)
5. [自動デプロイ設定（CI/CD）](#自動デプロイ設定cicd)
6. [コスト試算](#コスト試算)
7. [運用・監視](#運用監視)
8. [トラブルシューティング](#トラブルシューティング)

---

## 🎯 事前準備

### 1. Google Cloudアカウント作成
```
1. https://cloud.google.com にアクセス
2. 「無料で開始」をクリック
3. Googleアカウントでログイン
4. クレジットカード情報を登録（無料枠あり）
   - 初回 $300 クレジット付与（90日間有効）
```

### 2. Google Cloud SDK（gcloud）のインストール

#### macOS
```bash
# Homebrewでインストール
brew install --cask google-cloud-sdk

# インストール確認
gcloud version

# 初期化
gcloud init
```

#### インストール後の設定
```bash
# Googleアカウントでログイン
gcloud auth login

# プロジェクトIDを設定（後で作成します）
gcloud config set project YOUR_PROJECT_ID
```

### 3. Google Cloud プロジェクト作成

```bash
# プロジェクトIDを決める（全世界で一意）
# 例: sciencebuddy-2025, sciencebuddy-masaki など
PROJECT_ID="sciencebuddy-あなたの名前"

# プロジェクトを作成
gcloud projects create $PROJECT_ID --name="ScienceBuddy"

# プロジェクトを設定
gcloud config set project $PROJECT_ID

# 請求先アカウントを確認
gcloud billing accounts list

# 請求先を設定（BILLING_ACCOUNT_IDは上記コマンドで確認）
gcloud billing projects link $PROJECT_ID --billing-account=BILLING_ACCOUNT_ID
```

### 4. 必要なAPIを有効化

```bash
# Cloud Run, Cloud Build, Container Registryを有効化
gcloud services enable \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    containerregistry.googleapis.com
```

---

## 🚀 初回デプロイ（手動）

### 方法1: 自動スクリプト使用（推奨）

```bash
# リポジトリのディレクトリに移動
cd /path/to/science3

# デプロイスクリプトを実行
./deploy-cloudrun.sh
```

### 方法2: 手動コマンド実行

#### Step 1: Dockerイメージをビルド＆プッシュ

```bash
# プロジェクトIDを設定
PROJECT_ID="your-project-id"
SERVICE_NAME="sciencebuddy"
REGION="asia-northeast1"  # 東京リージョン

# Cloud Buildでイメージをビルド
gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME
```

#### Step 2: Cloud Runにデプロイ

```bash
gcloud run deploy $SERVICE_NAME \
    --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --memory 1Gi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 10 \
    --timeout 300 \
    --concurrency 80 \
    --port 8080
```

#### パラメータ説明:
- `--memory 1Gi`: メモリ1GB（27人対応に十分）
- `--cpu 1`: vCPU 1コア
- `--min-instances 0`: 未使用時はインスタンス0（コスト削減）
- `--max-instances 10`: 最大10インスタンス（負荷分散）
- `--timeout 300`: タイムアウト5分（OpenAI API待ちを考慮）
- `--concurrency 80`: 1インスタンスあたり80リクエストまで同時処理
- `--allow-unauthenticated`: 公開アクセス可能

---

## 🔐 環境変数の設定

### OPENAI_API_KEYの設定

```bash
# .envファイルからAPIキーを取得
cat .env

# 環境変数を設定
gcloud run services update sciencebuddy \
    --region asia-northeast1 \
    --update-env-vars OPENAI_API_KEY=あなたのAPIキー,FLASK_ENV=production
```

### Secret Managerを使用（推奨・セキュア）

```bash
# Secret Managerを有効化
gcloud services enable secretmanager.googleapis.com

# シークレットを作成
echo -n "あなたのAPIキー" | gcloud secrets create openai-api-key --data-file=-

# Cloud Runサービスにシークレットへのアクセス権を付与
gcloud secrets add-iam-policy-binding openai-api-key \
    --member=serviceAccount:$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')-compute@developer.gserviceaccount.com \
    --role=roles/secretmanager.secretAccessor

# Cloud Runでシークレットを環境変数として使用
gcloud run services update sciencebuddy \
    --region asia-northeast1 \
    --update-secrets OPENAI_API_KEY=openai-api-key:latest \
    --update-env-vars FLASK_ENV=production
```

---

## 🧪 テスト方法

### 1. サービスURLの取得

```bash
# URLを取得
gcloud run services describe sciencebuddy \
    --region asia-northeast1 \
    --format 'value(status.url)'

# 例: https://sciencebuddy-xxxxx-an.a.run.app
```

### 2. 基本動作確認

```bash
# ブラウザでアクセス
open $(gcloud run services describe sciencebuddy --region asia-northeast1 --format 'value(status.url)')

# またはcurlでテスト
SERVICE_URL=$(gcloud run services describe sciencebuddy --region asia-northeast1 --format 'value(status.url)')
curl $SERVICE_URL
```

### 3. 負荷テスト（27人同時接続シミュレーション）

#### Apache Benchを使用

```bash
# Apache Benchをインストール（macOS）
brew install httpd

# 27人同時接続、合計270リクエストでテスト
ab -n 270 -c 27 -t 60 $SERVICE_URL/

# 結果の見方:
# - Requests per second: 1秒あたりの処理数
# - Time per request: 平均応答時間（ms）
# - Failed requests: 失敗したリクエスト数（0が理想）
```

#### Locustを使用（より高度）

```bash
# Locustをインストール
pip install locust

# locustfile.pyを作成
cat > locustfile.py << 'EOF'
from locust import HttpUser, task, between

class ScienceBuddyUser(HttpUser):
    wait_time = between(1, 5)
    
    @task
    def index(self):
        self.client.get("/")
    
    @task(3)
    def select_unit(self):
        self.client.get("/select_unit?class=1&number=1")
    
    @task(2)
    def prediction(self):
        self.client.get("/prediction?class=1&number=1&unit=空気の温度と体積")
EOF

# Locustを起動
locust --host=$SERVICE_URL

# ブラウザで http://localhost:8089 にアクセス
# Number of users: 27
# Spawn rate: 5
# で開始してテスト
```

### 4. AI応答テスト

```bash
# チャットAPIをテスト
curl -X POST $SERVICE_URL/chat \
    -H "Content-Type: application/json" \
    -d '{"message":"空気をあたためるとどうなると思いますか？"}'

# 期待される応答: AIの返答がJSON形式で返る
```

---

## 🔄 自動デプロイ設定（CI/CD）

### GitHub Actionsを使用

#### Step 1: Cloud Build トリガーを作成

```bash
# Cloud Build トリガーを作成
gcloud builds triggers create github \
    --repo-name=ScienceBuddy \
    --repo-owner=nov11masaki \
    --branch-pattern="^main$" \
    --build-config=cloudbuild.yaml
```

#### Step 2: GitHub Actionsワークフローを作成

`.github/workflows/deploy.yml` を作成:

```yaml
name: Deploy to Cloud Run

on:
  push:
    branches:
      - main

env:
  PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}
  SERVICE_NAME: sciencebuddy
  REGION: asia-northeast1

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout
        uses: actions/checkout@v3
      
      - name: Setup Cloud SDK
        uses: google-github-actions/setup-gcloud@v1
        with:
          service_account_key: ${{ secrets.GCP_SA_KEY }}
          project_id: ${{ secrets.GCP_PROJECT_ID }}
      
      - name: Configure Docker
        run: gcloud auth configure-docker
      
      - name: Build and Push
        run: |
          gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME
      
      - name: Deploy to Cloud Run
        run: |
          gcloud run deploy $SERVICE_NAME \
            --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
            --region $REGION \
            --platform managed \
            --allow-unauthenticated
```

#### Step 3: GitHub Secretsを設定

1. サービスアカウントキーを作成:
```bash
gcloud iam service-accounts create github-actions \
    --display-name="GitHub Actions"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/run.admin" \
    --role="roles/storage.admin" \
    --role="roles/iam.serviceAccountUser"

gcloud iam service-accounts keys create key.json \
    --iam-account=github-actions@$PROJECT_ID.iam.gserviceaccount.com
```

2. GitHubリポジトリの Settings → Secrets で以下を追加:
   - `GCP_PROJECT_ID`: プロジェクトID
   - `GCP_SA_KEY`: key.jsonの内容

---

## 💰 コスト試算

### 無料枠（毎月リセット）
```
- CPU: 180,000 vCPU秒/月
- メモリ: 360,000 GiB秒/月
- リクエスト: 200万リクエスト/月
- ネットワーク: 1GB 送信/月
```

### あなたのケースでのコスト試算

#### 前提条件
```
- 総授業時間: 32時間/月
- 同時接続: 最大27人
- 設定: 1GB メモリ, 1 vCPU
- リクエスト数: 約10,000リクエスト/月
```

#### 計算

##### CPU時間
```
1 vCPU × 32時間 × 3600秒 = 115,200 vCPU秒
無料枠: 180,000 vCPU秒
→ 無料枠内 ✅
```

##### メモリ使用
```
1 GiB × 32時間 × 3600秒 = 115,200 GiB秒
無料枠: 360,000 GiB秒
→ 無料枠内 ✅
```

##### リクエスト数
```
約10,000リクエスト/月
無料枠: 200万リクエスト
→ 無料枠内 ✅
```

**結果: ほぼ無料で運用可能！** 🎉

実際のコスト: **約 $0-2/月（0-280円）**

---

## 📊 運用・監視

### ログの確認

```bash
# リアルタイムログを表示
gcloud run services logs tail sciencebuddy --region asia-northeast1

# 最近のログを表示
gcloud run services logs read sciencebuddy --region asia-northeast1 --limit 50
```

### メトリクスの確認

```bash
# Cloud Consoleで確認（推奨）
# https://console.cloud.google.com/run

# または
gcloud run services describe sciencebuddy \
    --region asia-northeast1 \
    --format yaml
```

### アラート設定

Cloud Console → Monitoring → Alerting でアラートを設定:
- エラー率が5%を超えた場合
- レスポンス時間が3秒を超えた場合
- メモリ使用率が90%を超えた場合

---

## 🔧 トラブルシューティング

### ビルドエラー

```bash
# ログを確認
gcloud builds list --limit 5
gcloud builds log [BUILD_ID]
```

### デプロイエラー

```bash
# サービスの詳細を確認
gcloud run services describe sciencebuddy --region asia-northeast1

# イベントログを確認
gcloud run services logs read sciencebuddy --region asia-northeast1
```

### APIキーエラー

```bash
# 環境変数を確認
gcloud run services describe sciencebuddy --region asia-northeast1 --format="value(spec.template.spec.containers[0].env)"

# 再設定
gcloud run services update sciencebuddy \
    --region asia-northeast1 \
    --update-env-vars OPENAI_API_KEY=新しいキー
```

### パフォーマンス問題

```bash
# インスタンス数を増やす
gcloud run services update sciencebuddy \
    --region asia-northeast1 \
    --max-instances 20

# メモリを増やす
gcloud run services update sciencebuddy \
    --region asia-northeast1 \
    --memory 2Gi

# CPUを増やす
gcloud run services update sciencebuddy \
    --region asia-northeast1 \
    --cpu 2
```

---

## 📋 チェックリスト

### デプロイ前
- [ ] Google Cloudアカウント作成
- [ ] gcloud CLIインストール
- [ ] プロジェクト作成
- [ ] APIを有効化
- [ ] .envファイルにAPIキー設定

### デプロイ
- [ ] Dockerイメージビルド成功
- [ ] Cloud Runデプロイ成功
- [ ] 環境変数設定完了
- [ ] URLアクセス可能

### テスト
- [ ] トップページ表示
- [ ] クラス選択動作
- [ ] AI対話動作
- [ ] 負荷テスト実施（27人同時接続）
- [ ] レスポンス時間確認（3秒以内）

### 本番運用
- [ ] カスタムドメイン設定（オプション）
- [ ] ログ監視設定
- [ ] アラート設定
- [ ] バックアップ設定

---

## 🎓 次のステップ

1. **データベース導入**
   - Cloud SQL（PostgreSQL）を追加
   - JSONファイル → データベース移行

2. **CDN設定**
   - Cloud CDNで静的ファイル配信を高速化

3. **カスタムドメイン**
   - 独自ドメインの設定

4. **監視強化**
   - Cloud Monitoringで詳細監視
   - Error Reportingでエラー追跡

---

## 📞 サポート

### ドキュメント
- Cloud Run公式: https://cloud.google.com/run/docs
- gcloud CLI: https://cloud.google.com/sdk/gcloud/reference

### コミュニティ
- Stack Overflow: `[google-cloud-run]` タグ
- Google Cloud Community: https://www.googlecloudcommunity.com/

---

**作成日**: 2025年11月6日  
**対象プロジェクト**: ScienceBuddy  
**環境**: Google Cloud Run
