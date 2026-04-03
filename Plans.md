# Plans.md - 家計管理アプリ

## 現在のフェーズ: 開発完了 - 運用フェーズ

---

## タスク一覧

### Phase 1: 基盤構築 `cc:完了`
- [x] プロジェクトディレクトリ作成
- [x] requirements.txt作成
- [x] カテゴリ設定ファイル作成
- [x] サンプルデータ作成
- [x] CLAUDE.md作成

### Phase 2: コア機能 `cc:完了`
- [x] data_loader.py（CSV/Excel読み込み）
- [x] analyzer.py（基本統計・集計）
- [x] visualizer.py（Plotlyグラフ）

### Phase 3: Streamlitアプリ `cc:完了`
- [x] app.py メイン画面レイアウト
- [x] ファイルアップロード機能
- [x] 手動入力フォーム
- [x] グラフ表示コンポーネント

### Phase 4: AIアドバイス `cc:完了`
- [x] advisor.py（ルールベース診断）
- [x] Claude API連携
- [x] アドバイス表示UI

### Phase 5: NotebookLM連携 `cc:完了`
- [x] Google Sheetsテンプレート作成
- [x] 連携ガイドドキュメント

### Phase 6: 資産管理・税金計算 `cc:完了`
- [x] config/assets.yaml（資産・税金設定）
- [x] modules/asset_manager.py（資産CRUD・減価償却計算）
- [x] modules/tax_calculator.py（所得税・住民税・自動車税計算）
- [x] modules/asset_visualizer.py（資産・税金グラフ）
- [x] data/sample_assets.csv（サンプル資産データ）
- [x] app.py 資産管理タブ追加
- [x] app.py 税金計算タブ追加

### Phase 7: データ暗号化 `cc:完了`
- [x] modules/crypto_manager.py（PBKDF2 + Fernet暗号化）
- [x] modules/asset_manager.py 暗号化連携メソッド追加
- [x] app.py 暗号化UI（パスワード入力、保存/読込ボタン）
- [x] .gitignore（.salt, .encrypted除外）

### Phase 8: レシート自動読み取り `cc:完了`
- [x] modules/receipt_reader.py（Gemini API連携）
- [x] app.py レシート読み取りUI（画像アップロード、自動解析）
- [x] 日付・カテゴリ・金額の自動抽出

### Phase 9: 月別支出インポート `cc:完了`
- [x] modules/monthly_importer.py（横形式Excel読み込み・変換）
- [x] config/categories.yaml カテゴリマッピング設定
- [x] app.py 月別インポートUI（ファイルアップロード、プレビュー）
- [x] カテゴリ自動マッピング（コンビニ→食費、AI費→通信費等）

### Phase 10: 機能拡張・セキュリティ強化（2026-04-03 完了） `cc:完了`
- [x] 収入管理タブ追加（月別入力、口座給与自動検出、収支比較グラフ）
- [x] ローン・負債管理追加（月々/賞与月返済、引落口座指定、返済進捗）
- [x] PDF・画像取り込み拡張（全口座対応、複数ファイル一括、Gemini Vision）
- [x] カテゴリ分類改善（bank_formats.yaml最適化、起動時全件再分類）
- [x] セキュリティ強化:
  - API送信データ匿名化（金額概算化、個人名非送信）
  - エラーメッセージ汎用化（例外詳細はlogger.errorのみ）
  - CSVインジェクション対策
  - .gitignore完全化（個人データ除外）
  - HTMLエスケープ、入力検証、パスワード強度要件
- [x] 年度データ対応（年度フィルタ将来年度対応）
- [x] 生データプレビュー改善（降順表示、削除機能、検索・フィルタ）

---

## 完了したタスク

| タスク | 完了日 | 備考 |
|--------|--------|------|
| プロジェクト基盤作成 | 2026-03-07 | Phase 1完了 |
| コア機能実装 | 2026-03-07 | Phase 2完了 |
| Streamlitアプリ実装 | 2026-03-07 | Phase 3完了 |
| AIアドバイス機能 | 2026-03-07 | Phase 4完了 |
| NotebookLM連携ドキュメント | 2026-03-07 | Phase 5完了 |
| 動作確認・Plans.md更新 | 2026-03-11 | 全Phase完了確認 |
| 資産管理・税金計算機能 | 2026-03-18 | Phase 6完了 |
| データ暗号化機能 | 2026-03-18 | Phase 7完了 |
| レシート自動読み取り | 2026-03-18 | Phase 8完了 |
| 月別支出インポート | 2026-03-18 | Phase 9完了 |
| 機能拡張・セキュリティ強化 | 2026-04-03 | Phase 10完了 |

---

## 今後の拡張候補（オプション）

- [ ] 収入データの管理機能
- [ ] 予算設定の永続化
- [ ] 複数月の比較レポート機能
- [ ] データのエクスポート機能強化
- [ ] ダークモード対応

---

## メモ

- カテゴリは `config/categories.yaml` で管理
- サンプルデータは3ヶ月分（1月〜3月）
- アプリ起動: `python3 -m streamlit run app.py`
