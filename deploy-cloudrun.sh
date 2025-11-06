#!/bin/bash
# Cloud Run デプロイスクリプト

set -e

# 変数設定
PROJECT_ID="sciencebuddy-project"  # あなたのGCPプロジェクトIDに変更してください
SERVICE_NAME="sciencebuddy"
REGION="asia-northeast1"  # 東京リージョン
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "=========================================="
echo "Cloud Run デプロイスクリプト"
echo "=========================================="
echo ""

# 1. プロジェクトIDの確認
echo "Step 1: プロジェクトIDを確認"
echo "現在のプロジェクトID: ${PROJECT_ID}"
read -p "このプロジェクトIDで正しいですか？ (y/n): " confirm
if [ "$confirm" != "y" ]; then
    read -p "正しいプロジェクトIDを入力してください: " PROJECT_ID
    IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"
fi
echo ""

# 2. gcloudプロジェクトを設定
echo "Step 2: gcloud プロジェクトを設定"
gcloud config set project ${PROJECT_ID}
echo ""

# 3. 必要なAPIを有効化
echo "Step 3: 必要なAPIを有効化"
gcloud services enable \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    containerregistry.googleapis.com
echo ""

# 4. Dockerイメージをビルド
echo "Step 4: Dockerイメージをビルド"
gcloud builds submit --tag ${IMAGE_NAME}
echo ""

# 5. Cloud Runにデプロイ
echo "Step 5: Cloud Runにデプロイ"
gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_NAME} \
    --platform managed \
    --region ${REGION} \
    --allow-unauthenticated \
    --memory 1Gi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 10 \
    --timeout 300 \
    --concurrency 80 \
    --port 8080
echo ""

# 6. 環境変数を設定（OPENAI_API_KEYは手動設定が必要）
echo "Step 6: 環境変数を設定"
echo "次のコマンドを実行して、OPENAI_API_KEYを設定してください:"
echo ""
echo "gcloud run services update ${SERVICE_NAME} \\"
echo "  --region ${REGION} \\"
echo "  --update-env-vars OPENAI_API_KEY=あなたのAPIキー,FLASK_ENV=production"
echo ""

# 7. デプロイ完了
echo "=========================================="
echo "デプロイ完了！"
echo "=========================================="
echo ""
echo "サービスURLを取得:"
gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format 'value(status.url)'
echo ""
echo "次のステップ:"
echo "1. 上記のコマンドでOPENAI_API_KEYを設定"
echo "2. URLにアクセスして動作確認"
echo ""
