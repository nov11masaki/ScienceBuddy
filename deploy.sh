#!/bin/bash
# Load environment variables
source "$(dirname "$0")/.env"

# Deploy to Cloud Run
gcloud run deploy sciencebuddy-us \
  --source . \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars OPENAI_API_KEY=${OPENAI_API_KEY},GCP_PROJECT_ID=sciencebuddy-478409,GCS_BUCKET_NAME=science-buddy-logs,FLASK_ENV=production
