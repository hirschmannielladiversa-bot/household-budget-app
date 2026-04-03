# Cursor実装依頼 - 家計管理アプリ

## プロジェクト概要

NotebookLM（Google Sheets）と連携した家計管理・分析Streamlitアプリ。
多角的グラフ分析 + Claudeファイナンシャルプランナーによるアドバイス機能。

**場所**: `/Volumes/tkg SSD/household-budget-app/`

---

## 完了済み（Claude Code実装分）

### Phase 1: 基盤 ✅
- プロジェクト構造作成
- `requirements.txt`
- `config/categories.yaml`（カテゴリ設定）
- `data/sample_budget.csv`（サンプルデータ3ヶ月分）

### Phase 2: コアモジュール ✅
- `modules/data_loader.py` - CSV/Excel読み込み、カテゴリ管理
- `modules/analyzer.py` - 統計分析、トレンド、異常検出
- `modules/visualizer.py` - Plotlyグラフ生成（円・棒・折れ線・ヒートマップ）

---

## 依頼タスク

### Phase 3: Streamlitアプリ 🔴 未実装
```
modules/advisor.py を先に作成してから app.py を実装
```

1. **`modules/advisor.py`** - ファイナンシャルアドバイス生成
   - ルールベース診断（理想比率との比較）
   - Claude API連携（オプション、環境変数 `ANTHROPIC_API_KEY`）
   - 節約提案、貯蓄アドバイス生成

2. **`app.py`** - メインStreamlitアプリ
   - サイドバー：ファイルアップロード、手動入力フォーム
   - メイン：グラフ表示（タブ切り替え）
   - AIアドバイス表示セクション

### Phase 4: NotebookLM連携 🔴 未実装

3. **`templates/google_sheets_template.md`**
   - 推奨Google Sheetsフォーマット説明
   - NotebookLM連携手順ガイド

---

## データ形式

```csv
日付,カテゴリ,金額,メモ
2024-03-01,食費,3500,スーパー買い物
```

**カテゴリ**: 食費, 交通費, 医療費, 通信費, 光熱費, 住居費, 保険料, 娯楽費, 教育費, 日用品, 衣服, その他

---

## 実装参考

### モジュール使用例
```python
from modules import DataLoader, BudgetAnalyzer, BudgetVisualizer, FinancialAdvisor

# データ読み込み
loader = DataLoader()
df = loader.load_csv('data/sample_budget.csv')

# 分析
analyzer = BudgetAnalyzer(df, loader.get_ideal_ratios())
summary = analyzer.statistics_summary()

# グラフ
viz = BudgetVisualizer(analyzer)
fig = viz.category_pie_chart()
```

### Streamlitの構成案
```
┌─────────────────────────────────────────┐
│  🏠 家計管理アプリ                        │
├──────────┬──────────────────────────────┤
│ サイドバー  │  メインエリア                  │
│          │                              │
│ 📁 アップ  │  [概要] [グラフ] [アドバイス]    │
│ ロード    │  ─────────────────────        │
│          │                              │
│ ✏️ 手動   │  (選択タブの内容)              │
│ 入力     │                              │
│          │                              │
│ ⚙️ 設定  │                              │
└──────────┴──────────────────────────────┘
```

---

## 起動方法

```bash
cd "/Volumes/tkg SSD/household-budget-app"
pip install -r requirements.txt
streamlit run app.py
```

---

## 注意事項

- `modules/__init__.py` でFinancialAdvisorをインポート済み（advisor.py作成必須）
- Claude API連携はオプション（なくてもルールベースで動作）
- グラフはPlotlyのインタラクティブグラフを使用

---

**依頼日**: 2024-03-07
**優先度**: Phase 3 > Phase 4
