# Renderへのデプロイ手順

## 準備

1. **Renderアカウント作成**
   - https://render.com にアクセス
   - GitHubアカウントでサインアップ（推奨）

2. **GitHubリポジトリの確認**
   - リポジトリ: https://github.com/nov11masaki/ScienceBuddy
   - すべての変更がpushされていることを確認

## デプロイ手順

### 方法1: Render Dashboard（推奨）

1. **Renderダッシュボードにログイン**
   - https://dashboard.render.com

2. **新しいWeb Serviceを作成**
   - 「New +」→ 「Web Service」をクリック
   - 「Connect a repository」でGitHubを選択
   - `nov11masaki/ScienceBuddy` を選択

3. **設定を入力**
   ```
   Name: sciencebuddy
   Region: Singapore (最も近いリージョン)
   Branch: main
   Runtime: Python 3
   Build Command: ./build.sh
   Start Command: gunicorn app:app -c gunicorn_config.py
   ```

4. **プランを選択**
   - Instance Type: **Free** （無料プラン）
   - Free プランの制限:
     - 750時間/月の稼働時間
     - 512MB RAM
     - アクセスがない場合、15分後にスリープ
     - スリープから復帰に30秒〜1分

5. **環境変数を設定**
   - 「Environment」タブで以下を追加:
   ```
   OPENAI_API_KEY = (あなたのOpenAI APIキーを.envファイルから取得して入力)
   FLASK_ENV = production
   ```
   
   **重要**: APIキーは `.env` ファイルに記載されているものを使用してください。

6. **デプロイ開始**
   - 「Create Web Service」をクリック
   - ビルドログが表示されます（5〜10分程度）

7. **デプロイ完了を確認**
   - ログに「Build completed successfully!」が表示される
   - 自動的にアプリが起動
   - URLが発行される: `https://sciencebuddy.onrender.com`

### 方法2: render.yaml（自動デプロイ）

1. **Blueprint を使用**
   - Render Dashboard → 「New +」→ 「Blueprint」
   - リポジトリを選択
   - `render.yaml` が自動検出される
   - 環境変数 `OPENAI_API_KEY` を設定
   - 「Apply」をクリック

## デプロイ後の確認

1. **アプリにアクセス**
   ```
   https://sciencebuddy.onrender.com
   ```

2. **動作確認項目**
   - [ ] トップページが表示される
   - [ ] クラス選択ができる
   - [ ] 出席番号選択ができる
   - [ ] 単元選択ができる
   - [ ] AI対話が動作する（予想段階）
   - [ ] 考察段階でAI対話が動作する
   - [ ] 教員ページにログインできる

3. **ログの確認**
   - Render Dashboard → 自分のサービス → 「Logs」タブ
   - エラーがないか確認

## トラブルシューティング

### ビルドエラー
```bash
# build.shの権限エラーの場合
chmod +x build.sh
git add build.sh
git commit -m "Fix build.sh permissions"
git push origin main
```

### APIエラー
- 環境変数 `OPENAI_API_KEY` が正しく設定されているか確認
- Render Dashboard → Environment で再確認

### スリープからの復帰が遅い
- 無料プランの仕様（15分未使用でスリープ）
- 有料プラン（$7/月）にアップグレードで常時稼働

### メモリ不足
- 無料プランは512MB制限
- ログに「Out of Memory」が出る場合、有料プランを検討

## 自動デプロイ設定

GitHubに push すると自動的にデプロイされます:

1. Render Dashboard → 自分のサービス → 「Settings」
2. 「Auto-Deploy」が **Yes** になっていることを確認
3. mainブランチへのpushで自動デプロイ

## カスタムドメイン設定（オプション）

1. Render Dashboard → 自分のサービス → 「Settings」
2. 「Custom Domain」セクション
3. ドメインを入力（例: sciencebuddy.example.com）
4. DNS設定でCNAMEレコードを追加

## コスト試算

### 無料プラン
- **月額**: $0
- **制限**: 
  - 750時間/月
  - 15分未使用でスリープ
  - 512MB RAM
- **適用**: テスト・デモ用

### Starterプラン（推奨）
- **月額**: $7
- **メリット**:
  - 常時稼働（スリープなし）
  - 512MB RAM
  - 自動スケーリング
- **適用**: 小規模本番環境（〜100ユーザー）

### Standardプラン
- **月額**: $25
- **メリット**:
  - 2GB RAM
  - より高速な応答
- **適用**: 中規模本番環境（100〜500ユーザー）

## モニタリング

### アクセス監視
- Render Dashboard → 自分のサービス → 「Metrics」
- CPU、メモリ、リクエスト数を確認

### エラー監視
- 「Logs」タブで随時確認
- エラーアラートはメールで通知

## バックアップ

### ログデータ
- `logs/` ディレクトリは一時的（再起動で消える）
- 重要なログはS3やGoogleドライブに定期バックアップ推奨

### 進捗データ
- `learning_progress.json` も同様
- データベース（PostgreSQL等）への移行を推奨

## 次のステップ

1. **データベース導入**
   - Render PostgreSQL（無料枠あり）
   - JSON → DB移行

2. **パフォーマンス最適化**
   - OpenAI APIのストリーミング対応
   - キャッシュ導入

3. **監視強化**
   - Sentryでエラー監視
   - Google Analyticsでアクセス解析
