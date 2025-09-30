# 学習進行管理システム設計

## 機能概要
- 各学習者の授業進行状況を追跡
- Unit選択時に前回の続きから自動復帰
- 学習段階（予想→実験→考察）の状態管理

## データベース構造拡張

### 学習進行状況テーブル (learning_progress)
```json
{
  "student_id": "1_11",  // クラス_番号
  "unit": "空気の温度と体積",
  "current_stage": "prediction",  // prediction, experiment, reflection, completed
  "last_access": "2025-09-30T14:30:00",
  "stage_progress": {
    "prediction": {
      "started": true,
      "conversation_count": 3,
      "summary_created": false,
      "last_message": "風船が膨らむのを見たことがある"
    },
    "experiment": {
      "started": false,
      "completed": false
    },
    "reflection": {
      "started": false,
      "conversation_count": 0,
      "summary_created": false
    }
  },
  "conversation_history": [
    // 最新の対話履歴を保存
  ]
}
```

## 実装方針

### 1. 進行状況の自動記録
- 各対話時に進行状況を更新
- 段階移行時にフラグ更新
- セッション終了時に状態保存

### 2. 自動復帰機能
- Unit選択時に進行状況をチェック
- 前回の続きから再開するかユーザーに確認
- 対話履歴の復元

### 3. 柔軟な段階管理
- 一つの段階内での中断・再開
- 段階をまたいだ長期間の学習継続
- 複数単元の並行学習対応

## UI改善
- Unit選択画面に進行状況表示
- 「前回の続きから」ボタン
- 進行度インジケーター