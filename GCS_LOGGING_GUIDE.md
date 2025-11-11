# GCS ログ確認ガイド

## 概要
ログの保存・読み込み・削除操作すべてを詳細に追跡できるようにしました。各操作は特定のログタグ付きで CloudRun ログに出力されます。

## ログタグ一覧

| タグ | 操作 | 説明 |
|------|------|------|
| `[GCS_SAVE]` | ログ保存 | 学習ログが GCS に保存される際のログ |
| `[GCS_LOAD]` | ログ読み込み | ログファイルが GCS から読み込まれる際のログ |
| `[GCS_DELETE]` | ログ削除 | 管理者がログを削除する際のログ |
| `[GCS_LIST]` | ファイル一覧 | 利用可能なログファイルを列挙する際のログ |

## CloudRun ログの確認方法

### 方法 1: Google Cloud Console（簡単）

1. [Google Cloud Console](https://console.cloud.google.com) を開く
2. 「Cloud Run」を選択
3. 「sciencebuddy」サービスをクリック
4. 左パネルから「ログ」をクリック
5. ログを検索するには、画面上部のフィルターを使用

### 方法 2: gcloud CLI（詳細な検索）

```bash
# 最新の 50 件のログを表示
gcloud logging read "resource.type=cloud_run_revision" \
  --limit=50 \
  --format='value(timestamp,severity,jsonPayload.message)'

# GCS_SAVE ログのみを表示
gcloud logging read "resource.type=cloud_run_revision AND textPayload=~'GCS_SAVE'" \
  --limit=30 \
  --format=json

# GCS_DELETE ログのみを表示（削除操作の追跡）
gcloud logging read "resource.type=cloud_run_revision AND textPayload=~'GCS_DELETE'" \
  --limit=30 \
  --format=json

# エラーログのみを表示
gcloud logging read "resource.type=cloud_run_revision AND severity=ERROR" \
  --limit=30 \
  --format=json
```

## ログの追跡フロー

### ログ保存時の流れ

```
[GCS_SAVE] START - blob: logs/learning_log_20251111.json, class: 1組3番, unit: 金属のあたたまり方, type: prediction_chat
[GCS_SAVE] LOAD_SUCCESS - loaded 5 existing logs
[GCS_SAVE] APPEND - new log added, total: 6
[GCS_SAVE] SUCCESS - saved 6 logs to GCS
```

### ログ読み込み時の流れ

```
[GCS_LOAD] START - blob: logs/learning_log_20251111.json
[GCS_LOAD] SUCCESS - loaded 6 logs
```

### ログ削除時の流れ（正常系）

```
[GCS_DELETE] START - teacher: teacher001
[GCS_DELETE] PARAMS - class: 1, seat: 3, unit: '金属のあたたまり方', date: '20251111'
[GCS_DELETE] LOAD - loading logs from date: 20251111
  [GCS_LOAD] START - blob: logs/learning_log_20251111.json
  [GCS_LOAD] SUCCESS - loaded 6 logs
[GCS_DELETE] LOAD_RESULT - loaded 6 logs
[GCS_DELETE] FILTERED - deleted: 2, remaining: 4
[GCS_DELETE] SAVE_START - blob: logs/learning_log_20251111.json, logs: 4
[GCS_DELETE] SAVE_SUCCESS - updated file with 4 logs remaining
[GCS_DELETE] SUCCESS - deleted 2 logs
```

### ログ削除時の流れ（エラー系）

```
[GCS_DELETE] START - teacher: teacher001
[GCS_DELETE] PARAMS - class: 1, seat: 3, unit: '金属のあたたまり方', date: '20251111'
[GCS_DELETE] VALIDATION_FAILED - 削除に必要な情報が不足しています
```

または

```
[GCS_DELETE] SAVE_ERROR - GCS エラー: PermissionDenied - Insufficient Permission
[GCS_DELETE] FATAL_ERROR - 403 Forbidden: Access Denied
```

## トラブルシューティング

### 削除エラーが発生した場合

1. **CloudRun ログを確認**
   ```bash
   gcloud logging read "resource.type=cloud_run_revision AND textPayload=~'GCS_DELETE.*ERROR'" \
     --limit=10 \
     --format=json | jq '.[] | {timestamp, textPayload}'
   ```

2. **エラーの原因を特定**
   - `403 Forbidden` → GCS 権限不足
   - `404 Not Found` → ファイルが存在しない
   - `500 Internal Server Error` → サーバー側エラー

3. **ブラウザの開発者ツールを確認**
   - F12 を押して「コンソール」タブを開く
   - 削除ボタンをクリック
   - アラート内容を確認

### ログが保存されていない場合

1. **ログファイルが作成されているか確認**
   ```bash
   # GCS バケット内のログファイルを列挙
   gsutil ls gs://your-bucket-name/logs/
   ```

2. **ファイルの内容を確認**
   ```bash
   # 最新のログファイルを確認
   gsutil cat gs://your-bucket-name/logs/learning_log_20251111.json | jq '.'
   ```

3. **CloudRun ログで保存操作を確認**
   ```bash
   gcloud logging read "resource.type=cloud_run_revision AND textPayload=~'GCS_SAVE'" \
     --limit=10 --format=json | jq '.[] | {timestamp, textPayload}'
   ```

## リアルタイムログ監視

ログをリアルタイムで監視したい場合：

```bash
# ターミナルで以下コマンドを実行し、保ったままにしておく
gcloud logging read "resource.type=cloud_run_revision" \
  --follow \
  --format='value(timestamp,textPayload)' \
  --limit=0
```

その後、ブラウザで削除ボタンをクリックすると、リアルタイムでログが表示されます。

## ログの読み取り権限確認

CloudRun サービスが GCS に対して適切な権限を持っているか確認：

```bash
# サービスアカウントを確認
gcloud run services describe sciencebuddy --region asia-northeast1 --format='value(serviceConfig.serviceAccountEmail)'

# 結果例: sciencebuddy@sciencebuddy-382384155895.iam.gserviceaccount.com

# そのアカウントの GCS 権限を確認
gcloud projects get-iam-policy sciencebuddy-382384155895 \
  --flatten="bindings[].members" \
  --filter="bindings.members:sciencebuddy@sciencebuddy-382384155895.iam.gserviceaccount.com" \
  --format='table(bindings.role)'
```

期待される権限:
- `roles/storage.objectAdmin` または
- `roles/storage.objectCreator` + `roles/storage.objectViewer`

## コミット情報

- **最新コミット**: `1270db9` - "Add comprehensive GCS logging - track save, load, delete operations"
- **実装内容**:
  - `[GCS_SAVE]` タグでログ保存の追跡
  - `[GCS_LOAD]` タグでログ読み込みの追跡
  - `[GCS_DELETE]` タグでログ削除の追跡
  - `[GCS_LIST]` タグでファイル一覧の追跡
  - エラー時の詳細なスタックトレース出力
