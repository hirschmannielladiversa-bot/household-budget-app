# 🏠 家計管理ダッシュボード

NotebookLM（Google Sheets）連携を想定した家計管理・分析アプリケーション。
Streamlitベースのダッシュボードで、多角的なグラフ分析とAIアドバイス機能を提供。

**Version 2.6.0**

## 特徴

- **完全ローカル動作** — APIキーなしで全コア機能が使えます
- **AIアドバイス（オプション）** — Claude / Gemini APIで家計診断
- **銀行CSV / PDF / 画像取り込み** — 三菱UFJ、楽天銀行、ろうきん等に対応
- **収入管理** — 月別入力 + 口座からの給与自動検出
- **ローン・負債管理** — 月々/賞与月返済、引落口座指定
- **セキュリティ** — API送信データ匿名化、入力検証、暗号化保存

## クイックスタート

### 方法1: ダブルクリック（推奨）

`開始はこのフォルダ/家計アプリ起動.command` をダブルクリックするだけ。

> 初回に「開発元が未確認」と表示された場合:
> ファイルを右クリック → 「開く」 → 「開く」

### 方法2: ターミナル

```bash
pip install -r requirements.txt
python3 -m streamlit run app.py
```

## プロジェクト構成

```
household-budget-app/
├── 開始はこのフォルダ/               # ★ まずここを開く
│   ├── 家計アプリ起動.command        # ダブルクリック起動
│   ├── はじめにお読みください.md      # 使い方の概要
│   ├── 使い方ガイド.html             # 詳しい操作説明
│   ├── 開発ログ.html                # 開発の経緯
│   └── Excelのデータ例.xlsx          # 取り込み用サンプルExcel
├── app.py                          # メインアプリ
├── requirements.txt                # 依存関係
├── config/
│   ├── categories.yaml             # カテゴリ設定
│   ├── bank_formats.yaml           # 銀行CSV/分類パターン
│   └── assets.yaml                 # 資産・税金設定
├── data/
│   ├── sample_budget.csv           # サンプル支出データ
│   └── sample_assets.csv           # サンプル資産データ
├── modules/
│   ├── data_loader.py              # データ読み込み
│   ├── analyzer.py                 # 分析ロジック
│   ├── visualizer.py               # グラフ生成
│   ├── advisor.py                  # AIアドバイス
│   ├── bank_manager.py             # 口座・取引管理
│   ├── asset_manager.py            # 資産管理
│   ├── asset_visualizer.py         # 資産グラフ
│   ├── tax_calculator.py           # 税金計算
│   ├── year_end_adjustment.py      # 年末調整
│   ├── crypto_manager.py           # データ暗号化
│   ├── receipt_reader.py           # レシート読み取り
│   ├── google_sheets_loader.py     # Google Sheets連携
│   ├── monthly_importer.py         # 月別支出インポート
│   └── gemini_utils.py             # Gemini APIリトライ
└── VERSION
```

## タブ構成

| タブ | 機能 |
|------|------|
| 📋 概要 | 収支サマリー、カテゴリ円グラフ |
| 📈 グラフ | 月別推移、トレンド、ダッシュボード |
| 💰 収入管理 | 月別収入入力、口座連携、収支比較グラフ |
| 🧭 アドバイス | AI家計診断、チャット相談 |
| 🏦 資産管理 | 預貯金・金融資産・保険・ローン |
| 💴 税金・年末調整 | 所得税/住民税計算、ふるさと納税 |
| 💳 口座管理 | CSV/PDF/画像取り込み、取引履歴 |
| 📄 データ一覧 | 全データの検索・編集・削除 |

## API設定（オプション）

| API | 用途 | 取得先 |
|-----|------|--------|
| Gemini API（無料枠あり） | レシート読み取り、PDF取り込み | aistudio.google.com |
| Claude API | 家計アドバイス | console.anthropic.com |
| Google Sheets API（無料） | スプレッドシート連携 | console.cloud.google.com |

APIキーはサイドバーに入力するか、環境変数で設定:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

## セキュリティ

- API送信データは匿名化（金額は概算、口座名/保険会社名は非送信）
- APIキーは画面に非表示、セッション終了で消去
- エラーメッセージは汎用化（内部情報を非表示）
- CSVインジェクション対策、HTMLエスケープ、入力検証
- 個人データは `.gitignore` で除外済み

## 使い方ガイド

`開始はこのフォルダ/使い方ガイド.html` をダブルクリックしてください。
中学生でもわかるステップバイステップガイドです。

## 技術スタック

- Python 3.9+ / Streamlit / Pandas / Plotly
- Anthropic API / Google Gemini API（オプション）
- cryptography（Fernet暗号化）

## 作成者・連絡先

- **作成者**: TKG.M.
- **質問・感想**: [GitHub Issues](https://github.com/hirschmannielladiversa-bot/household-budget-app/issues) からお願いします

## ライセンス

個人利用限定。2次配布は禁止です。
