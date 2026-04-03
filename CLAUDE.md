# CLAUDE.md - 家計管理アプリ

**Version**: 2.0.0

## プロジェクト概要

NotebookLM（Google Sheets）と連携した家計管理・分析アプリケーション。
Streamlitベースのダッシュボードで、多角的なグラフ分析とAIアドバイス機能を提供。
Google Sheets APIによる直接連携で、スプレッドシートから収入・支出データを自動取得可能。
収入管理・ローン追跡機能を搭載し、収支の全体像を把握可能。
セキュリティ強化により、API送信データの匿名化や入力検証を実装。

## クイックスタート

```bash
cd "/Volumes/tkg SSD/household-budget-app"

# 依存関係インストール
pip install -r requirements.txt

# アプリ起動
python3 -m streamlit run app.py
```

## プロジェクト構造

```
household-budget-app/
├── app.py                    # メインStreamlitアプリ
├── requirements.txt          # 依存関係
├── config/
│   ├── categories.yaml       # カテゴリ設定
│   └── bank_formats.yaml     # 銀行CSV/カテゴリパターン設定
├── data/
│   ├── sample_budget.csv     # サンプルデータ
│   ├── budget.csv            # 保存された家計データ
│   ├── accounts.csv          # 口座データ
│   └── transactions.csv      # 取引データ
├── modules/
│   ├── data_loader.py        # データ読み込み
│   ├── analyzer.py           # 分析ロジック
│   ├── visualizer.py         # グラフ生成
│   ├── advisor.py            # AIアドバイス（Claude/Gemini）
│   ├── bank_manager.py       # 口座・取引管理
│   ├── receipt_reader.py     # レシート画像読み取り（Gemini）
│   ├── gemini_utils.py       # Gemini APIリトライ処理
│   ├── asset_manager.py      # 資産管理
│   ├── tax_calculator.py     # 税金計算
│   ├── year_end_adjustment.py # 年末調整
│   └── google_sheets_loader.py # Google Sheets API連携
└── templates/
    └── google_sheets_template.md
```

## 技術スタック

- Python 3.9+
- Streamlit（Web UI）
- Pandas（データ処理）
- Plotly（インタラクティブグラフ）
- Anthropic API（AIアドバイス・チャット）
- Google Gemini API（レシート読み取り・PDF解析）

## タブ構成

📋 概要 | 📈 グラフ | 💰 収入管理 | 🧭 アドバイス | 🏦 資産管理 | 💴 税金・年末調整 | 💳 口座管理 | 📄 データ一覧

## 機能一覧

### データ入力
- CSV/Excelファイルアップロード
- 手動入力フォーム
- **Google Sheets API連携**: スプレッドシートから直接読み込み（収入・支出両対応）
- レシート画像読み取り（Gemini API）

### Google Sheets連携（📊）
- **直接読み込み**: スプレッドシートURLを入力してデータ取得
- **収入・支出の両方対応**: シート名自動検出（支出/収入/expenses/income）
- **列名自動マッピング**: 日付/date、カテゴリ/category、金額/amount等
- **NotebookLM連携**: YAMLエクスポート、月別レポート生成

### 💰 収入管理
- **月別収入入力**: 月ごとの収入データを管理
- **口座からの給与自動検出**: 銀行口座の取引データから給与を自動検出
- **収支比較グラフ**: 収入と支出を月別に比較表示
- **収支差額グラフ**: 月別の収支差額を可視化

### 🏠 ローン・負債管理
- **住宅ローン/車ローン**: 各種ローンの登録・管理
- **月々返済額**: 毎月の返済額を設定
- **賞与月返済額**: ボーナス月の増額返済に対応
- **引落口座指定**: ローンごとに引落口座を指定
- **返済進捗**: 返済状況の進捗表示

### 口座管理（💳）
- **銀行CSV取り込み**: 三菱UFJ、三井住友、みずほ、楽天銀行、新生銀行、ろうきん等
- **クレジットカードCSV取り込み**: 三井住友カード、三菱UFJニコス、Amazon Mastercard等
- **自動カテゴリ分類**: 摘要から自動でカテゴリを判定
- **家計データ連携**: 口座の支出を家計データにエクスポート
- **重複チェック**: 同一取引の重複登録を防止

### 📄 PDF・画像取り込み
- **全口座対応**: 銀行明細・カード明細の両方に対応
- **PDF複数一括**: 複数のPDFファイルを一括取り込み
- **画像(JPG/PNG)複数一括**: 複数の画像ファイルを一括取り込み
- **Gemini Vision**: Gemini APIで明細を解析・データ化

### カテゴリ自動分類
`config/bank_formats.yaml`で定義されたパターンに基づき自動分類：

| カテゴリ | 例 |
|---------|-----|
| 給与 | 給与、賞与、ソウムジム |
| 食費 | イオン、セブン、マクドナルド、パルシステム |
| 交通費 | JR、SUICA、ETC、ガソリン、ENEOS |
| 医療費 | 病院、クリニック、薬局、ドラッグ |
| 通信費 | ドコモ、AU、APPLE、NHK |
| 光熱費 | 東京電力、東京ガス、水道、クレツクス |
| 住居費 | 家賃、D-room、管理費 |
| 保険料 | オリックス生命、ジブラルタ、アンシンセイメイ |
| 娯楽費 | Netflix、Nintendo、TSUTAYA |
| 日用品 | ダイソー、ニトリ、DCM、テラスモール |
| 衣服 | ユニクロ、GU、アルペン、ヘア |
| AI費 | Claude、OpenAI、ChatGPT、Midjourney、Norton |
| 税 | 所得税、住民税、固定資産税 |
| 資産 | iDeCo、NISA、確定拠出、積立 |
| 車両費 | スバル、車検、オートバックス |
| 除外 | ATM、楽天カード、セブン銀行定期（集計から除外） |

**特徴**:
- 半角全角を区別しない（NFKC正規化）
- 部分一致で判定

### 分析・可視化（📈）
- カテゴリ別支出円グラフ
- 月別推移棒グラフ
- トレンド折れ線グラフ
- 曜日×カテゴリヒートマップ
- 予算達成ゲージ

### AIアドバイス（🧭）
- **総合アドバイス生成**: 家計全体の診断とアクションプラン
- **チャット相談**: Claudeファイナンシャルプランナーと対話形式で相談
- **Gemini連携**: レシート読み取り、PDF解析
- ルールベース診断（APIキーなしでも動作）

### 資産管理（🏦）
- 現金・預金・投資・不動産等の資産追跡
- 暗号資産対応（オプション）
- 資産推移グラフ

### 税金・年末調整（💴）
- 所得税・住民税計算
- 年末調整シミュレーション
- 税金カレンダー

### データ管理（📄）
- **重複削除**: 同日・同金額・同メモの重複を検出して削除（「その他」優先削除）
- **楽天カード削除**: メモに楽天カードを含むデータを一括削除
- **カテゴリ再分類**: 「その他」カテゴリを再分類

## 🔒 セキュリティ

- **API送信データの匿名化**: 金額は概算で送信、個人名・口座名はAPIに送信しない
- **ローカル完結**: APIなしで全コア機能が動作（AI機能のみAPI必要）
- **.gitignoreで個人データ除外**: CSVデータ・認証情報はリポジトリに含めない
- **入力検証**: CSVインジェクション対策、日付範囲チェック、金額上限チェック
- **HTMLエスケープ**: ユーザー入力の表示時にエスケープ処理
- **エラーメッセージ汎用化**: 内部情報を漏洩しない汎用的なエラーメッセージ

## API設定

### Google Sheets API（スプレッドシート連携）
1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクト作成
2. 「APIとサービス」→「ライブラリ」→ Google Sheets API を有効化
3. 「認証情報」→「サービスアカウント」を作成
4. JSONキーをダウンロード → `config/google_credentials.json` に配置
5. スプレッドシートをサービスアカウントのメールアドレスと共有
6. サイドバー「📊 Google Sheets連携」でURL入力して読み込み

### Claude API（アドバイス用）
1. サイドバーの「Anthropic API Key」欄にキーを貼り付け
2. 「Claudeによる自然文アドバイスを有効化」にチェック

### Gemini API（レシート読み取り・PDF解析用）
1. サイドバーの「Gemini API Key」欄にキーを貼り付け
2. レシート読み取りやPDF取り込みで使用

### APIキーの取得
- Claude: https://console.anthropic.com/
- Gemini: https://makersuite.google.com/app/apikey

## 設定ファイル

### config/bank_formats.yaml
銀行CSVフォーマットとカテゴリ自動分類パターンを定義：

```yaml
bank:
  mufj:
    name: "三菱UFJ銀行"
    encoding: "shift_jis"
    columns:
      date: "日付"
      description: "摘要"
      ...

category_patterns:
  食費:
    - イオン
    - セブン
    ...
```

### config/categories.yaml
支出カテゴリと理想比率を定義

## スキル

| コマンド | 説明 |
|---------|------|
| `/budget-app` | アプリを起動 |
| `/budget-analyze` | サンプルデータで分析テスト |

---

**Last Updated**: 2026-04-03
