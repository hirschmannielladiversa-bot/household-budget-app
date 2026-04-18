import html
import logging
import os
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

import pandas as pd
import streamlit as st

from modules import (
    DataLoader, BudgetAnalyzer, BudgetVisualizer, FinancialAdvisor,
    AssetManager, TaxCalculator, AssetVisualizer, CryptoManager, is_crypto_available,
    ReceiptReader, is_gemini_available, MonthlyImporter, is_monthly_format,
    YearEndAdjustment, BankManager,
    GoogleSheetsLoader, NotebookLMExporter, is_google_sheets_available
)
from modules.advisor import get_history_summary_path


APP_TITLE = "🏠 家計管理ダッシュボード"
APP_DESCRIPTION = "NotebookLM（Google Sheets）連携を想定した家計管理・分析アプリです。"

BASE_DIR = Path(__file__).parent
PROFILES_PATH = BASE_DIR / "data" / "profiles.json"


def get_data_dir() -> Path:
    """現在選択中のプロファイルのデータディレクトリを取得"""
    rel = st.session_state.get("data_dir_rel", "data")
    return BASE_DIR / rel


def get_user_settings_path() -> Path:
    return get_data_dir() / "user_settings.json"


def load_user_settings() -> dict:
    """ユーザー設定をファイルから読み込み"""
    import json
    path = get_user_settings_path()
    if path.exists():
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_user_settings(settings: dict) -> None:
    """ユーザー設定をファイルに保存"""
    import json
    path = get_user_settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except IOError as e:
        logger.error(f"設定の保存に失敗しました: {e}")
        st.error("設定の保存に失敗しました。再試行してください。")


def get_current_settings() -> dict:
    """現在のセッションからユーザー設定を取得"""
    return {
        "insurance_list": st.session_state.get("insurance_list", []),
        "financial_assets": st.session_state.get("financial_assets", []),
        "furusato_donations": st.session_state.get("furusato_donations", []),
        "usd_rate": st.session_state.get("usd_rate", 150.0),
        "total_income": st.session_state.get("total_income", 0),
        "monthly_income": st.session_state.get("monthly_income"),
        "budget": st.session_state.get("budget"),
        "annual_income": st.session_state.get("annual_income"),
        "savings_deposit": st.session_state.get("savings_deposit", 0),
    }


def apply_saved_settings(settings: dict) -> None:
    """保存された設定をセッションに適用"""
    if "insurance_list" in settings:
        st.session_state.insurance_list = settings["insurance_list"]
    if "usd_rate" in settings:
        st.session_state.usd_rate = settings["usd_rate"]
    if "total_income" in settings:
        st.session_state.total_income = settings["total_income"]
    if "monthly_income" in settings and settings["monthly_income"] is not None:
        st.session_state.monthly_income = settings["monthly_income"]
    if "budget" in settings and settings["budget"] is not None:
        st.session_state.budget = settings["budget"]
    if "annual_income" in settings and settings["annual_income"] is not None:
        st.session_state.annual_income = settings["annual_income"]
    if "savings_deposit" in settings:
        st.session_state.savings_deposit = settings["savings_deposit"]
    if "financial_assets" in settings:
        st.session_state.financial_assets = settings["financial_assets"]
    if "furusato_donations" in settings:
        st.session_state.furusato_donations = settings["furusato_donations"]


def init_session_state() -> None:
    """セッション状態の初期化"""
    data_dir = str(get_data_dir())
    # data_dir をadvisor.pyからも参照できるよう session_state に保存
    st.session_state.data_dir = data_dir

    if "data_loader" not in st.session_state:
        st.session_state.data_loader = DataLoader(data_dir=data_dir)
    if "df" not in st.session_state:
        loader: DataLoader = st.session_state.data_loader
        saved_df = loader.load_saved_data()
        if saved_df is not None:
            st.session_state.df = saved_df
        else:
            st.session_state.df = None  # type: ignore[assignment]
    if "monthly_income" not in st.session_state:
        st.session_state.monthly_income = None
    if "budget" not in st.session_state:
        st.session_state.budget = None
    if "use_claude" not in st.session_state:
        st.session_state.use_claude = False
    if "assets_df" not in st.session_state:
        st.session_state.assets_df = None
    if "asset_manager" not in st.session_state:
        st.session_state.asset_manager = AssetManager()
    if "tax_calculator" not in st.session_state:
        st.session_state.tax_calculator = TaxCalculator()
    if "annual_income" not in st.session_state:
        st.session_state.annual_income = None
    if "crypto_manager" not in st.session_state:
        base_dir = Path(__file__).parent
        st.session_state.crypto_manager = CryptoManager(base_dir)
    if "asset_password" not in st.session_state:
        st.session_state.asset_password = None
    if "asset_unlocked" not in st.session_state:
        st.session_state.asset_unlocked = False
    if "gemini_api_key" not in st.session_state:
        st.session_state.gemini_api_key = ""
    if "receipt_result" not in st.session_state:
        st.session_state.receipt_result = None
    if "monthly_importer" not in st.session_state:
        st.session_state.monthly_importer = MonthlyImporter()
    if "year_end_adjustment" not in st.session_state:
        st.session_state.year_end_adjustment = YearEndAdjustment(data_dir=data_dir)
        st.session_state.year_end_adjustment.load_from_yaml()
    if "bank_manager" not in st.session_state:
        st.session_state.bank_manager = BankManager(data_dir=data_dir)
        st.session_state.bank_manager.load_from_csv()
        st.session_state.bank_manager.reclassify_transactions(only_other=False)
    if "financial_assets" not in st.session_state:
        st.session_state.financial_assets = []
    if "furusato_donations" not in st.session_state:
        st.session_state.furusato_donations = []
    if "insurance_list" not in st.session_state:
        st.session_state.insurance_list = []
    if "usd_rate" not in st.session_state:
        st.session_state.usd_rate = 150.0
    if "editing_insurance_idx" not in st.session_state:
        st.session_state.editing_insurance_idx = None

    # ユーザー設定の読み込み（保険、為替レート、収入など）
    if "user_settings_loaded" not in st.session_state:
        saved_settings = load_user_settings()
        apply_saved_settings(saved_settings)
        st.session_state.user_settings_loaded = True


def load_sample_data() -> pd.DataFrame:
    """サンプルデータ読み込み"""
    sample_path = get_data_dir() / "sample_budget.csv"
    loader: DataLoader = st.session_state.data_loader
    return loader.load_csv(sample_path)


def load_sample_assets() -> pd.DataFrame:
    """サンプル資産データ読み込み"""
    sample_path = get_data_dir() / "sample_assets.csv"
    manager: AssetManager = st.session_state.asset_manager
    return manager.load_assets(str(sample_path))


def sidebar_data_input() -> None:
    """サイドバー：AI設定・暗号化・Google Sheets"""

    # AI アドバイス設定
    st.sidebar.subheader("🤖 AI アドバイス")

    # AIプロバイダー選択
    if "ai_provider" not in st.session_state:
        st.session_state.ai_provider = "gemini"

    ai_provider = st.sidebar.radio(
        "AIプロバイダー",
        options=["gemini", "claude"],
        format_func=lambda x: "Gemini (無料)" if x == "gemini" else "Claude (有料)",
        index=0 if st.session_state.ai_provider == "gemini" else 1,
        horizontal=True,
    )
    st.session_state.ai_provider = ai_provider

    # Gemini API Key（アドバイス + レシート読み取り共用）
    gemini_env = os.getenv("GEMINI_API_KEY", "")
    gemini_key = st.sidebar.text_input(
        "Gemini APIキー",
        value=st.session_state.get("gemini_api_key", gemini_env),
        type="password",
        help="Google AI Studioで取得: https://aistudio.google.com/",
    )
    st.session_state.gemini_api_key = gemini_key

    # Claude API Key
    env_key = os.getenv("ANTHROPIC_API_KEY")
    if "api_key" not in st.session_state:
        st.session_state.api_key = env_key or ""

    if ai_provider == "claude":
        api_key_input = st.sidebar.text_input(
            "Anthropic API Key",
            value=st.session_state.api_key,
            type="password",
            help="Claude APIを利用するにはAPIキーが必要です。https://console.anthropic.com/ で取得できます。",
        )
        st.session_state.api_key = api_key_input
        has_api_key = api_key_input is not None and api_key_input != ""
    else:
        has_api_key = bool(gemini_key)

    use_ai = st.sidebar.checkbox(
        "AI による自然文アドバイスを有効化",
        value=st.session_state.use_claude,
        disabled=not has_api_key,
        help=None if has_api_key else "APIキーを入力してください。",
    )
    st.session_state.use_claude = use_ai

    sidebar_security_settings()
    sidebar_google_sheets()


def sidebar_receipt_reader() -> None:
    """サイドバー：レシート読み取り"""
    st.sidebar.markdown("---")
    st.sidebar.header("📷 レシート自動読み取り")

    # Gemini APIキー入力
    gemini_key = st.sidebar.text_input(
        "Gemini APIキー",
        value=st.session_state.gemini_api_key,
        type="password",
        help="Google AI Studioで取得: https://aistudio.google.com/"
    )
    st.session_state.gemini_api_key = gemini_key

    if not gemini_key:
        st.sidebar.caption("APIキーを入力してレシート読み取りを有効化")
        return

    # 画像/PDFアップロード
    uploaded_image = st.sidebar.file_uploader(
        "レシート画像またはPDFをアップロード",
        type=["jpg", "jpeg", "png", "webp", "pdf"],
        key="receipt_image"
    )

    if uploaded_image is not None:
        # プレビュー（PDFは画像表示できないのでファイル名のみ）
        if uploaded_image.name.lower().endswith(".pdf"):
            st.sidebar.info(f"📄 {uploaded_image.name}")
        else:
            st.sidebar.image(uploaded_image, caption="アップロード画像", use_container_width=True)

        # 読み取り実行ボタン
        if st.sidebar.button("🔍 読み取り実行"):
            with st.sidebar.spinner("Gemini APIで解析中..."):
                try:
                    reader = ReceiptReader(gemini_key)
                    result = reader.read_receipt(uploaded_image.read(), filename=uploaded_image.name)
                    st.session_state.receipt_result = result
                    st.sidebar.success("読み取り完了！")
                except Exception as e:
                    logger.error(f"レシート読み取りエラー: {e}")
                    st.sidebar.error("レシートの読み取りに失敗しました。ファイルを確認してください。")
                    st.session_state.receipt_result = None

    # 読み取り結果の表示と編集
    result = st.session_state.receipt_result
    if result:
        st.sidebar.markdown("---")
        st.sidebar.subheader("📋 読み取り結果")

        # 編集可能なフォーム
        with st.sidebar.form("receipt_entry_form"):
            from datetime import datetime

            # 日付
            date_value = result.get("date")
            if date_value:
                try:
                    date_obj = datetime.strptime(date_value, "%Y-%m-%d").date()
                except:
                    date_obj = datetime.now().date()
            else:
                date_obj = datetime.now().date()

            edit_date = st.date_input("日付", value=date_obj)

            # 店舗名
            edit_store = st.text_input("店舗", value=result.get("store_name", ""))

            # カテゴリ
            loader: DataLoader = st.session_state.data_loader
            categories = loader.get_category_list()
            current_cat = result.get("category", "その他")
            if current_cat in categories:
                cat_index = categories.index(current_cat)
            else:
                cat_index = categories.index("その他") if "その他" in categories else 0

            edit_category = st.selectbox("カテゴリ", categories, index=cat_index)

            # 金額
            edit_amount = st.number_input(
                "金額（円）",
                value=float(result.get("amount", 0)),
                min_value=0.0,
                step=1.0
            )

            # メモ
            edit_memo = st.text_input(
                "メモ",
                value=f"{result.get('store_name', '')} - {result.get('memo', '')}".strip(" -")
            )

            # 信頼度表示
            confidence = result.get("confidence", 0)
            st.caption(f"読み取り信頼度: {confidence * 100:.0f}%")

            # 追加ボタン
            submitted = st.form_submit_button("✅ 支出に追加")

            if submitted:
                if st.session_state.df is None:
                    df = loader.create_empty_dataframe()
                else:
                    df = st.session_state.df

                try:
                    df = loader.add_entry(df, edit_date, edit_category, edit_amount, edit_memo)
                    st.session_state.df = df
                    st.session_state.receipt_result = None  # 結果をクリア
                    st.success("支出を追加しました！")
                except Exception as e:
                    logger.error(f"支出の追加に失敗しました: {e}")
                    st.error("追加に失敗しました。入力内容を確認してください。")


def sidebar_monthly_import() -> None:
    """サイドバー：月別データインポート"""
    st.sidebar.markdown("---")
    st.sidebar.header("📅 月別支出インポート")

    # Excelファイルアップロード
    uploaded_excel = st.sidebar.file_uploader(
        "月別支出Excel（横持ちフォーマット）",
        type=["xlsx", "xls"],
        key="monthly_excel",
        help="月が行、カテゴリが列のExcelファイル"
    )

    if uploaded_excel is not None:
        importer: MonthlyImporter = st.session_state.monthly_importer

        try:
            # Excelを読み込み
            raw_df = importer.load_from_bytes(uploaded_excel.read())

            # プレビュー表示
            st.sidebar.success(f"読み込み成功: {len(raw_df)}行")

            # カテゴリマッピングプレビュー
            with st.sidebar.expander("📋 カテゴリマッピング確認"):
                mappings = importer.get_category_mapping_preview(raw_df)
                for m in mappings:
                    st.write(f"**{m['元カテゴリ']}** → {m['マッピング先']}")

            # 変換ボタン
            if st.sidebar.button("📥 インポート実行"):
                # 標準フォーマットに変換
                converted_df = importer.convert_to_standard_format(raw_df)

                if len(converted_df) > 0:
                    # 既存データに追加
                    loader: DataLoader = st.session_state.data_loader

                    if st.session_state.df is None or len(st.session_state.df) == 0:
                        st.session_state.df = converted_df
                    else:
                        # 重複チェック（同じ年月のデータは上書き）
                        existing = st.session_state.df.copy()
                        existing["年月"] = pd.to_datetime(existing["日付"]).dt.to_period("M")
                        converted_df["年月"] = pd.to_datetime(converted_df["日付"]).dt.to_period("M")

                        new_months = set(converted_df["年月"].unique())
                        existing = existing[~existing["年月"].isin(new_months)]

                        combined = pd.concat([existing.drop(columns=["年月"]),
                                            converted_df.drop(columns=["年月"])],
                                           ignore_index=True)
                        st.session_state.df = combined

                    st.sidebar.success(f"✓ {len(converted_df)}件のデータをインポートしました")
                    st.rerun()
                else:
                    st.sidebar.error("変換できるデータがありませんでした")

        except Exception as e:
            logger.error(f"月別データ読み込みエラー: {e}")
            st.sidebar.error("データの読み込みに失敗しました。ファイル形式を確認してください。")


def sidebar_google_sheets() -> None:
    """サイドバー：Google Sheets連携"""
    st.sidebar.markdown("---")
    st.sidebar.header("📊 Google Sheets連携")

    # API利用可否チェック
    if not is_google_sheets_available():
        st.sidebar.warning(
            "Google Sheets APIライブラリが未インストール\n\n"
            "`pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib`"
        )
        return

    # 認証ファイルパス
    config_dir = Path(__file__).parent / "config"
    credentials_path = config_dir / "google_credentials.json"

    if not credentials_path.exists():
        with st.sidebar.expander("🔧 セットアップ手順", expanded=True):
            st.markdown("""
            **Google Sheets APIの設定:**

            1. [Google Cloud Console](https://console.cloud.google.com/) にアクセス
            2. プロジェクトを作成（または既存を選択）
            3. 「APIとサービス」→「ライブラリ」→ Google Sheets API を有効化
            4. 「APIとサービス」→「認証情報」→「サービスアカウント」を作成
            5. サービスアカウントのキー（JSON）をダウンロード
            6. JSONファイルを以下に配置:

            `config/google_credentials.json`

            7. スプレッドシートをサービスアカウントのメールアドレスと共有
            """)
        return

    # セッション状態の初期化
    if "gsheets_loader" not in st.session_state:
        st.session_state.gsheets_loader = GoogleSheetsLoader(str(credentials_path))
    if "gsheets_income_df" not in st.session_state:
        st.session_state.gsheets_income_df = None
    if "sheets_url" not in st.session_state:
        st.session_state.sheets_url = ""

    st.sidebar.success("✓ 認証ファイル検出")

    # スプレッドシートURL入力
    sheets_url = st.sidebar.text_input(
        "スプレッドシートURL または ID",
        value=st.session_state.sheets_url,
        placeholder="https://docs.google.com/spreadsheets/d/...",
        help="共有設定で「リンクを知っている全員」またはサービスアカウントに共有してください"
    )
    st.session_state.sheets_url = sheets_url

    if not sheets_url:
        st.sidebar.caption("URLを入力してシートに接続")
        return

    loader: GoogleSheetsLoader = st.session_state.gsheets_loader

    # シート一覧取得
    try:
        with st.sidebar.spinner("シート一覧を取得中..."):
            sheet_names = loader.get_sheet_names(sheets_url)
    except Exception as e:
        logger.error(f"Google Sheets接続エラー: {e}")
        st.sidebar.error("接続に失敗しました。URLとAPIキーを確認してください。")
        return

    st.sidebar.success(f"✓ {len(sheet_names)}シート検出")

    # シート選択
    col1, col2 = st.sidebar.columns(2)
    with col1:
        expense_sheet = st.selectbox(
            "支出シート",
            ["(自動検出)"] + sheet_names,
            key="expense_sheet_select"
        )
    with col2:
        income_sheet = st.selectbox(
            "収入シート",
            ["(自動検出)"] + sheet_names,
            key="income_sheet_select"
        )

    # データ読み込みボタン
    if st.sidebar.button("📥 スプレッドシートから読み込み", use_container_width=True):
        with st.sidebar.spinner("データ読み込み中..."):
            try:
                # 支出データ読み込み
                expense_sheet_name = None if expense_sheet == "(自動検出)" else expense_sheet
                expenses_df = loader.load_expenses(sheets_url, expense_sheet_name)

                if len(expenses_df) > 0:
                    st.session_state.df = expenses_df
                    st.sidebar.success(f"✓ 支出: {len(expenses_df)}件")
                else:
                    st.sidebar.warning("支出データが見つかりませんでした")

                # 収入データ読み込み
                income_sheet_name = None if income_sheet == "(自動検出)" else income_sheet
                try:
                    income_df = loader.load_income(sheets_url, income_sheet_name)
                    if len(income_df) > 0:
                        st.session_state.gsheets_income_df = income_df

                        # 月別収入を計算してセッションに保存
                        monthly_income = income_df.groupby('年月')['金額'].sum()
                        if len(monthly_income) > 0:
                            avg_monthly = monthly_income.mean()
                            st.session_state.monthly_income = float(avg_monthly)
                            st.session_state.total_income = float(monthly_income.sum())

                        st.sidebar.success(f"✓ 収入: {len(income_df)}件")
                except Exception:
                    st.sidebar.caption("収入シートは見つかりませんでした")

                # 設定を保存
                save_user_settings(get_current_settings())
                st.rerun()

            except Exception as e:
                logger.error(f"Google Sheets読み込みエラー: {e}")
                st.sidebar.error("シートの読み込みに失敗しました。設定を確認してください。")

    # NotebookLM連携
    with st.sidebar.expander("📝 NotebookLM連携", expanded=False):
        if st.session_state.df is not None and len(st.session_state.df) > 0:
            exporter = NotebookLMExporter()

            # YAMLエクスポート
            if st.button("📋 YAML生成", key="generate_yaml"):
                yaml_str = exporter.export_to_yaml(
                    st.session_state.df,
                    st.session_state.gsheets_income_df
                )
                st.code(yaml_str, language="yaml")

            # 月別レポート
            st.markdown("---")
            st.caption("月別レポート生成")

            df_copy = st.session_state.df.copy()
            df_copy['年月'] = df_copy['日付'].dt.to_period('M').astype(str)
            months = sorted(df_copy['年月'].unique(), reverse=True)

            selected_month = st.selectbox("対象月", months, key="report_month")

            if st.button("📄 レポート生成", key="generate_report"):
                report = exporter.export_monthly_report(
                    st.session_state.df,
                    st.session_state.gsheets_income_df,
                    selected_month
                )
                st.markdown(report)

            # ダウンロードボタン
            st.markdown("---")
            yaml_content = exporter.export_to_yaml(
                st.session_state.df,
                st.session_state.gsheets_income_df
            )
            st.download_button(
                "📥 YAMLダウンロード",
                data=yaml_content,
                file_name="budget_data.yaml",
                mime="text/yaml"
            )
        else:
            st.caption("データを読み込むとNotebookLM連携が利用できます")


def sidebar_security_settings() -> None:
    """サイドバー：セキュリティ設定"""
    st.sidebar.markdown("---")
    st.sidebar.header("🔐 資産データ暗号化")

    crypto: CryptoManager = st.session_state.crypto_manager
    has_data = crypto.has_encrypted_data()

    if has_data:
        info = crypto.get_encrypted_info()
        st.sidebar.caption(f"暗号化ファイル: 存在 ({info['size_bytes']:,} bytes)")
    else:
        st.sidebar.caption("暗号化ファイル: なし")

    # パスワード入力
    password = st.sidebar.text_input(
        "パスワード",
        type="password",
        key="asset_password_input",
        help="資産データの暗号化・復号に使用するパスワード"
    )

    col1, col2 = st.sidebar.columns(2)

    with col1:
        if st.button("🔓 読み込み", disabled=not has_data or not password):
            manager: AssetManager = st.session_state.asset_manager
            if manager.load_encrypted(crypto, password):
                st.session_state.assets_df = manager.df
                st.session_state.asset_password = password
                st.session_state.asset_unlocked = True
                st.sidebar.success("復号成功！")
                st.rerun()
            else:
                st.sidebar.error("パスワードが違います")

    with col2:
        assets_df = st.session_state.assets_df
        can_save = password and assets_df is not None and len(assets_df) > 0
        if st.button("💾 保存", disabled=not can_save):
            manager: AssetManager = st.session_state.asset_manager
            manager.df = assets_df
            if manager.save_encrypted(crypto, password):
                st.session_state.asset_password = password
                st.sidebar.success("暗号化保存完了！")
            else:
                st.sidebar.error("保存に失敗しました")

    # ロック状態表示
    if st.session_state.asset_unlocked:
        st.sidebar.success("🔓 資産データ: アンロック済み")
        if st.sidebar.button("🔒 ロック"):
            st.session_state.asset_unlocked = False
            st.session_state.asset_password = None
            st.session_state.assets_df = None
            st.rerun()


def show_overview_tab(analyzer: BudgetAnalyzer, visualizer: BudgetVisualizer) -> None:
    """概要タブ"""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    df = analyzer.df

    # --- 年度フィルタ ---
    current_year = datetime.now().year
    current_month = datetime.now().month
    # 現在の年度（4月始まり: 1〜3月は前年度）
    current_nendo = current_year if current_month >= 4 else current_year - 1
    reiwa_offset = 2018  # 令和1年 = 2019年

    # データから年度の範囲を推定
    nendo_options = ["全期間"]
    if not df.empty and '日付' in df.columns:
        min_year = df['日付'].min().year
        min_month = df['日付'].min().month
        max_year = df['日付'].max().year
        max_month = df['日付'].max().month
        first_nendo = min_year if min_month >= 4 else min_year - 1
        last_nendo = max(current_nendo, max_year if max_month >= 4 else max_year - 1)
        for y in range(first_nendo, last_nendo + 1):
            reiwa = y - reiwa_offset
            nendo_options.append(f"R{reiwa}年度（{y}/4〜{y+1}/3）")
    else:
        for y in range(current_nendo - 2, current_nendo + 1):
            reiwa = y - reiwa_offset
            nendo_options.append(f"R{reiwa}年度（{y}/4〜{y+1}/3）")

    selected_nendo = st.selectbox("📅 対象年度", options=nendo_options, index=0, key="overview_nendo")

    # 年度に応じてdfをフィルタ
    if selected_nendo != "全期間" and not df.empty and '日付' in df.columns:
        try:
            nendo_year = int(selected_nendo.split("（")[1].split("/")[0])
            nendo_start = pd.Timestamp(nendo_year, 4, 1)
            nendo_end = pd.Timestamp(nendo_year + 1, 3, 31, 23, 59, 59)
            df = df[(df['日付'] >= nendo_start) & (df['日付'] <= nendo_end)]
        except (IndexError, ValueError):
            st.warning("年度のパースに失敗しました。全期間を表示します。")

    # フィルタ後のanalyzerを再構築
    filtered_analyzer = BudgetAnalyzer(df, analyzer.ideal_ratios)
    stats = filtered_analyzer.statistics_summary()

    # 収入計算（monthly_income_dataから実データ集計）
    import json as _json
    _income_data = st.session_state.get("monthly_income_data", {})
    if not _income_data:
        _income_path = get_data_dir() / "monthly_income.json"
        if _income_path.exists():
            try:
                with open(_income_path, 'r', encoding='utf-8') as _f:
                    _income_data = _json.load(_f)
                    st.session_state.monthly_income_data = _income_data
            except Exception:
                _income_data = {}

    def _overview_get_take_home(v):
        if isinstance(v, (int, float)):
            return int(v)
        if isinstance(v, dict):
            return v.get("take_home", 0)
        return 0

    if selected_nendo != "全期間" and not df.empty and '日付' in df.columns:
        # 年度フィルタ: 該当年度の月のみ集計
        nendo_months = set(str(m) for m in df['日付'].dt.to_period('M').unique())
        income_total = sum(
            _overview_get_take_home(v) for k, v in _income_data.items()
            if k.replace("_bonus", "").replace("_adj", "") in nendo_months
        )
    else:
        # 全期間: 全データ集計
        income_total = sum(_overview_get_take_home(v) for v in _income_data.values())

    filled_income_months = len([k for k, v in _income_data.items() if not k.endswith("_bonus") and not k.endswith("_adj") and _overview_get_take_home(v) > 0])
    monthly_income = income_total / filled_income_months if filled_income_months > 0 else 0

    # 銀行口座の残高合計（預貯金）
    bank_manager = st.session_state.get("bank_manager")
    total_deposits = 0
    account_balances = []
    if bank_manager and bank_manager.accounts_df is not None and not bank_manager.accounts_df.empty:
        for _, acc in bank_manager.accounts_df.iterrows():
            balance = acc.get('current_balance', 0) or 0
            total_deposits += balance
            if balance > 0:
                account_balances.append({
                    'name': acc.get('name', '不明'),
                    'bank_name': acc.get('bank_name', ''),
                    'type': acc.get('account_type', ''),
                    'balance': balance
                })

    # 総資産計算（預貯金 + 貯蓄型保険 + 金融資産）
    insurance_list = st.session_state.get("insurance_list", [])
    _usd_rate = st.session_state.get("usd_rate", 150.0)
    savings_insurance_value = 0
    savings_insurance_annual = 0
    term_insurance_annual = 0
    for _ins in insurance_list:
        if _ins.get("currency") == "USD":
            _ins_annual = int(_ins.get("annual_usd", 0) * _usd_rate)
            _ins_value = int(_ins.get("value_usd", 0) * _usd_rate)
        else:
            _ins_annual = _ins.get("annual", 0)
            _ins_value = _ins.get("value", 0)
        if _ins.get("type") == "貯蓄型":
            savings_insurance_annual += _ins_annual
            savings_insurance_value += _ins_value
        else:
            term_insurance_annual += _ins_annual
    financial_assets = st.session_state.get("financial_assets", [])
    financial_assets_value = sum(fa.get("current_value", 0) for fa in financial_assets)
    total_assets = total_deposits + savings_insurance_value + financial_assets_value

    # 支出の指標（収入を除外）
    expense_df = df[df['カテゴリ'] != '給与'] if not df.empty and 'カテゴリ' in df.columns else df
    expense_total = expense_df['金額'].sum() if not expense_df.empty else 0

    # 収支バランス
    balance = income_total - expense_total

    # メトリクス表示（2行に分割）
    nendo_label = selected_nendo.split("（")[0] if selected_nendo != "全期間" else "全期間"
    st.markdown(f"### 💰 収支サマリー（{nendo_label}）")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        income_label = f"手取り収入（{nendo_label}）" if selected_nendo != "全期間" else "年間手取り収入"
        st.metric(income_label, f"¥{income_total:,.0f}")
    with col2:
        st.metric("総支出（期間内）", f"¥{expense_total:,.0f}")
    with col3:
        st.metric("預貯金", f"¥{total_deposits:,.0f}")
    with col4:
        st.metric("総資産", f"¥{total_assets:,.0f}")

    col5, col6, col7, col8 = st.columns(4)
    with col5:
        st.metric("月収（手取り）", f"¥{monthly_income:,.0f}")
    with col6:
        st.metric("月平均支出", f"¥{stats['average_monthly']:,.0f}")
    with col7:
        total_insurance = savings_insurance_annual + term_insurance_annual
        st.metric("年間保険料", f"¥{total_insurance:,.0f}")
    with col8:
        trend = stats["trend"]
        st.metric("支出トレンド", trend.get("trend", "不明"), f"{trend.get('change', 0):.1f}%")

    # 収入・資産の円グラフ
    st.markdown("### 📊 収入・資産の内訳")
    col_income_pie, col_asset_pie = st.columns(2)

    with col_income_pie:
        # 収入の使途内訳（手取りベース）
        if income_total > 0:
            # 支出カテゴリ別の合計
            if not expense_df.empty and 'カテゴリ' in expense_df.columns:
                expense_by_cat = expense_df.groupby('カテゴリ')['金額'].sum()

                # 支出カテゴリ
                labels = list(expense_by_cat.index)
                values = list(expense_by_cat.values)

                # 残額（貯蓄）
                remaining = income_total - expense_total
                if remaining > 0:
                    labels.append('貯蓄・余剰')
                    values.append(remaining)

                fig_income = go.Figure(data=[go.Pie(
                    labels=labels,
                    values=values,
                    hole=0.4,
                    textinfo='label+percent',
                    textposition='outside',
                    textfont_size=10,
                    pull=[0.02] * len(labels),
                )])
                fig_income.update_layout(
                    title=f'手取り収入の使途（年間: ¥{income_total:,.0f}）',
                    height=550,
                    margin=dict(t=50, b=30, l=30, r=30),
                    showlegend=True,
                    legend=dict(
                        orientation='v',
                        yanchor='middle',
                        y=0.5,
                        xanchor='left',
                        x=1.05,
                        font=dict(size=9),
                    ),
                    uniformtext_minsize=8,
                    uniformtext_mode='hide',
                )
                st.plotly_chart(fig_income, use_container_width=True)
            else:
                st.info("支出データがありません")
        else:
            st.info("サイドバーで月収（手取り）を入力してください")

    with col_asset_pie:
        # 資産内訳 - 個別項目ごとに表示、カテゴリは色で区別
        # 青系=貯金（銀行口座）、赤系=貯蓄型保険、緑系=金融資産
        asset_labels = []
        asset_values = []
        asset_colors = []
        asset_categories = []

        # 青系カラーパレット（貯金）
        blue_palette = ["#2980b9", "#3498db", "#5dade2", "#85c1e9", "#aed6f1"]
        # 赤系カラーパレット（貯蓄型保険）
        red_palette = ["#c0392b", "#e74c3c", "#ec7063", "#f1948a"]
        # 緑系カラーパレット（金融資産）
        green_palette = ["#27ae60", "#2ecc71", "#58d68d", "#82e0aa"]

        # 銀行口座 → 貯金（短縮名で表示）
        blue_idx = 0
        for acc in account_balances:
            if acc['balance'] > 0:
                # グラフ用は短い名前、詳細用はフル名
                short_label = acc['name']
                asset_labels.append(short_label)
                asset_values.append(acc['balance'])
                asset_colors.append(blue_palette[blue_idx % len(blue_palette)])
                asset_categories.append("貯金")
                blue_idx += 1

        # 貯蓄型保険（短縮名で表示）
        red_idx = 0
        for ins in insurance_list:
            if ins["type"] == "貯蓄型" and ins.get("value", 0) > 0:
                if ins.get("currency") == "USD":
                    usd_rate = st.session_state.get("usd_rate", 150.0)
                    value = int(ins.get("value_usd", 0) * usd_rate)
                else:
                    value = ins.get("value", 0)
                # 長い保険名を短縮（「」内の商品名を使う）
                full_name = ins['name']
                if '「' in full_name and '」' in full_name:
                    short_label = full_name[full_name.index('「'):full_name.index('」') + 1]
                elif len(full_name) > 10:
                    short_label = full_name[:10] + '…'
                else:
                    short_label = full_name
                asset_labels.append(short_label)
                asset_values.append(value)
                asset_colors.append(red_palette[red_idx % len(red_palette)])
                asset_categories.append("貯蓄型保険")
                red_idx += 1

        # 金融資産（iDeCo, NISAなど）
        green_idx = 0
        for fa in financial_assets:
            v = fa.get("current_value", 0)
            if v > 0:
                asset_labels.append(fa['name'])
                asset_values.append(v)
                asset_colors.append(green_palette[green_idx % len(green_palette)])
                asset_categories.append("金融資産")
                green_idx += 1

        if asset_labels:
            total_assets_pie = sum(asset_values)

            # ホバーにフル名・カテゴリ・金額を表示
            full_names = []
            fi = 0
            for acc in account_balances:
                if acc['balance'] > 0:
                    bn = acc.get('bank_name', '')
                    full_names.append(f"{acc['name']}（{bn}）" if bn else acc['name'])
            for ins in insurance_list:
                if ins["type"] == "貯蓄型" and ins.get("value", 0) > 0:
                    full_names.append(ins['name'])
            for fa in financial_assets:
                if fa.get("current_value", 0) > 0:
                    full_names.append(f"{fa['name']}（{fa.get('type', '')}）")

            hover_texts = [f"【{cat}】{fn}<br>¥{val:,.0f}"
                           for fn, val, cat in zip(full_names, asset_values, asset_categories)]

            fig_assets = go.Figure(data=[go.Pie(
                labels=asset_labels,
                values=asset_values,
                hole=0.4,
                textinfo='label+percent',
                textposition='inside',
                insidetextorientation='radial',
                hovertext=hover_texts,
                hoverinfo='text',
                marker=dict(colors=asset_colors),
                textfont=dict(size=11),
            )])
            fig_assets.update_layout(
                title=dict(text=f'資産内訳（総資産: ¥{total_assets_pie:,.0f}）', font=dict(size=14)),
                height=420,
                showlegend=True,
                legend=dict(
                    orientation='h', yanchor='top', y=-0.02,
                    xanchor='center', x=0.5, font=dict(size=10)
                ),
                margin=dict(t=40, b=60, l=10, r=10),
            )
            st.plotly_chart(fig_assets, use_container_width=True)

            # カテゴリ別サマリーをexpanderで表示
            with st.expander("資産内訳の詳細"):
                # カテゴリごとに集計
                cat_totals = {}
                cat_items = {}
                for label, val, cat in zip(asset_labels, asset_values, asset_categories):
                    cat_totals[cat] = cat_totals.get(cat, 0) + val
                    cat_items.setdefault(cat, []).append(f"{html.escape(label)}: ¥{val:,.0f}")

                for cat_name, color_hint in [("貯金", "🔵"), ("貯蓄型保険", "🔴"), ("金融資産", "🟢")]:
                    if cat_name in cat_totals:
                        st.markdown(f"**{color_hint} {html.escape(cat_name)}（¥{cat_totals[cat_name]:,.0f}）**")
                        for item in cat_items[cat_name]:
                            st.markdown(f"- {item}")
        else:
            st.info("資産データがありません（口座管理で口座を追加するか、サイドバーで金融資産・保険を登録してください）")

    # 収入・支出・資産のグラフ
    st.markdown("### 📊 月別収支推移")

    # 銀行取引から月別の入出金を取得
    bank_income_by_month = pd.Series(dtype=float)
    bank_expense_by_month = pd.Series(dtype=float)
    bm = st.session_state.get("bank_manager")
    if bm and bm.transactions_df is not None and len(bm.transactions_df) > 0:
        tx = bm.transactions_df.copy()
        tx['date'] = pd.to_datetime(tx['date'])
        # 年度フィルタを適用
        if selected_nendo != "全期間":
            try:
                ny = int(selected_nendo.split("（")[1].split("/")[0])
                tx = tx[(tx['date'] >= pd.Timestamp(ny, 4, 1)) & (tx['date'] <= pd.Timestamp(ny + 1, 3, 31, 23, 59, 59))]
            except (IndexError, ValueError):
                pass
        tx['month'] = tx['date'].dt.to_period('M').astype(str)
        # 入金（amount > 0）
        bank_income_by_month = tx[tx['amount'] > 0].groupby('month')['amount'].sum()
        # 出金（amount < 0）→ 絶対値
        bank_expense_by_month = tx[tx['amount'] < 0].groupby('month')['amount'].sum().abs()

    if not df.empty and '日付' in df.columns:
        # 月別データを計算
        df_with_month = df.copy()
        df_with_month['month'] = df_with_month['日付'].dt.to_period('M').astype(str)

        # 月別支出（家計データから）
        expense_by_month_budget = df_with_month[df_with_month['カテゴリ'] != '給与'].groupby('month')['金額'].sum()

        # 月別収入：銀行入金データがあればそれを使用、なければサイドバー月収を適用
        all_expense_months = set(expense_by_month_budget.index)
        all_income_months = set(bank_income_by_month.index) if len(bank_income_by_month) > 0 else set()
        all_months = sorted(all_expense_months | all_income_months)

        if all_months:
            has_bank_income = len(bank_income_by_month) > 0
            if has_bank_income:
                income_values = [bank_income_by_month.get(m, 0) for m in all_months]
            else:
                income_values = [monthly_income for _ in all_months]
            expense_values = [expense_by_month_budget.get(m, 0) for m in all_months]
            balance_values = [inc - exp for inc, exp in zip(income_values, expense_values)]

            # 累計資産の推移（収支バランスの累積）
            cumulative_balance = []
            running_total = 0
            for b in balance_values:
                running_total += b
                cumulative_balance.append(running_total)

            # 収支グラフ
            fig_income_expense = go.Figure()

            fig_income_expense.add_trace(go.Bar(
                name='収入',
                x=all_months,
                y=income_values,
                marker_color='#2ecc71'
            ))

            fig_income_expense.add_trace(go.Bar(
                name='支出',
                x=all_months,
                y=expense_values,
                marker_color='#e74c3c'
            ))

            fig_income_expense.add_trace(go.Scatter(
                name='収支バランス',
                x=all_months,
                y=balance_values,
                mode='lines+markers',
                line=dict(color='#3498db', width=3),
                yaxis='y2'
            ))

            fig_income_expense.update_layout(
                barmode='group',
                title='月別収入・支出推移',
                xaxis_title='月',
                yaxis_title='金額（円）',
                yaxis2=dict(
                    title='収支バランス（円）',
                    overlaying='y',
                    side='right',
                    showgrid=False
                ),
                legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='center', x=0.5),
                height=400
            )

            col_graph1, col_graph2 = st.columns(2)

            with col_graph1:
                st.plotly_chart(fig_income_expense, use_container_width=True)

            with col_graph2:
                # 累計資産推移グラフ
                fig_assets = go.Figure()

                # 累計収支
                fig_assets.add_trace(go.Scatter(
                    name='累計収支',
                    x=all_months,
                    y=cumulative_balance,
                    mode='lines+markers+text',
                    fill='tozeroy',
                    line=dict(color='#9b59b6', width=2),
                    fillcolor='rgba(155, 89, 182, 0.3)'
                ))

                # 貯蓄型保険（固定値として表示）
                if savings_insurance_value > 0:
                    fig_assets.add_hline(
                        y=savings_insurance_value,
                        line_dash="dash",
                        line_color="#f39c12",
                        annotation_text=f"貯蓄型保険: ¥{savings_insurance_value:,.0f}",
                        annotation_position="top right"
                    )

                fig_assets.update_layout(
                    title='累計収支推移',
                    xaxis_title='月',
                    yaxis_title='累計額（円）',
                    height=400,
                    showlegend=True
                )

                st.plotly_chart(fig_assets, use_container_width=True)

    st.markdown("---")
    st.markdown("### 📈 多角的分析ダッシュボード")
    st.caption("家計のバランス・理想比率との乖離・貯蓄率・季節性など、複数の視点で現状を把握できます。")

    _analysis_tabs = st.tabs([
        "🎯 理想比率との乖離",
        "💧 貯蓄率トレンド",
        "🔥 月×カテゴリ ヒートマップ",
        "📊 50/30/20 ルール",
        "🌊 収支フロー（Sankey）",
        "📋 支出ランキング",
    ])

    # --- Tab 1: 理想比率との乖離 ---
    with _analysis_tabs[0]:
        if expense_df is not None and not expense_df.empty and 'カテゴリ' in expense_df.columns and income_total > 0:
            ideal_ratios = getattr(analyzer, 'ideal_ratios', {}) or {}
            actual_by_cat = expense_df.groupby('カテゴリ')['金額'].sum()
            _rows = []
            for _cat in actual_by_cat.index:
                if _cat == '給与':
                    continue
                _actual_ratio = float(actual_by_cat[_cat]) / float(income_total) if income_total > 0 else 0
                _ideal_ratio = float(ideal_ratios.get(_cat, 0) or 0)
                _rows.append({
                    'カテゴリ': _cat,
                    '実績比率': _actual_ratio * 100,
                    '理想比率': _ideal_ratio * 100,
                    '差分': (_actual_ratio - _ideal_ratio) * 100,
                })
            if _rows:
                _df_ratio = pd.DataFrame(_rows).sort_values('差分')
                _fig_dev = go.Figure()
                _fig_dev.add_trace(go.Bar(
                    name='理想比率',
                    y=_df_ratio['カテゴリ'],
                    x=_df_ratio['理想比率'],
                    orientation='h',
                    marker_color='rgba(189,195,199,0.6)',
                    hovertemplate='%{y}<br>理想: %{x:.1f}%<extra></extra>',
                ))
                _colors = ['#e74c3c' if d > 0 else '#27ae60' for d in _df_ratio['差分']]
                _fig_dev.add_trace(go.Bar(
                    name='実績比率',
                    y=_df_ratio['カテゴリ'],
                    x=_df_ratio['実績比率'],
                    orientation='h',
                    marker_color=_colors,
                    customdata=_df_ratio['差分'],
                    hovertemplate='%{y}<br>実績: %{x:.1f}%<br>差分: %{customdata:+.1f}pt<extra></extra>',
                ))
                _fig_dev.update_layout(
                    barmode='overlay',
                    title='カテゴリ別：実績 vs 理想比率（手取り収入に対する %）',
                    xaxis_title='比率（%）',
                    height=max(350, 32 * len(_df_ratio)),
                    legend=dict(orientation='h', y=-0.15),
                    margin=dict(t=50, b=40, l=80, r=20),
                )
                st.plotly_chart(_fig_dev, use_container_width=True)
                st.caption("🔴 赤 = 理想比率より多い／🟢 緑 = 理想比率以下。灰色バーは理想値。手取り収入を分母にした割合です。")
            else:
                st.info("支出データが足りません。")
        else:
            st.info("支出データまたは手取り収入データが不足しています。")

    # --- Tab 2: 貯蓄率トレンド ---
    with _analysis_tabs[1]:
        _has_monthly = (
            not df.empty and '日付' in df.columns
            and 'all_months' in dir() and len(locals().get('all_months', [])) > 0
        )
        # 上の if ブロック外でも参照できるよう、再計算する
        if not df.empty and '日付' in df.columns:
            _dfm = df.copy()
            _dfm['month'] = _dfm['日付'].dt.to_period('M').astype(str)
            _exp_by_m = _dfm[_dfm['カテゴリ'] != '給与'].groupby('month')['金額'].sum()
            # 月別収入: 銀行入金 or monthly_income_data
            _inc_by_m = {}
            if bm and bm.transactions_df is not None and len(bm.transactions_df) > 0:
                _tx = bm.transactions_df.copy()
                _tx['date'] = pd.to_datetime(_tx['date'])
                if selected_nendo != "全期間":
                    try:
                        _ny = int(selected_nendo.split("（")[1].split("/")[0])
                        _tx = _tx[(_tx['date'] >= pd.Timestamp(_ny, 4, 1)) & (_tx['date'] <= pd.Timestamp(_ny + 1, 3, 31, 23, 59, 59))]
                    except (IndexError, ValueError):
                        pass
                _tx['month'] = _tx['date'].dt.to_period('M').astype(str)
                _inc_series = _tx[_tx['amount'] > 0].groupby('month')['amount'].sum()
                _inc_by_m = _inc_series.to_dict()
            # monthly_income_data からも補完
            for _k, _v in _income_data.items():
                if _k.endswith("_bonus") or _k.endswith("_adj"):
                    continue
                _th = _overview_get_take_home(_v)
                if _th > 0 and _k not in _inc_by_m:
                    _inc_by_m[_k] = _th

            _all_m = sorted(set(_exp_by_m.index) | set(_inc_by_m.keys()))
            if _all_m:
                _inc_vals = [float(_inc_by_m.get(m, 0)) for m in _all_m]
                _exp_vals = [float(_exp_by_m.get(m, 0)) for m in _all_m]
                _sr = [((i - e) / i * 100) if i > 0 else 0 for i, e in zip(_inc_vals, _exp_vals)]
                # 3ヶ月移動平均
                _ma = []
                for _i in range(len(_sr)):
                    _start = max(0, _i - 2)
                    _win = _sr[_start:_i + 1]
                    _ma.append(sum(_win) / len(_win) if _win else 0)

                _fig_sr = go.Figure()
                _fig_sr.add_trace(go.Bar(
                    x=_all_m, y=_sr, name='月次貯蓄率',
                    marker_color=['#27ae60' if r >= 20 else '#f39c12' if r >= 0 else '#e74c3c' for r in _sr],
                    hovertemplate='%{x}<br>貯蓄率: %{y:.1f}%<extra></extra>',
                ))
                _fig_sr.add_trace(go.Scatter(
                    x=_all_m, y=_ma, name='3ヶ月移動平均',
                    mode='lines+markers',
                    line=dict(color='#2c3e50', width=3, dash='dash'),
                ))
                _fig_sr.add_hline(y=20, line_dash='dot', line_color='#16a085',
                                  annotation_text='推奨: 20%', annotation_position='top right')
                _fig_sr.add_hline(y=0, line_color='#7f8c8d', line_width=1)
                _fig_sr.update_layout(
                    title='月次貯蓄率の推移（(収入 − 支出) / 収入）',
                    yaxis_title='貯蓄率（%）',
                    xaxis_title='月',
                    height=420,
                    legend=dict(orientation='h', y=-0.2),
                )
                st.plotly_chart(_fig_sr, use_container_width=True)

                _avg_sr = sum(_sr) / len(_sr) if _sr else 0
                _positive_months = sum(1 for r in _sr if r > 0)
                _cs1, _cs2, _cs3 = st.columns(3)
                with _cs1:
                    st.metric("平均貯蓄率", f"{_avg_sr:.1f}%",
                              delta=f"{_avg_sr - 20:+.1f}pt vs 推奨 20%")
                with _cs2:
                    st.metric("黒字月", f"{_positive_months} / {len(_sr)} ヶ月")
                with _cs3:
                    if _sr:
                        st.metric("直近の貯蓄率", f"{_sr[-1]:.1f}%",
                                  delta=f"{_sr[-1] - _avg_sr:+.1f}pt vs 平均")
            else:
                st.info("月別の収支データがありません。")
        else:
            st.info("支出データがありません。")

    # --- Tab 3: 月×カテゴリ ヒートマップ ---
    with _analysis_tabs[2]:
        if expense_df is not None and not expense_df.empty and '日付' in expense_df.columns:
            _hm = expense_df.copy()
            _hm['month'] = _hm['日付'].dt.to_period('M').astype(str)
            _pivot = _hm.groupby(['カテゴリ', 'month'])['金額'].sum().unstack(fill_value=0)
            if not _pivot.empty:
                # カテゴリ順: 合計の大きい順
                _pivot = _pivot.loc[_pivot.sum(axis=1).sort_values(ascending=True).index]
                _fig_hm = go.Figure(data=go.Heatmap(
                    z=_pivot.values,
                    x=_pivot.columns,
                    y=_pivot.index,
                    colorscale='YlOrRd',
                    hovertemplate='カテゴリ: %{y}<br>月: %{x}<br>支出: ¥%{z:,.0f}<extra></extra>',
                    colorbar=dict(title='金額（円）'),
                ))
                _fig_hm.update_layout(
                    title='カテゴリ × 月 の支出ヒートマップ',
                    xaxis_title='月', yaxis_title='カテゴリ',
                    height=max(400, 28 * len(_pivot.index)),
                    margin=dict(t=50, b=40, l=100, r=40),
                )
                st.plotly_chart(_fig_hm, use_container_width=True)
                st.caption("色が濃いほど支出が大きい月。季節変動・突発支出・特定カテゴリの膨張を一目で把握できます。")
            else:
                st.info("ピボットできる支出データがありません。")
        else:
            st.info("支出データがありません。")

    # --- Tab 4: 50/30/20 ルール ---
    with _analysis_tabs[3]:
        NEEDS_CATS = {'食費', '住居費', '光熱費', '通信費', '医療費', '保険料', '税金', '交通費', '日用品'}
        WANTS_CATS = {'娯楽費', '衣服', '自己投資', '教育費', 'AI費', 'IT費', '雑費', '車両費', 'その他', 'ふるさと納税'}
        SAVINGS_CATS = {'投資'}
        if expense_df is not None and not expense_df.empty and income_total > 0:
            _cs = expense_df.groupby('カテゴリ')['金額'].sum()
            _needs = float(sum(_cs.get(c, 0) for c in NEEDS_CATS))
            _wants = float(sum(_cs.get(c, 0) for c in WANTS_CATS))
            _savings_explicit = float(sum(_cs.get(c, 0) for c in SAVINGS_CATS))
            _residual = float(income_total) - _needs - _wants - _savings_explicit
            _savings = _savings_explicit + max(_residual, 0)
            _actual = {
                '必需（Needs）': _needs,
                '娯楽（Wants）': _wants,
                '貯蓄（Savings）': _savings,
            }
            _target = {
                '必需（Needs）': float(income_total) * 0.5,
                '娯楽（Wants）': float(income_total) * 0.3,
                '貯蓄（Savings）': float(income_total) * 0.2,
            }
            _fig_rule = go.Figure()
            _fig_rule.add_trace(go.Bar(
                name='目標 (50/30/20)',
                x=list(_target.keys()), y=list(_target.values()),
                marker_color='rgba(189,195,199,0.55)',
                text=[f'¥{v:,.0f}<br>{v/income_total*100:.0f}%' for v in _target.values()],
                textposition='outside',
            ))
            _fig_rule.add_trace(go.Bar(
                name='実績',
                x=list(_actual.keys()), y=list(_actual.values()),
                marker_color=['#3498db', '#e67e22', '#27ae60'],
                text=[f'¥{v:,.0f}<br>{v/income_total*100:.1f}%' for v in _actual.values()],
                textposition='outside',
            ))
            _fig_rule.update_layout(
                barmode='group',
                title='50/30/20 ルール：実績 vs 目標',
                yaxis_title='金額（円）',
                height=450,
                legend=dict(orientation='h', y=-0.15),
            )
            st.plotly_chart(_fig_rule, use_container_width=True)

            _r1, _r2, _r3 = st.columns(3)
            with _r1:
                _n_pct = _needs / income_total * 100
                st.metric("必需 Needs", f"{_n_pct:.1f}%", f"{_n_pct - 50:+.1f}pt vs 50%")
            with _r2:
                _w_pct = _wants / income_total * 100
                st.metric("娯楽 Wants", f"{_w_pct:.1f}%", f"{_w_pct - 30:+.1f}pt vs 30%")
            with _r3:
                _s_pct = _savings / income_total * 100
                st.metric("貯蓄 Savings", f"{_s_pct:.1f}%", f"{_s_pct - 20:+.1f}pt vs 20%")
            st.caption("エリザベス・ウォーレン提唱の「50/30/20 ルール」。必需50% / 娯楽30% / 貯蓄20%が健全な家計バランスの目安です。カテゴリ分類は編集可（コード上の NEEDS_CATS / WANTS_CATS を参照）。")
        else:
            st.info("支出データまたは手取り収入が不足しています。")

    # --- Tab 5: Sankey ---
    with _analysis_tabs[4]:
        if expense_df is not None and not expense_df.empty and income_total > 0:
            _cs2 = expense_df.groupby('カテゴリ')['金額'].sum().sort_values(ascending=False)
            _cats = list(_cs2.index)
            _vals = [float(v) for v in _cs2.values]
            _residual2 = max(float(income_total) - sum(_vals), 0)
            _labels = ['手取り収入'] + _cats + ['貯蓄・余剰']
            _sources = [0] * (len(_cats) + 1)
            _targets = list(range(1, len(_cats) + 2))
            _values = _vals + [_residual2]
            _node_colors = ['#2ecc71'] + ['#e74c3c'] * len(_cats) + ['#3498db']
            _link_colors = ['rgba(231,76,60,0.25)'] * len(_cats) + ['rgba(52,152,219,0.35)']
            _fig_sk = go.Figure(go.Sankey(
                arrangement='snap',
                node=dict(label=_labels, pad=15, thickness=22, color=_node_colors,
                          line=dict(color='#2c3e50', width=0.5)),
                link=dict(source=_sources, target=_targets, value=_values, color=_link_colors),
            ))
            _fig_sk.update_layout(
                title='収入 → 支出カテゴリ → 貯蓄 のフロー',
                height=550,
                font=dict(size=12),
                margin=dict(t=50, b=20, l=10, r=10),
            )
            st.plotly_chart(_fig_sk, use_container_width=True)
            st.caption("手取り収入を起点に、どのカテゴリへいくら流れ、最終的にいくら貯蓄に回ったかを一望できます。")
        else:
            st.info("支出データまたは手取り収入が不足しています。")

    # --- Tab 6: 支出ランキング ---
    with _analysis_tabs[5]:
        _colp, _colt = st.columns(2)
        with _colp:
            st.markdown("#### カテゴリ別支出割合")
            st.plotly_chart(visualizer.category_pie_chart(), use_container_width=True)
        with _colt:
            st.markdown("#### 高額支出一覧")
            st.plotly_chart(visualizer.top_expenses_table(), use_container_width=True)


def show_income_tab(analyzer: BudgetAnalyzer) -> None:
    """収入管理タブ（拡張版: 月収/控除/手取り/口座分け + 給与明細PDF読み取り）"""
    import json
    import plotly.graph_objects as go

    st.markdown("### 💰 月別収入管理")
    st.caption("月ごとの収入を入力し、支出との比較を確認できます。給与明細PDFからの自動読み取りにも対応。")

    income_path = get_data_dir() / "monthly_income.json"
    if "monthly_income_data" not in st.session_state:
        if income_path.exists():
            try:
                with open(income_path, 'r', encoding='utf-8') as f:
                    st.session_state.monthly_income_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                st.session_state.monthly_income_data = {}
        else:
            st.session_state.monthly_income_data = {}

    income_data = st.session_state.monthly_income_data

    def _normalize_entry(value):
        if isinstance(value, (int, float)):
            return {"gross_salary": 0, "deductions": {"social_insurance": 0, "income_tax": 0, "resident_tax": 0, "other": 0}, "take_home": int(value), "account_distribution": {}}
        return value

    def _get_take_home(value):
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, dict):
            return value.get("take_home", 0)
        return 0

    if not analyzer.df.empty and '日付' in analyzer.df.columns:
        months = sorted(analyzer.df['日付'].dt.to_period('M').unique(), reverse=True)
    else:
        months = []

    # === 振込口座の設定（読み込み: サブタブ共通で使用） ===
    settings_path = get_data_dir() / "user_settings.json"
    _usr_settings = {}
    if settings_path.exists():
        try:
            with open(settings_path, 'r', encoding='utf-8') as _sf:
                _usr_settings = json.load(_sf)
        except (json.JSONDecodeError, IOError):
            pass

    # BankManager口座リスト取得
    _bm = st.session_state.get("bank_manager")
    _bm_accounts = []  # [(account_id, display_label), ...]
    if _bm and _bm.accounts_df is not None and not _bm.accounts_df.empty:
        for _, _acc in _bm.accounts_df[_bm.accounts_df['account_type'] == 'bank'].iterrows():
            _bm_accounts.append((_acc['account_id'], f"{_acc['name']}（{_acc['bank_name']}）"))

    # 口座リンク設定の読み込み
    _acct_links = {
        "account_1": _usr_settings.get("income_account_1_id", ""),
        "account_2": _usr_settings.get("income_account_2_id", ""),
        "account_3": _usr_settings.get("income_account_3_id", ""),
    }
    _acct_names = {}
    for _ak, _aid in _acct_links.items():
        if _aid and _bm:
            _acc_row = _bm.get_account(_aid)
            _acct_names[_ak] = _acc_row['name'] if _acc_row is not None else ""
        else:
            _acct_names[_ak] = _usr_settings.get(f"income_{_ak}_name", "")

    def _sync_income_to_bank(year_month, acct_key, amount, doc_type="salary"):
        """収入データをBankManager口座に入金トランザクションとして反映"""
        if not _bm or amount <= 0:
            return
        linked_id = _acct_links.get(acct_key, "")
        if not linked_id:
            return
        acc = _bm.get_account(linked_id)
        if acc is None:
            return
        type_label = {"salary": "給与", "bonus": "賞与", "adjustment": "差額"}.get(doc_type, "給与")
        desc = f"{type_label}振込 ({year_month})"
        # 日付: 月末の20日を仮定（給与支給日）
        tx_date = f"{year_month}-20"
        tid = _bm.add_transaction(
            account_id=linked_id, date=tx_date, description=desc,
            amount=float(amount), category="給与",
            memo=f"自動連携: {acct_key}", skip_duplicate_check=False
        )
        if tid:
            # 残高を更新（現在の残高 + 入金額）
            new_bal = float(acc.get('current_balance', 0)) + float(amount)
            _bm.update_account(linked_id, {'current_balance': new_bal})

    # サブタブ: PDF読み取り / 手入力 / データ一覧
    income_sub1, income_sub_manual, income_sub2 = st.tabs(["📄 PDF読み取り・サマリー", "✏️ 手入力", "📊 データ一覧・編集"])

    with income_sub_manual:
        st.subheader("✏️ 収入を手入力")
        st.caption("月別の収入を口座ごとに記録できます。口座を選択すると、その口座の残高にも自動加算されます。")

        # 口座選択肢（登録済み銀行口座 + 手動入力口座）
        _im_acct_choices = ["（口座連携なし）"] + [lbl for _, lbl in _bm_accounts]
        _im_acct_ids = [""] + [aid for aid, _ in _bm_accounts]

        with st.form("_income_manual_form", clear_on_submit=True):
            _imc1, _imc2 = st.columns(2)
            with _imc1:
                _im_year = st.number_input("年", min_value=2000, max_value=2100,
                                            value=datetime.now().year, step=1, key="_im_year")
                _im_month = st.number_input("月", min_value=1, max_value=12,
                                             value=datetime.now().month, step=1, key="_im_month")
                _im_type = st.selectbox("収入種別",
                                         ["給与", "賞与", "差額", "その他"],
                                         key="_im_type")
            with _imc2:
                _im_amount = st.number_input("金額（円・手取り）", min_value=0.0, step=1000.0, key="_im_amount")
                _im_acct = st.selectbox("入金口座", _im_acct_choices, key="_im_acct")
                _im_memo = st.text_input("メモ（任意）", key="_im_memo")
            _im_deposit = st.checkbox("選択口座の残高に自動加算する", value=True, key="_im_deposit")
            _im_submit = st.form_submit_button("➕ 追加", type="primary")

            if _im_submit:
                if _im_amount <= 0:
                    st.warning("金額を入力してください。")
                else:
                    ym = f"{int(_im_year):04d}-{int(_im_month):02d}"
                    entry = _normalize_entry(income_data.get(ym, {}))
                    if not isinstance(entry, dict):
                        entry = _normalize_entry(entry)
                    # 手入力分を account_distribution に積み上げ
                    acct_label = _im_acct if _im_acct != "（口座連携なし）" else ""
                    dist_key = acct_label if acct_label else "手入力"
                    dist = entry.get("account_distribution") or {}
                    dist[dist_key] = float(dist.get(dist_key, 0) or 0) + float(_im_amount)
                    entry["account_distribution"] = dist
                    entry["take_home"] = int(float(entry.get("take_home", 0) or 0) + float(_im_amount))
                    # 種別とメモを notes に追記（既存があれば連結）
                    notes = entry.get("manual_notes", [])
                    notes.append({
                        "type": _im_type,
                        "amount": float(_im_amount),
                        "account": acct_label,
                        "memo": _im_memo,
                        "added_at": datetime.now().isoformat(timespec="seconds"),
                    })
                    entry["manual_notes"] = notes
                    income_data[ym] = entry
                    st.session_state.monthly_income_data = income_data

                    # ファイル保存
                    try:
                        with open(income_path, 'w', encoding='utf-8') as _f:
                            json.dump(income_data, _f, ensure_ascii=False, indent=2)
                    except IOError as _e:
                        st.error(f"収入データの保存に失敗しました: {_e}")

                    # 口座残高に加算
                    deposited = False
                    if acct_label and _im_deposit and _bm is not None:
                        _idx = _im_acct_choices.index(_im_acct)
                        _aid = _im_acct_ids[_idx] if _idx >= 0 else ""
                        if _aid:
                            _acc = _bm.get_account(_aid)
                            if _acc is not None:
                                _type_label = {"給与": "salary", "賞与": "bonus", "差額": "adjustment"}.get(_im_type, "other")
                                _desc = f"{_im_type}振込 ({ym})" + (f" - {_im_memo}" if _im_memo else "")
                                _tid = _bm.add_transaction(
                                    account_id=_aid, date=f"{ym}-20",
                                    description=_desc, amount=float(_im_amount),
                                    category="給与", memo=_im_memo or f"手入力: {_im_type}",
                                    skip_duplicate_check=False,
                                )
                                if _tid:
                                    _new_bal = float(_acc.get('current_balance', 0) or 0) + float(_im_amount)
                                    _bm.update_account(_aid, {'current_balance': _new_bal})
                                    try:
                                        _bm.save_to_csv()
                                        deposited = True
                                    except Exception as _e:
                                        st.error(f"口座保存に失敗: {_e}")
                    msg = f"✓ {ym} に {_im_type} ¥{_im_amount:,.0f} を追加しました。"
                    if deposited:
                        msg += f"（{acct_label} の残高に加算済み）"
                    elif acct_label and _im_deposit:
                        msg += "（口座が特定できなかったため残高加算はスキップしました）"
                    st.success(msg)

        # 既存の手入力メモ一覧
        st.markdown("---")
        st.markdown("#### 📋 これまでに手入力した項目")
        _all_notes = []
        for _ym, _entry in sorted(income_data.items()):
            _entry_n = _entry if isinstance(_entry, dict) else _normalize_entry(_entry)
            for _n in (_entry_n.get("manual_notes") or []):
                _all_notes.append({
                    "年月": _ym,
                    "種別": _n.get("type", ""),
                    "金額": int(float(_n.get("amount", 0) or 0)),
                    "口座": _n.get("account", ""),
                    "メモ": _n.get("memo", ""),
                    "追加日時": _n.get("added_at", ""),
                })
        if _all_notes:
            _notes_df = pd.DataFrame(_all_notes).sort_values(["年月", "追加日時"], ascending=[False, False])
            st.dataframe(_notes_df, use_container_width=True, hide_index=True)
        else:
            st.caption("まだ手入力された収入はありません。")

    with income_sub1:
        # === 振込口座の設定UI ===
        with st.expander("🏦 振込口座の設定（入力し直さない限り引き継がれます）", expanded=False):
            if not _bm_accounts:
                st.warning("口座が未登録です。「🏦 資産・税金・保険」タブの口座一覧で口座を追加してください。")
                st.caption("口座名を直接入力することもできます（口座残高連携なし）。")
                _ac_col1, _ac_col2, _ac_col3 = st.columns(3)
                with _ac_col1:
                    _a1_input = st.text_input("第1口座", value=_acct_names.get("account_1", ""), key="_income_acct1_name", placeholder="例: 地共済茨城")
                with _ac_col2:
                    _a2_input = st.text_input("第2口座", value=_acct_names.get("account_2", ""), key="_income_acct2_name", placeholder="例: ゆうちょ銀行")
                with _ac_col3:
                    _a3_input = st.text_input("第3口座", value=_acct_names.get("account_3", ""), key="_income_acct3_name", placeholder="例: 〇〇銀行")
                if st.button("💾 口座設定を保存", key="_income_save_acct_settings"):
                    _usr_settings["income_account_1_name"] = _a1_input.strip()
                    _usr_settings["income_account_2_name"] = _a2_input.strip()
                    _usr_settings["income_account_3_name"] = _a3_input.strip()
                    _usr_settings.pop("income_account_1_id", None)
                    _usr_settings.pop("income_account_2_id", None)
                    _usr_settings.pop("income_account_3_id", None)
                    try:
                        with open(settings_path, 'w', encoding='utf-8') as _sf:
                            json.dump(_usr_settings, _sf, ensure_ascii=False, indent=2)
                        st.success("✓ 口座設定を保存しました")
                    except IOError:
                        st.error("保存に失敗しました")
            else:
                st.caption("口座一覧から選択すると、給与振込が口座残高に自動反映されます。")
                _acct_options = ["（未設定）"] + [label for _, label in _bm_accounts]
                _acct_ids = [""] + [aid for aid, _ in _bm_accounts]

                def _find_idx(acct_key):
                    saved_id = _acct_links.get(acct_key, "")
                    if saved_id in _acct_ids:
                        return _acct_ids.index(saved_id)
                    return 0

                _ac_col1, _ac_col2, _ac_col3 = st.columns(3)
                with _ac_col1:
                    _a1_sel = st.selectbox("第1口座", _acct_options, index=_find_idx("account_1"), key="_income_acct1_sel")
                with _ac_col2:
                    _a2_sel = st.selectbox("第2口座", _acct_options, index=_find_idx("account_2"), key="_income_acct2_sel")
                with _ac_col3:
                    _a3_sel = st.selectbox("第3口座", _acct_options, index=_find_idx("account_3"), key="_income_acct3_sel")

                if st.button("💾 口座設定を保存", key="_income_save_acct_settings"):
                    for _key, _sel_val in [("1", _a1_sel), ("2", _a2_sel), ("3", _a3_sel)]:
                        _sel_idx = _acct_options.index(_sel_val) if _sel_val in _acct_options else 0
                        _sel_id = _acct_ids[_sel_idx] if _sel_idx > 0 else ""
                        _sel_name = ""
                        if _sel_id and _bm:
                            _acc_r = _bm.get_account(_sel_id)
                            _sel_name = _acc_r['name'] if _acc_r is not None else ""
                        _usr_settings[f"income_account_{_key}_id"] = _sel_id
                        _usr_settings[f"income_account_{_key}_name"] = _sel_name
                        _acct_links[f"account_{_key}"] = _sel_id
                        _acct_names[f"account_{_key}"] = _sel_name
                    try:
                        with open(settings_path, 'w', encoding='utf-8') as _sf:
                            json.dump(_usr_settings, _sf, ensure_ascii=False, indent=2)
                        st.success("✓ 口座設定を保存しました（給与振込が口座残高に自動連携されます）")
                    except IOError:
                        st.error("保存に失敗しました")

        # === 給与明細PDF読み取り ===
        with st.expander("📄 給与明細PDF・画像から読み取り", expanded=False):
            gemini_key = st.session_state.get("gemini_api_key", "")
            if not gemini_key:
                st.warning("サイドバーの「🤖 AI アドバイス」で Gemini API キーを入力してください。")
            else:
                payslip_files = st.file_uploader(
                    "給与明細のPDFまたは画像をアップロード（複数可）",
                    type=["pdf", "jpg", "jpeg", "png", "webp"],
                    accept_multiple_files=True,
                    key="_income_payslip_upload"
                )
                if payslip_files:
                    st.caption(f"{len(payslip_files)}件のファイルが選択されています")
                    if st.button(f"🔍 {len(payslip_files)}件を一括読み取り", type="primary", key="_income_payslip_read"):
                        from modules.gemini_utils import call_gemini_with_retry
                        from google import genai
                        import re as _re

                        client = genai.Client(api_key=gemini_key)
                        all_parsed = []
                        progress = st.progress(0, text="読み取り中...")

                        prompt = """この書類の種別を自動判定し、JSON形式で情報を抽出してください。
    書類は「月例給与」「賞与（ボーナス）」「差額（年末調整等の差額支給）」「年末調整（源泉徴収票）」のいずれかです。
    金額は数値のみ（カンマなし）。該当項目がない場合は 0 、文字列は "" にしてください。

    【重要な読み取り指示】
    - 「＜振込情報＞」セクション（書類の右側）にある「第1口座振込額」「第2口座振込額」を必ず読み取ること。
      振込先金融機関名（共済支部名など）も取得すること。
    - 「＜控除金内訳＞」セクションの右列にある「一般財形貯蓄」「年金財形貯蓄」「住宅財形貯蓄」の金額を必ず読み取ること。
      これらは控除項目の横に並んでいるので見落とさないこと。

    {
      "doc_type": "salary" or "bonus" or "adjustment" or "year_end_adjustment",
      "year_month": "YYYY-MM（対象年月。賞与は支給月、年末調整は12月）",
      "gross_salary": 総支給額（月例給与: 基本給+手当合計、賞与: 賞与総支給額）,
      "basic_salary": 基本給（月例給与のみ。賞与・年末調整は0）,
      "allowances": 各種手当の合計（月例給与のみ）,
      "health_insurance": 健康保険料（該当なしは0）,
      "pension_insurance": 厚生年金保険料（該当なしは0）,
      "employment_insurance": 雇用保険料（該当なしは0）,
      "social_insurance": 社会保険料合計（健康保険+厚生年金+雇用保険。個別値が取れない場合のみ合計値を入れる。個別値が取れた場合は 3項目の合計と一致させること）,
      "income_tax": 所得税（源泉徴収税額）,
      "resident_tax": 住民税,
      "other_deduction": その他の控除合計（財形貯蓄は含めない）,
      "take_home": 差引支給額（＝手取り。差引受取額とも呼ばれる。総支給額から控除合計を引いた金額）,
      "account_1_name": "第1口座の振込先金融機関名（共済支部名など。記載がなければ空文字）",
      "account_1_amount": 第1口座振込額（記載がなければ0。第1・第2口座の記載がない場合、差引支給額と同額にしてください）,
      "account_2_name": "第2口座の振込先金融機関名（記載がなければ空文字）",
      "account_2_amount": 第2口座振込額（記載がなければ0）,
      "account_3_name": "第3口座の金融機関名",
      "account_3_amount": 第3口座への振込金額,
      "zaikei_general": 一般財形貯蓄の金額（該当なしは0）,
      "zaikei_pension": 年金財形貯蓄の金額（該当なしは0）,
      "zaikei_housing": 住宅財形貯蓄の金額（該当なしは0）,
      "annual_income": 年間給与収入（年末調整・源泉徴収票の場合のみ。それ以外は0）,
      "annual_tax_withheld": 源泉徴収税額・年税額（年末調整の場合のみ）,
      "annual_social_insurance": 社会保険料等の年間合計（年末調整の場合のみ）,
      "year_end_refund": 年末調整の還付金額（過納付の場合プラス、不足の場合マイナス。該当なしは0）
    }

    複数ページ（複数月分）がある場合は、ページごとに1つのJSONオブジェクトを作成し、JSON配列 [...] で出力してください。
    1ページのみの場合も配列 [{...}] で出力してください。
    JSONのみ出力してください。説明は不要です。"""

                        for i, pf in enumerate(payslip_files):
                            progress.progress((i + 1) / len(payslip_files), text=f"読み取り中... ({i+1}/{len(payslip_files)}) {pf.name}")
                            try:
                                file_bytes = pf.read()
                                suffix = Path(pf.name).suffix.lower()

                                if suffix == ".pdf":
                                    import pdfplumber
                                    from io import BytesIO
                                    pdf = pdfplumber.open(BytesIO(file_bytes))
                                    # まずテキスト抽出を試みる
                                    text = "\n".join(page.extract_text() or "" for page in pdf.pages).strip()
                                    if len(text) > 50:
                                        # テキストベースで解析
                                        api_content = prompt + "\n\n【給与明細テキスト】\n" + text
                                        response = call_gemini_with_retry(client, api_content)
                                    else:
                                        # テキスト抽出できない（スキャンPDF）→ ページを画像化してGemini Visionに送信
                                        page_images = []
                                        for pg in pdf.pages:
                                            pg_img = pg.to_image(resolution=400)
                                            page_images.append(pg_img.original)  # PIL Image
                                        api_content = [prompt] + page_images
                                        response = call_gemini_with_retry(client, api_content)
                                    pdf.close()
                                else:
                                    from PIL import Image
                                    import io
                                    api_content = [prompt, Image.open(io.BytesIO(file_bytes))]
                                    response = call_gemini_with_retry(client, api_content)

                                # JSON配列 or 単一オブジェクトを抽出
                                resp_text = response.text
                                arr_match = _re.search(r'\[[\s\S]*\]', resp_text)
                                if arr_match:
                                    try:
                                        parsed_list = json.loads(arr_match.group())
                                        if isinstance(parsed_list, list):
                                            for p in parsed_list:
                                                p["_filename"] = pf.name
                                                all_parsed.append(p)
                                        else:
                                            parsed_list["_filename"] = pf.name
                                            all_parsed.append(parsed_list)
                                    except json.JSONDecodeError:
                                        # 配列パース失敗時は単一オブジェクトにフォールバック
                                        json_match = _re.search(r'\{[\s\S]*?\}', resp_text)
                                        if json_match:
                                            parsed = json.loads(json_match.group())
                                            parsed["_filename"] = pf.name
                                            all_parsed.append(parsed)
                                        else:
                                            all_parsed.append({"_filename": pf.name, "_error": "解析結果なし"})
                                else:
                                    json_match = _re.search(r'\{[\s\S]*?\}', resp_text)
                                    if json_match:
                                        parsed = json.loads(json_match.group())
                                        parsed["_filename"] = pf.name
                                        all_parsed.append(parsed)
                                    else:
                                        all_parsed.append({"_filename": pf.name, "_error": "解析結果なし"})
                            except Exception as e:
                                all_parsed.append({"_filename": pf.name, "_error": str(e)})

                        progress.empty()
                        st.session_state._income_payslip_results = all_parsed
                        ok_count = sum(1 for r in all_parsed if "_error" not in r)
                        st.success(f"✓ {ok_count}/{len(all_parsed)}件の読み取り完了")
                        st.rerun()

                # 読み取り結果の表示と一括反映
                results = st.session_state.get("_income_payslip_results", [])
                if results:
                    st.markdown("##### 📋 読み取り結果")
                    # エラーを表示
                    for r in results:
                        if "_error" in r:
                            st.error(f"❌ {r['_filename']}: {r['_error']}")

                    # 成功分をテーブルで編集可能に表示
                    ok_results = [r for r in results if "_error" not in r]
                    if ok_results:
                        # 書類種別と振込情報を表示
                        DOC_TYPE_LABELS = {"salary": "📄 月例給与", "bonus": "🎉 賞与", "adjustment": "📋 差額", "year_end_adjustment": "📝 年末調整"}
                        for r in ok_results:
                            dt = r.get("doc_type", "salary")
                            label = DOC_TYPE_LABELS.get(dt, f"📄 {dt}")
                            info_parts = [f"**{label}** ({r.get('year_month', '?')})"]
                            a1n = r.get("account_1_name", "")
                            a1a = int(r.get("account_1_amount", 0))
                            a2n = r.get("account_2_name", "")
                            a2a = int(r.get("account_2_amount", 0))
                            _th_raw = r.get("take_home", 0)
                            info_parts.append(f"手取り(差引支給額): ¥{int(_th_raw):,}")
                            if a1n: info_parts.append(f"{a1n}: ¥{a1a:,}")
                            if a2n: info_parts.append(f"{a2n}: ¥{a2a:,}")
                            if dt == "year_end_adjustment":
                                refund = int(r.get("year_end_refund", 0))
                                if refund != 0:
                                    info_parts.append(f"還付金: ¥{refund:,}" if refund > 0 else f"不足額: ¥{abs(refund):,}")
                            st.info(" / ".join(info_parts))

                        # デバッグ: Gemini生データ確認用
                        with st.expander("🔍 AI読み取り生データ（トラブルシュート用）", expanded=False):
                            for r in ok_results:
                                st.json({k: v for k, v in r.items() if not k.startswith("_")})

                        edit_rows = []
                        for r in ok_results:
                            dt = r.get("doc_type", "salary")
                            type_label = {"salary": "給与", "bonus": "賞与", "adjustment": "差額", "year_end_adjustment": "年末調整"}.get(dt, dt)
                            # 社保内訳: 個別値が取れていればそれを使い、なければ social_insurance 合計を健保欄に寄せる（後で手動で配分可能）
                            _r_hi = int(r.get("health_insurance", 0))
                            _r_pi = int(r.get("pension_insurance", 0))
                            _r_ei = int(r.get("employment_insurance", 0))
                            _r_si_total = int(r.get("social_insurance", 0))
                            if (_r_hi + _r_pi + _r_ei) == 0 and _r_si_total > 0:
                                # Gemini が内訳を返さなかった古い/簡易フォーマット → 合計のみ健保欄に入れる
                                _r_hi = _r_si_total
                            _r_take_home = int(r.get("take_home", 0))
                            _r_a1 = int(r.get("account_1_amount", 0))
                            _r_a2 = int(r.get("account_2_amount", 0))
                            _r_zk = int(r.get("zaikei_general", 0)) + int(r.get("zaikei_pension", 0)) + int(r.get("zaikei_housing", 0))
                            # 口座振込額が未記載の場合、手取り全額を第1口座に入れる
                            if _r_a1 == 0 and _r_a2 == 0 and _r_take_home > 0:
                                _r_a1 = _r_take_home
                            # 手取り: take_home（差引支給額）を優先。なければ口座合計+財形で算出
                            _r_hand = _r_take_home if _r_take_home > 0 else (_r_a1 + _r_a2 + _r_zk)
                            edit_rows.append({
                                "反映": True,
                                "種別": type_label,
                                "年月": r.get("year_month", ""),
                                "総支給額": int(r.get("gross_salary", 0)),
                                "基本給": int(r.get("basic_salary", 0)),
                                "手当": int(r.get("allowances", 0)),
                                "健康保険": _r_hi,
                                "厚生年金": _r_pi,
                                "雇用保険": _r_ei,
                                "所得税": int(r.get("income_tax", 0)),
                                "住民税": int(r.get("resident_tax", 0)),
                                "他控除": int(r.get("other_deduction", 0)),
                                "第1口座": _r_a1,
                                "第2口座": _r_a2,
                                "財形": _r_zk,
                                "手取り": _r_hand,
                            })
                        edit_df = pd.DataFrame(edit_rows)
                        edited = st.data_editor(
                            edit_df,
                            column_config={
                                "反映": st.column_config.CheckboxColumn("反映", default=True, width="small"),
                                "種別": st.column_config.SelectboxColumn("種別", options=["給与", "賞与", "差額", "年末調整"], width="small"),
                                "年月": st.column_config.TextColumn("年月", width="small"),
                                "総支給額": st.column_config.NumberColumn("総支給額", format="¥%d"),
                                "基本給": st.column_config.NumberColumn("基本給", format="¥%d"),
                                "手当": st.column_config.NumberColumn("手当", format="¥%d"),
                                "健康保険": st.column_config.NumberColumn("健康保険", format="¥%d", help="健康保険料"),
                                "厚生年金": st.column_config.NumberColumn("厚生年金", format="¥%d", help="厚生年金保険料"),
                                "雇用保険": st.column_config.NumberColumn("雇用保険", format="¥%d", help="雇用保険料"),
                                "所得税": st.column_config.NumberColumn("所得税", format="¥%d"),
                                "住民税": st.column_config.NumberColumn("住民税", format="¥%d"),
                                "他控除": st.column_config.NumberColumn("他控除", format="¥%d"),
                                "第1口座": st.column_config.NumberColumn("第1口座", format="¥%d"),
                                "第2口座": st.column_config.NumberColumn("第2口座", format="¥%d"),
                                "財形": st.column_config.NumberColumn("財形", format="¥%d"),
                                "手取り": st.column_config.NumberColumn("手取り", format="¥%d"),
                            },
                            use_container_width=True,
                            hide_index=True,
                            key="_income_payslip_editor"
                        )

                        selected = edited[edited["反映"] == True]
                        if st.button(f"📥 選択した {len(selected)}件を収入データに反映", type="primary", key="_income_p_apply_all"):
                            saved_count = 0
                            last_ym = None
                            for row_idx, row in selected.iterrows():
                                target_ym = str(row["年月"]).strip()
                                if not target_ym:
                                    continue
                                doc_type_label = str(row.get("種別", "給与"))
                                doc_type = {"給与": "salary", "賞与": "bonus", "差額": "adjustment", "年末調整": "year_end_adjustment"}.get(doc_type_label, "salary")

                                gross = int(row["総支給額"])
                                basic = int(row["基本給"])
                                allow = int(row["手当"])
                                hi = int(row.get("健康保険", 0))
                                pi = int(row.get("厚生年金", 0))
                                ei = int(row.get("雇用保険", 0))
                                si = hi + pi + ei  # 社保合計は3項目の和で算出
                                it = int(row["所得税"])
                                rt = int(row["住民税"])
                                od = int(row["他控除"])
                                acct1 = int(row.get("第1口座", 0))
                                acct2 = int(row.get("第2口座", 0))
                                zaikei_table = int(row.get("財形", 0))
                                th = int(row["手取り"])
                                if gross == 0 and (basic > 0 or allow > 0):
                                    gross = basic + allow
                                total_ded = si + it + rt + od
                                if th == 0 and gross > 0:
                                    th = gross - total_ded

                                # 対応するok_resultsを取得（振込情報+年末調整データ用）
                                matched_pr = None
                                for _pr in ok_results:
                                    if _pr.get("year_month", "").strip() == target_ym:
                                        matched_pr = _pr
                                        break

                                # 財形データを抽出（PDF読み取り結果から）
                                _zk_general = int(matched_pr.get("zaikei_general", 0)) if matched_pr else 0
                                _zk_pension = int(matched_pr.get("zaikei_pension", 0)) if matched_pr else 0
                                _zk_housing = int(matched_pr.get("zaikei_housing", 0)) if matched_pr else 0
                                _zk_total = _zk_general + _zk_pension + _zk_housing

                                if doc_type == "year_end_adjustment":
                                    # 年末調整: 既存の月データに年末調整情報を追記（年間合計のみ保持、月別推定はしない）
                                    existing = _normalize_entry(income_data.get(target_ym, 0))
                                    _yea_ann_income = int(matched_pr.get("annual_income", 0)) if matched_pr else 0
                                    _yea_ann_tax = int(matched_pr.get("annual_tax_withheld", 0)) if matched_pr else 0
                                    _yea_ann_si = int(matched_pr.get("annual_social_insurance", 0)) if matched_pr else 0
                                    _yea_refund = int(matched_pr.get("year_end_refund", 0)) if matched_pr else 0
                                    existing["year_end_adjustment"] = {
                                        "annual_income": _yea_ann_income,
                                        "annual_tax_withheld": _yea_ann_tax,
                                        "annual_social_insurance": _yea_ann_si,
                                        "refund": _yea_refund,
                                    }
                                    # 還付金が手取りに加算される場合
                                    if _yea_refund != 0 and existing.get("take_home", 0) > 0:
                                        existing["take_home"] += _yea_refund
                                    income_data[target_ym] = existing
                                    # セッションの年収のみ更新（税金タブで利用）
                                    if _yea_ann_income > 0:
                                        st.session_state.annual_income = _yea_ann_income
                                elif doc_type == "adjustment":
                                    # 差額: 別キーで保存（月例給与と分離）
                                    adj_key = target_ym + "_adj"
                                    new_entry = {
                                        "doc_type": "adjustment",
                                        "gross_salary": gross,
                                        "basic_salary": basic,
                                        "allowances": allow,
                                        "deductions": {"social_insurance": si, "health_insurance": hi, "pension_insurance": pi, "employment_insurance": ei, "income_tax": it, "resident_tax": rt, "other": od},
                                        "take_home": th,
                                        "zaikei": _zk_total,
                                        "zaikei_detail": {"general": _zk_general, "pension": _zk_pension, "housing": _zk_housing},
                                        "account_distribution": {},
                                    }
                                    if acct1 > 0:
                                        _a1name = _acct_names.get("account_1") or (str(matched_pr.get("account_1_name", "")).strip() if matched_pr else "")
                                        new_entry["account_distribution"]["account_1"] = {"name": _a1name, "amount": acct1}
                                    if acct2 > 0:
                                        _a2name = _acct_names.get("account_2") or (str(matched_pr.get("account_2_name", "")).strip() if matched_pr else "")
                                        new_entry["account_distribution"]["account_2"] = {"name": _a2name, "amount": acct2}
                                    income_data[adj_key] = new_entry
                                elif doc_type == "bonus":
                                    # 賞与: 別キーで保存（月例給与と分離）
                                    bonus_key = target_ym + "_bonus"
                                    new_entry = {
                                        "doc_type": "bonus",
                                        "gross_salary": gross,
                                        "basic_salary": 0,
                                        "allowances": 0,
                                        "deductions": {"social_insurance": si, "health_insurance": hi, "pension_insurance": pi, "employment_insurance": ei, "income_tax": it, "resident_tax": rt, "other": od},
                                        "take_home": th,
                                        "zaikei": _zk_total,
                                        "zaikei_detail": {"general": _zk_general, "pension": _zk_pension, "housing": _zk_housing},
                                        "account_distribution": {},
                                    }
                                    if acct1 > 0:
                                        _a1name = _acct_names.get("account_1") or (str(matched_pr.get("account_1_name", "")).strip() if matched_pr else "")
                                        new_entry["account_distribution"]["account_1"] = {"name": _a1name, "amount": acct1}
                                    if acct2 > 0:
                                        _a2name = _acct_names.get("account_2") or (str(matched_pr.get("account_2_name", "")).strip() if matched_pr else "")
                                        new_entry["account_distribution"]["account_2"] = {"name": _a2name, "amount": acct2}
                                    income_data[bonus_key] = new_entry
                                else:
                                    # 月例給与
                                    new_entry = {
                                        "doc_type": "salary",
                                        "gross_salary": gross,
                                        "basic_salary": basic,
                                        "allowances": allow,
                                        "deductions": {"social_insurance": si, "health_insurance": hi, "pension_insurance": pi, "employment_insurance": ei, "income_tax": it, "resident_tax": rt, "other": od},
                                        "take_home": th,
                                        "zaikei": _zk_total,
                                        "zaikei_detail": {"general": _zk_general, "pension": _zk_pension, "housing": _zk_housing},
                                        "account_distribution": {},
                                    }
                                    # 振込情報: テーブル編集値を優先、なければGemini結果を使用
                                    if acct1 > 0:
                                        _a1name = _acct_names.get("account_1") or (str(matched_pr.get("account_1_name", "")).strip() if matched_pr else "")
                                        new_entry["account_distribution"]["account_1"] = {"name": _a1name, "amount": acct1}
                                    if acct2 > 0:
                                        _a2name = _acct_names.get("account_2") or (str(matched_pr.get("account_2_name", "")).strip() if matched_pr else "")
                                        new_entry["account_distribution"]["account_2"] = {"name": _a2name, "amount": acct2}
                                    if matched_pr:
                                        # 第3口座はテーブルに列がないのでGemini結果から
                                        _a3name = _acct_names.get("account_3") or (str(matched_pr.get("account_3_name", "")).strip() if matched_pr else "")
                                        _a3amount = int(matched_pr.get("account_3_amount", 0))
                                        if _a3amount > 0:
                                            new_entry["account_distribution"]["account_3"] = {"name": _a3name, "amount": _a3amount}
                                    # 既存の口座分け保持
                                    existing_dist = _normalize_entry(income_data.get(target_ym, 0)).get("account_distribution", {})
                                    for _ek, _ev in existing_dist.items():
                                        if _ek not in new_entry["account_distribution"]:
                                            new_entry["account_distribution"][_ek] = _ev
                                    income_data[target_ym] = new_entry

                                last_ym = target_ym
                                saved_count += 1
                            if saved_count > 0:
                                st.session_state.monthly_income_data = income_data
                                # 最後に保存した月を月別詳細の選択月にセット
                                if last_ym:
                                    st.session_state._income_auto_select_month = last_ym
                                # 口座残高へ自動連携
                                _synced = 0
                                for _sr_idx, _sr_row in selected.iterrows():
                                    _sr_ym = str(_sr_row.get("年月", "")).strip()
                                    _sr_dt = str(_sr_row.get("種別", "給与"))
                                    _sr_dtype = {"給与": "salary", "賞与": "bonus", "差額": "adjustment"}.get(_sr_dt, "salary")
                                    _sr_a1 = int(_sr_row.get("第1口座", 0))
                                    _sr_a2 = int(_sr_row.get("第2口座", 0))
                                    if _sr_a1 > 0:
                                        _sync_income_to_bank(_sr_ym, "account_1", _sr_a1, _sr_dtype)
                                        _synced += 1
                                    if _sr_a2 > 0:
                                        _sync_income_to_bank(_sr_ym, "account_2", _sr_a2, _sr_dtype)
                                        _synced += 1
                                if _synced > 0 and _bm:
                                    _bm.save_to_csv()
                                try:
                                    income_path.parent.mkdir(parents=True, exist_ok=True)
                                    with open(income_path, 'w', encoding='utf-8') as f:
                                        json.dump(income_data, f, ensure_ascii=False, indent=2)
                                    st.session_state._income_payslip_results = []
                                    _sync_msg = f"（{_synced}件を口座残高に連携）" if _synced > 0 else ""
                                    st.success(f"✓ {saved_count}件の収入データを保存しました{_sync_msg}")
                                    st.rerun()
                                except IOError:
                                    st.error("保存に失敗しました")
                            else:
                                st.warning("反映する年月が指定されていません")


    with income_sub2:
        # === 収入データ一覧（テーブル中心のUI） ===
        st.markdown("#### 📄 収入データ一覧")
        st.caption("PDFから取り込んだデータをここで一覧・編集できます")

        # === サマリー ===
        salary_total = sum(_get_take_home(v) for k, v in income_data.items() if not k.endswith("_bonus") and not k.endswith("_adj"))
        bonus_total = sum(_get_take_home(v) for k, v in income_data.items() if k.endswith("_bonus"))
        adj_total = sum(_get_take_home(v) for k, v in income_data.items() if k.endswith("_adj"))
        total_income = salary_total + bonus_total + adj_total
        filled_months = len([k for k, v in income_data.items() if not k.endswith("_bonus") and _get_take_home(v) > 0])
        avg_income = salary_total / filled_months if filled_months > 0 else 0
        cm1, cm2, cm3, cm4 = st.columns(4)
        cm1.metric("給与手取り合計", f"¥{salary_total:,.0f}")
        cm2.metric("賞与手取り合計", f"¥{bonus_total:,.0f}")
        cm3.metric("総収入（手取り）", f"¥{total_income:,.0f}")
        cm4.metric("月平均給与 / 入力月数", f"¥{avg_income:,.0f} / {filled_months}ヶ月")

        st.markdown("---")

        # === 編集可能テーブル ===
        edit_rows = []
        row_keys = []
        for key in sorted(income_data.keys()):
            val = income_data[key]
            entry_d = _normalize_entry(val)
            is_bonus = key.endswith("_bonus")
            is_adj = key.endswith("_adj")
            ym_display = key.replace("_bonus", "").replace("_adj", "")
            doc_type = entry_d.get("doc_type", "bonus" if is_bonus else "adjustment" if is_adj else "salary")
            if doc_type == "bonus" or is_bonus:
                type_label = "賞与"
            elif doc_type == "adjustment" or is_adj:
                type_label = "差額"
            elif entry_d.get("year_end_adjustment"):
                type_label = "年末調整"
            else:
                type_label = "給与"
            ded = entry_d.get("deductions", {})
            acct = entry_d.get("account_distribution", {})
            a1 = acct.get("account_1", {})
            a2 = acct.get("account_2", {})
            a1_amount = int(a1.get("amount", 0))
            a2_amount = int(a2.get("amount", 0))
            zaikei = int(entry_d.get("zaikei", 0))
            th = int(entry_d.get("take_home", 0))
            # 口座分配データがない場合、手取りを第1口座に入れる
            if a1_amount == 0 and a2_amount == 0 and zaikei == 0 and th > 0:
                a1_amount = th
            edit_rows.append({
                "年月": ym_display,
                "種別": type_label,
                "総支給額": int(entry_d.get("gross_salary", 0)),
                "基本給": int(entry_d.get("basic_salary", 0)),
                "手当": int(entry_d.get("allowances", 0)),
                "社保": int(ded.get("social_insurance", 0)),
                "所得税": int(ded.get("income_tax", 0)),
                "住民税": int(ded.get("resident_tax", 0)),
                "他控除": int(ded.get("other", 0)),
                "第1口座": a1_amount,
                "第2口座": a2_amount,
                "財形": zaikei,
                "手取り": th if th > 0 else (a1_amount + a2_amount + zaikei),
            })
            row_keys.append(key)

        if edit_rows:
            edit_df = pd.DataFrame(edit_rows)
            edit_df.insert(0, "削除", False)
            # 横スクロール対応: 全列を横一列に表示
            st.markdown('<style>div[data-testid="stDataEditor"] { overflow-x: auto !important; }</style>', unsafe_allow_html=True)
            edited = st.data_editor(
                edit_df,
                column_config={
                    "削除": st.column_config.CheckboxColumn("🗑️", default=False, width="small"),
                    "年月": st.column_config.TextColumn("年月", width="small"),
                    "種別": st.column_config.SelectboxColumn("種別", options=["給与", "賞与", "差額", "年末調整"], width="small"),
                    "総支給額": st.column_config.NumberColumn("総支給額", format="¥%d", width="small"),
                    "基本給": st.column_config.NumberColumn("基本給", format="¥%d", width="small"),
                    "手当": st.column_config.NumberColumn("手当", format="¥%d", width="small"),
                    "社保": st.column_config.NumberColumn("社保", format="¥%d", width="small"),
                    "所得税": st.column_config.NumberColumn("所得税", format="¥%d", width="small"),
                    "住民税": st.column_config.NumberColumn("住民税", format="¥%d", width="small"),
                    "他控除": st.column_config.NumberColumn("他控除", format="¥%d", width="small"),
                    "第1口座": st.column_config.NumberColumn("第1口座", format="¥%d", width="small"),
                    "第2口座": st.column_config.NumberColumn("第2口座", format="¥%d", width="small"),
                    "財形": st.column_config.NumberColumn("財形", format="¥%d", width="small"),
                    "手取り": st.column_config.NumberColumn("手取り", format="¥%d", disabled=True, width="small"),
                },
                use_container_width=True, hide_index=True, num_rows="dynamic",
                key="_income_data_editor"
            )

            col_s1, col_s2, col_s3 = st.columns([1, 1, 3])
            with col_s1:
                if st.button("💾 変更を保存", type="primary", key="_income_save_edits"):
                    for i, (_, row) in enumerate(edited.iterrows()):
                        if i >= len(row_keys):
                            ym = str(row.get("年月", "")).strip()
                            if not ym: continue
                            new_key = ym + ("_bonus" if row.get("種別") == "賞与" else "_adj" if row.get("種別") == "差額" else "")
                        else:
                            new_key = row_keys[i]
                        gross = int(row.get("総支給額", 0))
                        basic = int(row.get("基本給", 0))
                        allow = int(row.get("手当", 0))
                        si = int(row.get("社保", 0))
                        it = int(row.get("所得税", 0))
                        rt = int(row.get("住民税", 0))
                        od = int(row.get("他控除", 0))
                        a1a = int(row.get("第1口座", 0))
                        a2a = int(row.get("第2口座", 0))
                        zaikei = int(row.get("財形", 0))
                        th = a1a + a2a + zaikei
                        if gross == 0 and (basic + allow) > 0: gross = basic + allow
                        if th == 0 and gross > 0: th = gross - (si + it + rt + od)
                        existing = _normalize_entry(income_data.get(new_key, 0))
                        # 財形の内訳を保持（既存の内訳比率で按分、なければ全額を一般財形に）
                        old_zk_detail = existing.get("zaikei_detail", {})
                        old_zk_total = existing.get("zaikei", 0)
                        if zaikei > 0 and old_zk_total > 0 and old_zk_detail:
                            ratio = zaikei / old_zk_total if old_zk_total else 1
                            zk_detail = {
                                "general": round(old_zk_detail.get("general", 0) * ratio),
                                "pension": round(old_zk_detail.get("pension", 0) * ratio),
                                "housing": round(old_zk_detail.get("housing", 0) * ratio),
                            }
                        elif zaikei > 0:
                            zk_detail = {"general": zaikei, "pension": 0, "housing": 0}
                        else:
                            zk_detail = {"general": 0, "pension": 0, "housing": 0}
                        existing.update({"gross_salary": gross, "basic_salary": basic, "allowances": allow,
                            "deductions": {"social_insurance": si, "income_tax": it, "resident_tax": rt, "other": od},
                            "take_home": th, "zaikei": zaikei, "zaikei_detail": zk_detail})
                        # 口座分配を保存（設定値の口座名を優先）
                        old_dist = existing.get("account_distribution", {})
                        a1_name = _acct_names.get("account_1") or old_dist.get("account_1", {}).get("name", "")
                        a2_name = _acct_names.get("account_2") or old_dist.get("account_2", {}).get("name", "")
                        acct_dist = {}
                        if a1a > 0: acct_dist["account_1"] = {"name": a1_name, "amount": a1a}
                        if a2a > 0: acct_dist["account_2"] = {"name": a2_name, "amount": a2a}
                        existing["account_distribution"] = acct_dist
                        income_data[new_key] = existing
                    st.session_state.monthly_income_data = income_data
                    try:
                        with open(income_path, 'w', encoding='utf-8') as f:
                            json.dump(income_data, f, ensure_ascii=False, indent=2)
                        st.success("✓ 収入データを保存しました")
                        st.rerun()
                    except IOError:
                        st.error("保存に失敗しました")
            with col_s2:
                delete_count = int(edited['削除'].sum()) if '削除' in edited.columns else 0
                if st.button(f"🗑️ 選択削除（{delete_count}件）", key="_income_del_selected", disabled=delete_count == 0, type="secondary"):
                    del_indices = edited[edited['削除'] == True].index.tolist()
                    for i in sorted(del_indices, reverse=True):
                        if i < len(row_keys): income_data.pop(row_keys[i], None)
                    st.session_state.monthly_income_data = income_data
                    try:
                        with open(income_path, 'w', encoding='utf-8') as f:
                            json.dump(income_data, f, ensure_ascii=False, indent=2)
                        st.success(f"✓ {delete_count}件を削除しました")
                        st.rerun()
                    except IOError:
                        st.error("削除に失敗しました")
            with col_s3:
                st.caption("テーブル上で直接編集 → 「変更を保存」。行追加も可能です。")
        else:
            st.info("収入データがありません。上の給与明細PDF読み取りからデータを追加してください。")

        st.markdown("---")

        # === 収支比較グラフ ===
        st.markdown("#### 📊 月別 収入 vs 支出")
        monthly_expense = analyzer.monthly_spending()
        month_labels = [str(m) for m in monthly_expense.index]
        expense_values = monthly_expense.values.tolist()
        income_values = [
            _get_take_home(income_data.get(m, 0))
            + _get_take_home(income_data.get(m + "_bonus", 0))
            + _get_take_home(income_data.get(m + "_adj", 0))
            for m in month_labels
        ]
        fig = go.Figure()
        fig.add_trace(go.Bar(name='収入', x=month_labels, y=income_values, marker_color='#2196F3'))
        fig.add_trace(go.Bar(name='支出', x=month_labels, y=expense_values, marker_color='#FF5252'))
        fig.update_layout(barmode='group', xaxis_title='月', yaxis_title='金額（円）', yaxis_tickformat=',', legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1), height=450)
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### 💹 月別収支差額")
        balance_values = [inc - exp for inc, exp in zip(income_values, expense_values)]
        colors = ['#4CAF50' if b >= 0 else '#FF5252' for b in balance_values]
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(x=month_labels, y=balance_values, marker_color=colors))
        fig2.add_hline(y=0, line_dash="dash", line_color="gray")
        fig2.update_layout(xaxis_title='月', yaxis_title='収支差額（円）', yaxis_tickformat=',', height=350)
        st.plotly_chart(fig2, use_container_width=True)



def show_graphs_tab(analyzer: BudgetAnalyzer, visualizer: BudgetVisualizer) -> None:
    """グラフタブ"""
    tab1, tab2, tab3 = st.tabs(
        ["📊 月別推移", "📈 トレンド", "📚 詳細ダッシュボード"]
    )

    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### 月別支出推移")
            st.plotly_chart(visualizer.monthly_bar_chart(), use_container_width=True)
        with col2:
            st.markdown("#### 月別カテゴリ構成")
            st.plotly_chart(visualizer.monthly_category_stacked(), use_container_width=True)

    with tab2:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### 日別支出推移")
            st.plotly_chart(visualizer.daily_spending_line(), use_container_width=True)
        with col2:
            st.markdown("#### 理想比率との比較")
            st.plotly_chart(visualizer.comparison_bar_chart(), use_container_width=True)

    with tab3:
        budget_value = st.session_state.budget
        if budget_value:
            st.markdown("#### 予算達成状況")
            st.caption(
                f"サイドバーで設定した月の目標予算（¥{budget_value:,.0f}）に対する実際の支出割合です。"
                " 🟢 90%以下＝順調 / 🟡 90〜100%＝注意 / 🔴 100%超＝予算オーバー"
            )
            st.plotly_chart(
                visualizer.spending_gauge(budget=budget_value),
                use_container_width=True,
            )
        else:
            st.info("サイドバーの「月の目標予算（円）」を設定すると、予算達成ゲージが表示されます。")
        st.markdown("#### コンパクトダッシュボード")
        st.plotly_chart(visualizer.dashboard(), use_container_width=True)


def show_advice_tab(analyzer: BudgetAnalyzer, advisor: FinancialAdvisor) -> None:
    """アドバイスタブ"""

    # プロフィール・履歴管理セクション
    with st.expander("👤 プロフィール設定", expanded=False):
        profile = FinancialAdvisor.load_profile()
        summary = FinancialAdvisor.load_history_summary()

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("##### 財務目標")
            goals_text = st.text_area(
                "目標（1行に1つ）",
                value="\n".join(profile.get("goals", [])),
                height=100,
                key="profile_goals",
                placeholder="例:\n老後資金2000万円\n住宅購入の頭金500万円"
            )

            st.markdown("##### 予定しているライフイベント")
            events_text = st.text_area(
                "ライフイベント（1行に1つ）",
                value="\n".join(profile.get("life_events", [])),
                height=80,
                key="profile_events",
                placeholder="例:\n2027年 結婚\n2030年 マイホーム購入"
            )

        with col2:
            st.markdown("##### 気になっていること")
            concerns_text = st.text_area(
                "懸念・関心事（1行に1つ）",
                value="\n".join(profile.get("concerns", [])),
                height=100,
                key="profile_concerns",
                placeholder="例:\n保険が適切か分からない\n節税対策をしたい"
            )

            st.markdown("##### メモ")
            notes_text = st.text_area(
                "その他メモ",
                value=profile.get("notes", ""),
                height=80,
                key="profile_notes",
                placeholder="アドバイザーに知っておいてほしいこと"
            )

        # 保存ボタン
        if st.button("💾 プロフィールを保存", key="save_profile"):
            new_profile = {
                "name": "ユーザー",
                "goals": [g.strip() for g in goals_text.split("\n") if g.strip()],
                "concerns": [c.strip() for c in concerns_text.split("\n") if c.strip()],
                "life_events": [e.strip() for e in events_text.split("\n") if e.strip()],
                "notes": notes_text.strip(),
                "preferences": profile.get("preferences", {}),
                "created_at": profile.get("created_at"),
            }
            if FinancialAdvisor.save_profile(new_profile):
                st.success("プロフィールを保存しました")
            else:
                st.error("保存に失敗しました")

        # 履歴要約セクション
        st.markdown("---")
        st.markdown("##### 📝 会話履歴の要約")

        if summary.get("last_updated"):
            st.caption(f"最終更新: {summary['last_updated'][:10]}")

        if summary.get("key_insights"):
            st.markdown("**これまでに分かったこと:**")
            for insight in summary["key_insights"][:5]:
                st.markdown(f"- {html.escape(insight)}")

        if summary.get("action_items"):
            st.markdown("**検討中のアクション:**")
            for action in summary["action_items"][:3]:
                st.markdown(f"- {html.escape(action)}")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 履歴から要約を生成", key="gen_summary"):
                chat_history = st.session_state.get("chat_history", [])
                if chat_history:
                    with st.spinner("履歴を分析中..."):
                        result = advisor.generate_history_summary(chat_history)
                    if result and not result.startswith("[Error]"):
                        st.success("要約を生成・保存しました")
                        st.rerun()
                    else:
                        st.error(f"要約生成に失敗: {result}")
                else:
                    st.warning("チャット履歴がありません")
        with col2:
            if st.button("🗑️ 要約をクリア", key="clear_summary"):
                hs_path = get_history_summary_path()
                if hs_path.exists():
                    hs_path.unlink()
                    st.success("要約をクリアしました")
                    st.rerun()

    rule_advice = advisor.generate_rule_based_advice()

    st.markdown("### ルールベース診断")
    st.info(rule_advice.summary)

    # カテゴリ別
    st.markdown("#### カテゴリ別コメント")
    over_cols = st.columns(2)
    with over_cols[0]:
        st.markdown("**注意が必要なカテゴリ（超過）**")
        for w in rule_advice.category_warnings:
            if w["status"] != "超過":
                continue
            st.markdown(
                f"- **{html.escape(w['category'])}**: 実際 {w['actual_ratio']*100:.1f}% / "
                f"理想 {w['ideal_ratio']*100:.1f}%  \n"
                f"  {html.escape(w['message'])}"
            )
    with over_cols[1]:
        st.markdown("**良い傾向のカテゴリ（節約）**")
        for w in rule_advice.category_warnings:
            if w["status"] != "節約":
                continue
            st.markdown(
                f"- **{html.escape(w['category'])}**: 実際 {w['actual_ratio']*100:.1f}% / "
                f"理想 {w['ideal_ratio']*100:.1f}%  \n"
                f"  {html.escape(w['message'])}"
            )

    # 貯蓄ポテンシャル
    st.markdown("#### 貯蓄ポテンシャル")
    savings = rule_advice.savings_analysis
    income = advisor.monthly_income
    if income is not None and savings.get("current_savings_rate") is not None:
        st.write(
            f"- 推定月収: ¥{income:,.0f}\n"
            f"- 現在の月平均支出: ¥{savings['current_monthly_spending']:,.0f}\n"
            f"- 現在の貯蓄率（推定）: {savings['current_savings_rate']*100:.1f}%"
        )
        if savings.get("potential_additional_savings") is not None:
            st.write(
                f"- カテゴリ見直しにより、理論上は最大で "
                f"¥{savings['potential_additional_savings']:,.0f} 程度の追加余力が見込めます。"
            )

        if savings.get("reduction_targets"):
            st.markdown("**特に見直し候補となるカテゴリ**")
            for t in savings["reduction_targets"][:5]:
                st.markdown(
                    f"- **{html.escape(t['category'])}**: 理想を {t['excess_ratio']*100:.1f}% ポイント超過 "
                    f"（約 ¥{t['excess_amount']:,.0f}）"
                )
    else:
        st.info("月収が未設定のため、詳細な貯蓄ポテンシャルの算出はスキップしています。")

    # 異常支出
    st.markdown("#### 統計的に目立つ高額支出")
    if rule_advice.anomalies:
        for a in rule_advice.anomalies[:10]:
            date_str = (
                a["date"].strftime("%Y-%m-%d")
                if hasattr(a["date"], "strftime")
                else str(a["date"])
            )
            st.markdown(
                f"- {date_str} / {html.escape(a['category'])} / ¥{a['amount']:,.0f} / {html.escape(a.get('memo',''))}"
            )
    else:
        st.write("特に目立った異常値は検出されませんでした。")

    # AI による自然文アドバイス
    if st.session_state.use_claude:
        st.markdown("---")
        ai_provider = st.session_state.get("ai_provider", "gemini")
        provider_name = "Gemini" if ai_provider == "gemini" else "Claude"
        st.markdown(f"### 🤖 総合ファイナンシャルアドバイス")
        st.caption("家計・資産・税金・保険・年末調整・口座情報を統合して分析します")

        # 総合アドバイス用画像アップロード
        advice_images = st.file_uploader(
            "📎 参考画像を添付（任意）",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key="advice_image_upload",
            help="保険証券・投資明細・通帳など、アドバイスの参考にしたい画像を添付できます"
        )
        if advice_images:
            cols = st.columns(min(len(advice_images), 4))
            for i, img in enumerate(advice_images):
                with cols[i % len(cols)]:
                    st.image(img, caption=img.name, width=120)

        # 総合アドバイス生成ボタン
        col_adv1, col_adv2 = st.columns(2)
        with col_adv1:
            if st.button("📊 総合アドバイスを生成（履歴込み）", type="primary"):
                with st.spinner(f"チャット履歴と全データを統合して {provider_name} で分析中..."):
                    chat_hist = st.session_state.get("chat_history", [])
                    advice_imgs_data = []
                    if advice_images:
                        mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}
                        for img in advice_images:
                            ext = img.name.rsplit('.', 1)[-1].lower()
                            advice_imgs_data.append({"bytes": img.getvalue(), "mime_type": mime_map.get(ext, "image/png")})
                    if ai_provider == "gemini":
                        ai_text = advisor.generate_comprehensive_advice(
                            chat_history=chat_hist, rule_based=rule_advice,
                            images=advice_imgs_data if advice_imgs_data else None)
                    else:
                        ai_text = advisor.generate_ai_advice(rule_based=rule_advice)
                if ai_text:
                    if ai_text.startswith("[") and "Error]" in ai_text:
                        st.error(f"{provider_name} API エラー: {ai_text}")
                    else:
                        st.session_state.last_comprehensive_advice = ai_text
                        st.rerun()
                else:
                    st.warning(f"{provider_name} API からのアドバイス取得に失敗しました。")
        with col_adv2:
            if st.button("📋 簡易アドバイス（履歴なし）"):
                with st.spinner(f"{provider_name} からアドバイスを取得中..."):
                    if ai_provider == "gemini":
                        ai_text = advisor.generate_gemini_advice(rule_based=rule_advice)
                    else:
                        ai_text = advisor.generate_ai_advice(rule_based=rule_advice)
                if ai_text:
                    if ai_text.startswith("[") and "Error]" in ai_text:
                        st.error(f"{provider_name} API エラー: {ai_text}")
                    else:
                        st.session_state.last_comprehensive_advice = ai_text
                        st.rerun()

        # 前回生成したアドバイスを表示
        if st.session_state.get("last_comprehensive_advice"):
            st.markdown(st.session_state.last_comprehensive_advice)

        st.markdown("---")
        st.markdown("### 💬 AIファイナンシャルプランナー")
        st.caption("家計・資産・税金・保険・保険すべてを踏まえてアドバイスします。何でもご相談ください。")

        # チャット履歴の初期化（保存データがあれば読み込み）
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = FinancialAdvisor.load_chat_history()
        if "chat_history_loaded" not in st.session_state:
            st.session_state.chat_history_loaded = True

        # セッション開始時にサマリーがなければ履歴から自動生成
        if "summary_initialized" not in st.session_state:
            st.session_state.summary_initialized = True
            summary = FinancialAdvisor.load_history_summary()
            if not summary.get("key_insights") and st.session_state.chat_history:
                with st.spinner("過去の会話履歴をサマリー化中..."):
                    advisor.generate_history_summary(st.session_state.chat_history)

        # チャット履歴管理ボタン
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("💾 履歴を保存"):
                if FinancialAdvisor.save_chat_history(st.session_state.chat_history):
                    st.success("チャット履歴を保存しました")
                else:
                    st.error("保存に失敗しました")
        with col2:
            if st.button("📂 履歴を読み込み"):
                loaded = FinancialAdvisor.load_chat_history()
                if loaded:
                    st.session_state.chat_history = loaded
                    st.success(f"{len(loaded)}件の履歴を読み込みました")
                    st.rerun()
                else:
                    st.info("保存された履歴がありません")
        with col3:
            if st.button("🗑️ 画面クリア"):
                st.session_state.chat_history = []
                st.rerun()

        # チャット履歴の表示
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                if message.get("image_names"):
                    st.caption("📎 " + ", ".join(message["image_names"]))
                elif message.get("image_name"):
                    st.caption(f"📎 {message['image_name']}")
                st.markdown(message["content"])

        # ユーザー入力（Cmd+Enter / Ctrl+Enter で送信）
        with st.form("chat_form", clear_on_submit=True):
            prompt = st.text_area(
                "質問を入力（⌘+Enter で送信）",
                placeholder="例: 貯蓄を増やすには？ / 節税対策は？ / 保険の見直しは必要？",
                height=80, key="chat_text_input", label_visibility="collapsed"
            )
            uploaded_images = st.file_uploader(
                "📎 画像を添付（レシート・明細書・グラフなど）",
                type=["png", "jpg", "jpeg", "webp", "gif"],
                accept_multiple_files=True,
                help="複数画像を添付可能。AIが内容を分析します。",
                label_visibility="collapsed"
            )
            if uploaded_images:
                cols = st.columns(min(len(uploaded_images), 4))
                for i, img in enumerate(uploaded_images):
                    with cols[i % len(cols)]:
                        st.image(img, caption=img.name, width=120)
            submitted = st.form_submit_button("📨 送信（⌘+Enter）", type="primary", use_container_width=True)

        if submitted and prompt and prompt.strip():
            prompt = prompt.strip()
            # 画像データ取得（複数対応）
            images_data = []
            image_names = []
            mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                        "webp": "image/webp", "gif": "image/gif"}
            if uploaded_images:
                for img in uploaded_images:
                    ext = img.name.rsplit('.', 1)[-1].lower()
                    images_data.append({
                        "bytes": img.getvalue(),
                        "mime_type": mime_map.get(ext, "image/png"),
                    })
                    image_names.append(img.name)

            # ユーザーメッセージを表示・保存
            with st.chat_message("user"):
                if image_names:
                    st.caption("📎 " + ", ".join(image_names))
                st.markdown(prompt)

            # AI からの回答を取得
            with st.chat_message("assistant"):
                with st.spinner("データを分析中..."):
                    if ai_provider == "gemini":
                        response = advisor.gemini_chat(
                            prompt, st.session_state.chat_history,
                            images=images_data if images_data else None)
                    else:
                        response = advisor.chat(prompt, st.session_state.chat_history)

                if response:
                    if response.startswith("[") and "Error]" in response:
                        st.error(f"{provider_name} API エラー: {response}")
                    else:
                        st.markdown(response)
                        # 履歴に追加（画像名を記録、画像バイナリは保存しない）
                        user_msg = {"role": "user", "content": prompt}
                        if image_names:
                            user_msg["image_names"] = image_names
                        st.session_state.chat_history.append(user_msg)
                        st.session_state.chat_history.append({"role": "assistant", "content": response})
                        # 自動保存
                        FinancialAdvisor.save_chat_history(st.session_state.chat_history)
                        # 5往復ごとにサマリーを自動更新
                        msg_count = len(st.session_state.chat_history)
                        if msg_count > 0 and msg_count % 10 == 0:
                            advisor.generate_history_summary(st.session_state.chat_history)
                else:
                    st.error("回答の取得に失敗しました。APIキーを確認してください。")


def _show_loan_tab() -> None:
    """ローン・負債管理サブタブ"""
    import json

    st.markdown("#### 🏠 ローン・負債管理")
    st.caption("住宅ローン・車ローン等の管理。月々と賞与月の引落し額、引落口座を設定できます。")

    loan_path = get_data_dir() / "loans.json"
    if "loans_data" not in st.session_state:
        if loan_path.exists():
            try:
                with open(loan_path, 'r', encoding='utf-8') as f:
                    st.session_state.loans_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                st.session_state.loans_data = []
        else:
            st.session_state.loans_data = []

    loans = st.session_state.loans_data

    # 口座一覧取得
    bm = st.session_state.get("bank_manager")
    account_options = {}
    if bm and bm.accounts_df is not None and not bm.accounts_df.empty:
        for _, acc in bm.accounts_df.iterrows():
            if acc.get('account_type') != 'credit_card':
                account_options[acc['account_id']] = acc.get('name', acc['account_id'])

    # --- ローン一覧 ---
    if loans:
        total_monthly = sum(l.get('monthly_amount', 0) for l in loans)
        total_balance = sum(l.get('remaining_balance', 0) for l in loans)

        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("ローン残高合計", f"¥{total_balance:,.0f}")
        col_m2.metric("月々返済合計", f"¥{total_monthly:,.0f}")
        col_m3.metric("年間返済額", f"¥{total_monthly * 12 + sum(l.get('bonus_amount', 0) * 2 for l in loans):,.0f}")

        st.markdown("---")

        for i, loan in enumerate(loans):
            acc_name = account_options.get(loan.get('account_id', ''), '未設定')
            bonus_months_str = '・'.join([f"{m}月" for m in loan.get('bonus_months', [6, 12])])

            with st.expander(f"📄 {html.escape(loan['name'])}（残高: ¥{loan.get('remaining_balance', 0):,.0f}）", expanded=False):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"""
| 項目 | 内容 |
|------|------|
| ローン名 | {html.escape(loan['name'])} |
| 残高 | ¥{loan.get('remaining_balance', 0):,.0f} |
| 月々返済額 | ¥{loan.get('monthly_amount', 0):,.0f} |
| 賞与月返済額 | ¥{loan.get('bonus_amount', 0):,.0f} |
| 賞与月 | {bonus_months_str} |
| 引落口座 | {html.escape(acc_name)} |
| 金利 | {loan.get('interest_rate', 0):.2f}% |
""")
                with col2:
                    st.markdown(f"""
| 項目 | 内容 |
|------|------|
| 借入額 | ¥{loan.get('original_amount', 0):,.0f} |
| 借入日 | {loan.get('start_date', '未設定')} |
| 完済予定 | {loan.get('end_date', '未設定')} |
""")
                    # 返済進捗
                    original = loan.get('original_amount', 0)
                    remaining = loan.get('remaining_balance', 0)
                    if original > 0:
                        progress = (original - remaining) / original
                        st.progress(min(progress, 1.0), text=f"返済進捗: {progress * 100:.1f}%")

                col_btn1, col_btn2, _ = st.columns([1, 1, 3])
                with col_btn1:
                    if st.button("✏️ 編集", key=f"loan_edit_{i}"):
                        st.session_state[f"loan_editing_{i}"] = True
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ 削除", key=f"loan_del_{i}", type="secondary"):
                        st.session_state.loans_data.pop(i)
                        try:
                            with open(loan_path, 'w', encoding='utf-8') as f:
                                json.dump(st.session_state.loans_data, f, ensure_ascii=False, indent=2)
                        except IOError:
                            pass
                        st.success(f"「{html.escape(loan['name'])}」を削除しました")
                        st.rerun()

                # 編集フォーム
                if st.session_state.get(f"loan_editing_{i}", False):
                    st.markdown("##### 編集")
                    with st.form(f"loan_edit_form_{i}"):
                        ec1, ec2 = st.columns(2)
                        with ec1:
                            e_name = st.text_input("ローン名", value=loan['name'])
                            e_original = st.number_input("借入額", min_value=0, step=100000, value=int(loan.get('original_amount', 0)))
                            e_remaining = st.number_input("残高", min_value=0, step=100000, value=int(loan.get('remaining_balance', 0)))
                            e_rate = st.number_input("金利（%）", min_value=0.0, step=0.01, value=float(loan.get('interest_rate', 0)), format="%.2f")
                        with ec2:
                            e_monthly = st.number_input("月々返済額", min_value=0, step=1000, value=int(loan.get('monthly_amount', 0)))
                            e_bonus = st.number_input("賞与月返済額", min_value=0, step=10000, value=int(loan.get('bonus_amount', 0)))
                            bonus_month_options = list(range(1, 13))
                            e_bonus_months = st.multiselect("賞与月", options=bonus_month_options,
                                default=loan.get('bonus_months', [6, 12]),
                                format_func=lambda m: f"{m}月")
                            acc_ids = list(account_options.keys())
                            current_acc = loan.get('account_id', '')
                            acc_idx = acc_ids.index(current_acc) if current_acc in acc_ids else 0
                            e_account = st.selectbox("引落口座", options=acc_ids,
                                index=acc_idx if acc_ids else 0,
                                format_func=lambda x: account_options.get(x, x)) if acc_ids else None

                        if st.form_submit_button("💾 更新"):
                            st.session_state.loans_data[i].update({
                                'name': e_name, 'original_amount': e_original,
                                'remaining_balance': e_remaining, 'interest_rate': e_rate,
                                'monthly_amount': e_monthly, 'bonus_amount': e_bonus,
                                'bonus_months': e_bonus_months,
                                'account_id': e_account if e_account else '',
                            })
                            try:
                                with open(loan_path, 'w', encoding='utf-8') as f:
                                    json.dump(st.session_state.loans_data, f, ensure_ascii=False, indent=2)
                            except IOError:
                                pass
                            st.session_state[f"loan_editing_{i}"] = False
                            st.success("更新しました")
                            st.rerun()
    else:
        st.info("ローンが登録されていません。下のフォームから追加してください。")

    # --- ローン追加 ---
    st.markdown("---")
    st.markdown("##### ➕ ローンを追加")
    with st.form("add_loan_form", clear_on_submit=True):
        fc1, fc2 = st.columns(2)
        with fc1:
            new_name = st.text_input("ローン名", placeholder="例: 住宅ローン、車ローン", max_chars=100)
            new_original = st.number_input("借入額（円）", min_value=0, step=100000)
            new_remaining = st.number_input("現在の残高（円）", min_value=0, step=100000)
            new_rate = st.number_input("金利（%）", min_value=0.0, step=0.01, format="%.2f")
            new_start = st.text_input("借入日", placeholder="例: 2020-04-01")
            new_end = st.text_input("完済予定日", placeholder="例: 2055-03-31")
        with fc2:
            new_monthly = st.number_input("月々の返済額（円）", min_value=0, step=1000)
            new_bonus = st.number_input("賞与月の返済額（円）", min_value=0, step=10000)
            new_bonus_months = st.multiselect("賞与月", options=list(range(1, 13)),
                default=[6, 12], format_func=lambda m: f"{m}月")
            if account_options:
                acc_ids = list(account_options.keys())
                new_account = st.selectbox("引落口座", options=acc_ids,
                    format_func=lambda x: account_options.get(x, x))
            else:
                new_account = None
                st.caption("口座が未登録です。口座管理タブで追加してください。")

        if st.form_submit_button("➕ 追加"):
            if new_name:
                new_loan = {
                    'name': new_name,
                    'original_amount': new_original,
                    'remaining_balance': new_remaining,
                    'interest_rate': new_rate,
                    'monthly_amount': new_monthly,
                    'bonus_amount': new_bonus,
                    'bonus_months': new_bonus_months,
                    'account_id': new_account or '',
                    'start_date': new_start,
                    'end_date': new_end,
                }
                st.session_state.loans_data.append(new_loan)
                try:
                    loan_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(loan_path, 'w', encoding='utf-8') as f:
                        json.dump(st.session_state.loans_data, f, ensure_ascii=False, indent=2)
                    st.success(f"「{html.escape(new_name)}」を追加しました")
                    st.rerun()
                except IOError:
                    st.error("保存に失敗しました。再試行してください。")
            else:
                st.warning("ローン名を入力してください")


def show_assets_tab() -> None:
    """資産管理タブ - 統合ダッシュボード"""
    import plotly.graph_objects as go

    # === 全資産データ収集 ===

    # 1. 預貯金（口座管理 bank_manager から）
    bank_manager = st.session_state.get("bank_manager")
    bank_accounts = []
    bank_total = 0
    if bank_manager and bank_manager.accounts_df is not None and not bank_manager.accounts_df.empty:
        for _, acc in bank_manager.accounts_df.iterrows():
            balance = acc.get('current_balance', 0) or 0
            acc_type = acc.get('account_type', '')
            if balance > 0 and acc_type != 'credit_card':
                bank_accounts.append({
                    'name': acc.get('name', ''),
                    'bank_name': acc.get('bank_name', ''),
                    'type': acc_type,
                    'balance': balance
                })
                bank_total += balance

    # 2. 金融資産（user_settings: iDeCo, NISA 等）
    financial_assets = st.session_state.get("financial_assets", [])
    fa_total = sum(fa.get("current_value", 0) for fa in financial_assets)

    # 3. 貯蓄型保険（user_settings: insurance_list）
    insurance_list = st.session_state.get("insurance_list", [])
    usd_rate = st.session_state.get("usd_rate", 150.0)
    savings_insurances = []
    insurance_total = 0
    for ins in insurance_list:
        if ins.get("type") == "貯蓄型":
            if ins.get("currency") == "USD":
                value = int(ins.get("value_usd", 0) * usd_rate)
                annual = int(ins.get("annual_usd", 0) * usd_rate)
            else:
                value = ins.get("value", 0)
                annual = ins.get("annual", 0)
            savings_insurances.append({
                'name': ins.get('name', '不明'), 'value': value, 'annual': annual,
                'currency': ins.get('currency', '円')
            })
            insurance_total += value

    # 4. その他（暗号化 AssetManager: 車両・不動産等）
    manager: AssetManager = st.session_state.asset_manager
    assets_df = st.session_state.assets_df
    other_assets_value = 0
    if assets_df is not None and len(assets_df) > 0:
        other_assets_value = manager.get_total_assets_value()

    # 5. ローン・負債
    loans = st.session_state.get("loans_data", [])
    loan_total = sum(l.get('remaining_balance', 0) for l in loans)

    grand_total = bank_total + fa_total + insurance_total + other_assets_value
    net_total = grand_total - loan_total

    # === 資産サマリー ===
    st.markdown("### 📊 資産サマリー")
    col_top1, col_top2, col_top3 = st.columns(3)
    with col_top1:
        st.metric("総資産", f"¥{grand_total:,.0f}")
    with col_top2:
        st.metric("🏠 負債（ローン）", f"¥{loan_total:,.0f}")
    with col_top3:
        delta = f"¥{net_total - grand_total:,.0f}" if loan_total > 0 else None
        st.metric("純資産", f"¥{net_total:,.0f}", delta=delta)

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.metric("🔵 預貯金", f"¥{bank_total:,.0f}")
    with col_m2:
        st.metric("🟢 金融資産", f"¥{fa_total:,.0f}")
    with col_m3:
        st.metric("🔴 貯蓄型保険", f"¥{insurance_total:,.0f}")
    with col_m4:
        st.metric("🟠 その他", f"¥{other_assets_value:,.0f}")

    # === 資産構成グラフ（コンパクト版）===
    pie_labels = []
    pie_values = []
    pie_colors = []
    blue_p = ["#2980b9", "#3498db", "#5dade2", "#85c1e9"]
    green_p = ["#27ae60", "#2ecc71", "#58d68d", "#82e0aa"]
    red_p = ["#c0392b", "#e74c3c", "#ec7063", "#f1948a"]

    for i, acc in enumerate(bank_accounts):
        pie_labels.append(acc['name'])
        pie_values.append(acc['balance'])
        pie_colors.append(blue_p[i % len(blue_p)])
    for i, fa in enumerate(financial_assets):
        if fa.get("current_value", 0) > 0:
            pie_labels.append(fa['name'])
            pie_values.append(fa['current_value'])
            pie_colors.append(green_p[i % len(green_p)])
    for i, ins in enumerate(savings_insurances):
        if ins['value'] > 0:
            short = ins['name']
            if '「' in short and '」' in short:
                short = short[short.index('「'):short.index('」') + 1]
            elif len(short) > 8:
                short = short[:8] + '…'
            pie_labels.append(short)
            pie_values.append(ins['value'])
            pie_colors.append(red_p[i % len(red_p)])
    # その他資産（車両・不動産等）
    orange_p = ["#e67e22", "#f39c12", "#f5b041", "#f8c471"]
    if assets_df is not None and len(assets_df) > 0:
        for i, (_, row) in enumerate(assets_df.iterrows()):
            val = row.get('current_value', 0)
            if val and val > 0:
                pie_labels.append(row.get('name', 'その他'))
                pie_values.append(val)
                pie_colors.append(orange_p[i % len(orange_p)])

    if pie_labels:
        fig = go.Figure(data=[go.Pie(
            labels=pie_labels, values=pie_values, hole=0.4,
            textinfo='label+percent', textposition='inside',
            insidetextorientation='radial',
            marker=dict(colors=pie_colors),
            textfont=dict(size=11),
        )])
        fig.update_layout(
            height=350, showlegend=True,
            legend=dict(orientation='h', y=-0.05, xanchor='center', x=0.5, font=dict(size=10)),
            margin=dict(t=10, b=50, l=10, r=10),
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # === サブタブ ===
    sub_tabs = st.tabs([
        "🏦 預貯金",
        "💹 金融資産",
        "🛡️ 貯蓄型保険",
        "🏠 ローン・負債",
        "📦 その他資産",
        "📋 全資産一覧"
    ])

    # --- 🏦 預貯金タブ ---
    with sub_tabs[0]:
        st.markdown("#### 🏦 預貯金（口座管理から自動取得）")
        if bank_accounts:
            rows = []
            for acc in bank_accounts:
                bn = acc.get('bank_name', '')
                display_name = f"{acc['name']}（{bn}）" if bn and bn != acc['name'] else acc['name']
                rows.append({
                    "口座名": display_name,
                    "種別": "銀行口座" if acc['type'] == 'bank' else "証券口座",
                    "残高": acc['balance']
                })
            df_bank = pd.DataFrame(rows)
            st.dataframe(
                df_bank.style.format({"残高": "¥{:,.0f}"}),
                use_container_width=True, hide_index=True
            )
            st.metric("預貯金合計", f"¥{bank_total:,.0f}")
            st.caption("※ 口座の追加・編集は「💳 口座管理」タブで行えます")
        else:
            st.info("口座が登録されていません。「💳 口座管理」タブで口座を追加してください。")

    # --- 💹 金融資産タブ ---
    with sub_tabs[1]:
        st.markdown("#### 💹 金融資産（iDeCo・NISA・株式等）")

        if financial_assets:
            rows = []
            for fa in financial_assets:
                rows.append({
                    "資産名": fa['name'],
                    "種別": fa.get('type', ''),
                    "評価額": fa.get('current_value', 0),
                })
            df_fa = pd.DataFrame(rows)
            st.dataframe(
                df_fa.style.format({"評価額": "¥{:,.0f}"}),
                use_container_width=True, hide_index=True
            )
            st.metric("金融資産合計", f"¥{fa_total:,.0f}")
        else:
            st.info("金融資産が登録されていません。下のフォームから追加してください。")

        st.markdown("---")

        # 編集・削除
        if financial_assets:
            st.markdown("##### 既存の金融資産を編集・削除")
            fa_names = [f"{fa['name']}（{fa.get('type', '')}）" for fa in financial_assets]
            edit_idx = st.selectbox(
                "対象を選択", range(len(financial_assets)),
                format_func=lambda i: fa_names[i],
                key="fa_edit_select"
            )

            if edit_idx is not None:
                target = financial_assets[edit_idx]
                col_e1, col_e2, col_e3 = st.columns([2, 2, 1])
                with col_e1:
                    edit_name = st.text_input("資産名", value=target['name'], key="fa_edit_name")
                with col_e2:
                    FINANCIAL_ASSET_TYPES = [
                        "確定拠出年金（iDeCo）", "NISA", "株式", "投資信託", "債券", "外貨預金", "その他"
                    ]
                    current_type = target.get('type', 'その他')
                    type_idx = FINANCIAL_ASSET_TYPES.index(current_type) if current_type in FINANCIAL_ASSET_TYPES else len(FINANCIAL_ASSET_TYPES) - 1
                    edit_type = st.selectbox("種別", FINANCIAL_ASSET_TYPES, index=type_idx, key="fa_edit_type")
                with col_e3:
                    edit_value = st.number_input(
                        "評価額（円）", min_value=0, step=10000,
                        value=int(target.get('current_value', 0)), key="fa_edit_value"
                    )

                col_btn1, col_btn2, _ = st.columns([1, 1, 3])
                with col_btn1:
                    if st.button("💾 更新", key="fa_update_btn"):
                        st.session_state.financial_assets[edit_idx] = {
                            "name": edit_name, "type": edit_type, "current_value": edit_value,
                        }
                        save_user_settings(get_current_settings())
                        st.success(f"「{edit_name}」を更新しました")
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ 削除", key="fa_delete_btn", type="secondary"):
                        removed = st.session_state.financial_assets.pop(edit_idx)
                        save_user_settings(get_current_settings())
                        st.success(f"「{removed['name']}」を削除しました")
                        st.rerun()

        # 追加フォーム
        st.markdown("##### 金融資産を追加")
        with st.form("add_fa_form", clear_on_submit=True):
            FINANCIAL_ASSET_TYPES = [
                "確定拠出年金（iDeCo）", "NISA", "株式", "投資信託", "債券", "外貨預金", "その他"
            ]
            col_a1, col_a2, col_a3 = st.columns([2, 2, 1])
            with col_a1:
                new_name = st.text_input("資産名", placeholder="例: iDeCo, 楽天NISA")
            with col_a2:
                new_type = st.selectbox("種別", FINANCIAL_ASSET_TYPES)
            with col_a3:
                new_value = st.number_input("評価額（円）", min_value=0, step=10000)

            if st.form_submit_button("➕ 追加"):
                if new_name:
                    st.session_state.financial_assets.append({
                        "name": new_name, "type": new_type, "current_value": new_value,
                    })
                    save_user_settings(get_current_settings())
                    st.success(f"「{new_name}」を追加しました")
                    st.rerun()
                else:
                    st.warning("資産名を入力してください")

    # --- 🛡️ 貯蓄型保険タブ ---
    with sub_tabs[2]:
        st.markdown("#### 🛡️ 貯蓄型保険")
        if savings_insurances:
            rows = []
            for ins in savings_insurances:
                currency_mark = " 🇺🇸" if ins.get('currency') == 'USD' else ""
                rows.append({
                    "保険名": ins['name'] + currency_mark,
                    "年間保険料": ins['annual'],
                    "解約返戻金/積立額": ins['value'],
                })
            df_ins = pd.DataFrame(rows)
            st.dataframe(
                df_ins.style.format({
                    "年間保険料": "¥{:,.0f}",
                    "解約返戻金/積立額": "¥{:,.0f}",
                }),
                use_container_width=True, hide_index=True
            )
            annual_total = sum(ins['annual'] for ins in savings_insurances)
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                st.metric("資産価値合計", f"¥{insurance_total:,.0f}")
            with col_m2:
                st.metric("年間保険料合計", f"¥{annual_total:,.0f}")

            st.caption("※ 保険の追加・編集はサイドバーの「🛡️ 保険・固定費」で行えます")
        else:
            st.info("貯蓄型保険が登録されていません。サイドバーの「🛡️ 保険・固定費」から追加してください。")

    # --- 🏠 ローン・負債タブ ---
    with sub_tabs[3]:
        _show_loan_tab()

    # --- 📦 その他資産タブ ---
    with sub_tabs[4]:
        st.markdown("#### 📦 その他資産（車両・不動産等）")

        # 暗号化データの復号
        crypto: CryptoManager = st.session_state.crypto_manager
        if crypto.has_encrypted_data() and not st.session_state.asset_unlocked:
            st.info("🔐 暗号化された資産データがあります。パスワードを入力して復号してください。")
            with st.form("unlock_form"):
                password = st.text_input("パスワード", type="password")
                if st.form_submit_button("🔓 復号して開く"):
                    if password and manager.load_encrypted(crypto, password):
                        st.session_state.assets_df = manager.df
                        st.session_state.asset_password = password
                        st.session_state.asset_unlocked = True
                        st.rerun()
                    else:
                        st.error("パスワードが違います")
        elif assets_df is not None and len(assets_df) > 0:
            for asset_type, label, icon in [
                ("vehicle", "車両・バイク", "🚗"),
                ("real_estate", "不動産", "🏠"),
            ]:
                type_df = manager.get_assets_by_type(asset_type)
                if len(type_df) > 0:
                    st.markdown(f"##### {icon} {label}")
                    display_df = type_df[["name", "purchase_date", "purchase_price", "current_value"]].copy()
                    display_df.columns = ["名称", "購入日", "購入価格", "現在価値"]
                    st.dataframe(
                        display_df.style.format({"購入価格": "¥{:,.0f}", "現在価値": "¥{:,.0f}"}),
                        use_container_width=True, hide_index=True
                    )

            if other_assets_value > 0:
                st.metric("その他資産合計", f"¥{other_assets_value:,.0f}")

            # 削除
            st.markdown("##### 資産の削除")
            del_options = assets_df["asset_id"].tolist()
            if del_options:
                asset_to_delete = st.selectbox(
                    "削除する資産", del_options,
                    format_func=lambda x: f"{x}: {assets_df[assets_df['asset_id']==x]['name'].values[0]}",
                    key="other_asset_del"
                )
                if st.button("選択した資産を削除", type="secondary", key="other_del_btn"):
                    manager.delete_asset(asset_to_delete)
                    st.session_state.assets_df = manager.df
                    st.rerun()
        else:
            st.info("その他の資産データはありません。")

        # 資産追加フォーム
        st.markdown("##### 資産を追加")
        with st.form("add_other_asset_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                asset_type = st.selectbox(
                    "資産タイプ",
                    options=["vehicle", "real_estate"],
                    format_func=lambda x: {"vehicle": "🚗 車両・バイク", "real_estate": "🏠 不動産"}[x]
                )
                name = st.text_input("名称", placeholder="例: トヨタ アクア")
                purchase_date = st.date_input("購入日")
            with col2:
                purchase_price = st.number_input("購入価格（円）", min_value=0, step=100000)
                current_value = st.number_input("現在価値（円）", min_value=0, step=100000)
                details = st.text_input("詳細（任意）", placeholder='{"cc": 1500}')
            if st.form_submit_button("追加"):
                if name:
                    manager.add_asset({
                        "asset_type": asset_type, "name": name,
                        "purchase_date": purchase_date,
                        "purchase_price": purchase_price,
                        "current_value": current_value,
                        "details": details if details else "{}"
                    })
                    st.session_state.assets_df = manager.df
                    st.rerun()
                else:
                    st.warning("名称を入力してください")

    # --- 📋 全資産一覧タブ ---
    with sub_tabs[5]:
        st.markdown("#### 📋 全資産一覧")

        all_rows = []
        for acc in bank_accounts:
            bn = acc.get('bank_name', '')
            all_rows.append({
                "カテゴリ": "🔵 預貯金",
                "名称": f"{acc['name']}（{bn}）" if bn and bn != acc['name'] else acc['name'],
                "評価額": acc['balance'],
            })
        for fa in financial_assets:
            all_rows.append({
                "カテゴリ": "🟢 金融資産",
                "名称": f"{fa['name']}（{fa.get('type', '')}）",
                "評価額": fa.get('current_value', 0),
            })
        for ins in savings_insurances:
            all_rows.append({
                "カテゴリ": "🔴 貯蓄型保険",
                "名称": ins['name'],
                "評価額": ins['value'],
            })
        if assets_df is not None and len(assets_df) > 0:
            for _, row in assets_df.iterrows():
                type_label = {"vehicle": "🚗 車両", "real_estate": "🏠 不動産",
                              "financial": "💰 金融"}.get(row.get('asset_type', ''), "📦 その他")
                all_rows.append({
                    "カテゴリ": type_label,
                    "名称": row.get('name', ''),
                    "評価額": row.get('current_value', 0),
                })

        if all_rows:
            df_all = pd.DataFrame(all_rows)
            st.dataframe(
                df_all.style.format({"評価額": "¥{:,.0f}"}),
                use_container_width=True, hide_index=True
            )
            st.metric("全資産合計", f"¥{grand_total:,.0f}")
        else:
            st.info("資産データがありません。各タブから資産を追加してください。")


def _show_medical_deduction(calculator: TaxCalculator, adj: YearEndAdjustment, tax_year: int = None) -> None:
    """医療費控除タブ"""
    import plotly.graph_objects as go

    year = tax_year or adj.year
    st.markdown(f"## 🏥 医療費控除シミュレーション（{year}年）")

    # 年収取得
    annual_income = adj.get_annual_income() or st.session_state.get("annual_income") or 0

    if annual_income <= 0:
        st.warning("年収が未設定です。「📝 年末調整」タブまたはサイドバーで年収を入力してください。")

    # === セクション1: 自動集計 ===
    st.markdown(f"### 📊 {year}年の記録済み医療費")
    df = st.session_state.get("df")
    auto_total = 0
    auto_count = 0
    if df is not None and not df.empty and 'カテゴリ' in df.columns:
        med_data = TaxCalculator.extract_medical_expenses(df, year=year)
        auto_total = med_data['total']
        auto_count = med_data['count']

        if auto_count > 0:
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                st.metric("アプリ記録の医療費", f"¥{auto_total:,.0f}", f"{auto_count}件")
            with col_m2:
                threshold = max(100000, annual_income * 0.05) if annual_income > 0 else 100000
                remaining = max(0, threshold - auto_total)
                if remaining > 0:
                    st.metric("控除適用まであと", f"¥{remaining:,.0f}")
                else:
                    st.metric("控除適用", "基準超過済み ✓")

            # 月別棒グラフ
            if med_data['monthly']:
                months = sorted(med_data['monthly'].keys())
                values = [med_data['monthly'][m] for m in months]
                fig = go.Figure(data=[go.Bar(x=months, y=values, marker_color='#e74c3c')])
                fig.update_layout(title='月別医療費', height=250, margin=dict(t=30, b=30, l=40, r=20),
                                  xaxis_title='月', yaxis_title='金額（円）')
                st.plotly_chart(fig, use_container_width=True)

            with st.expander(f"医療費明細（{auto_count}件）"):
                display_df = med_data['entries'][['日付', '金額', 'メモ']].copy()
                display_df['金額'] = display_df['金額'].apply(lambda x: f"¥{x:,.0f}")
                st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.info(f"{adj.year}年の医療費データはありません。")
    else:
        st.info("家計データが読み込まれていません。")

    # === セクション2: 調整入力 ===
    st.markdown("### ✏️ 医療費の調整")
    col_i1, col_i2 = st.columns(2)
    with col_i1:
        extra_medical = st.number_input(
            "追加の医療費（家族分・アプリ外）", min_value=0, step=10000,
            key="med_extra", help="アプリに記録していない医療費（家族の分など）"
        )
        insurance_reimb = st.number_input(
            "保険金等の補填額", min_value=0, step=10000,
            key="med_reimb", help="生命保険・健康保険から補填された金額"
        )
    with col_i2:
        self_med = st.number_input(
            "セルフメディケーション対象額", min_value=0, step=1000,
            key="med_self", help="スイッチOTC対象医薬品の購入額"
        )
        use_self_med = st.checkbox("セルフメディケーション税制を検討", key="med_use_self")

    total_medical = auto_total + extra_medical

    # === セクション3: シミュレーション ===
    st.markdown("### 💰 控除額シミュレーション")

    if annual_income > 0 and total_medical > 0:
        result = calculator.calculate_medical_deduction(
            total_medical, insurance_reimb, annual_income, self_med
        )

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.markdown("#### 通常の医療費控除")
            std = result['standard']
            if std['deduction'] > 0:
                st.metric("控除額", f"¥{std['deduction']:,.0f}")
                st.metric("節税効果（見込み）", f"¥{std['savings']:,.0f}")
            else:
                threshold = max(100000, annual_income * 0.05)
                st.info(f"医療費が基準額（¥{threshold:,.0f}）に達していません")

        with col_s2:
            st.markdown("#### セルフメディケーション税制")
            sm = result['self_medication']
            if sm['deduction'] > 0:
                st.metric("控除額", f"¥{sm['deduction']:,.0f}")
                st.metric("節税効果（見込み）", f"¥{sm['savings']:,.0f}")
            else:
                if self_med > 0:
                    st.info("対象額が12,000円に達していません")
                else:
                    st.info("セルフメディケーション対象額を入力してください")

        # 推奨
        if result['standard']['deduction'] > 0 or result['self_medication']['deduction'] > 0:
            rec = result['recommended']
            rec_label = "通常の医療費控除" if rec == 'standard' else "セルフメディケーション税制"
            st.success(f"**推奨: {rec_label}** がより有利です（※ 両方の同時適用は不可）")

        # === セクション4: 年末調整連携 ===
        st.markdown("---")
        chosen = result['standard'] if not use_self_med else result['self_medication']
        if chosen['deduction'] > 0:
            if st.button("📥 この控除額を年末調整データに反映", key="med_apply"):
                adj.set_medical_expense(
                    total=total_medical,
                    insurance_reimbursement=insurance_reimb,
                    self_medication=self_med,
                    use_self_medication=use_self_med,
                )
                adj.save_to_yaml()
                st.success(f"医療費控除 ¥{chosen['deduction']:,.0f} を反映しました")
                st.rerun()
    elif annual_income <= 0:
        st.info("年収を入力すると控除額をシミュレーションできます。")
    else:
        st.info("医療費を入力すると控除額をシミュレーションできます。")


def _show_furusato_nouzei(calculator: TaxCalculator, adj: YearEndAdjustment, tax_year: int = None) -> None:
    """ふるさと納税タブ"""
    year = tax_year or adj.year
    st.markdown(f"## 🏡 ふるさと納税シミュレーション（{year}年）")

    # 年収取得
    annual_income = adj.get_annual_income() or st.session_state.get("annual_income") or 0

    if annual_income <= 0:
        st.warning("年収が未設定です。「📝 年末調整」タブまたはサイドバーで年収を入力してください。")

    # 既存の控除を収集（医療費控除がある場合はふるさと上限に影響）
    med_exp = adj.deductions.get('medical_expense', {})
    other_deductions = {}
    if med_exp.get('total', 0) > 0:
        med_result = calculator.calculate_medical_deduction(
            med_exp['total'], med_exp.get('insurance_reimbursement', 0),
            annual_income, med_exp.get('self_medication', 0)
        )
        if med_exp.get('use_self_medication'):
            ded_amt = med_result['self_medication']['deduction']
        else:
            ded_amt = med_result['standard']['deduction']
        if ded_amt > 0:
            other_deductions['医療費控除'] = ded_amt

    # === セクション1: 上限シミュレーション ===
    st.markdown("### 📊 控除上限シミュレーション")

    if annual_income > 0:
        limit_result = calculator.calculate_furusato_limit(annual_income, other_deductions)
        limit = limit_result['limit']

        # 寄附済み合計（対象年度のみ）
        all_d = st.session_state.get("furusato_donations", [])
        year_donations = [d for d in all_d if str(d.get('date', '')).startswith(str(year))]
        donated_total = sum(d.get('amount', 0) for d in year_donations)
        remaining = max(0, limit - donated_total)

        col_l1, col_l2, col_l3 = st.columns(3)
        with col_l1:
            st.metric("控除上限目安", f"¥{limit:,.0f}")
        with col_l2:
            st.metric("寄附済み", f"¥{donated_total:,.0f}")
        with col_l3:
            st.metric("残り寄附可能額", f"¥{remaining:,.0f}")

        # プログレスバー
        if limit > 0:
            progress = min(1.0, donated_total / limit)
            st.progress(progress, text=f"利用率: {progress*100:.0f}%")

        if other_deductions:
            st.caption("※ 医療費控除（¥{:,.0f}）を考慮した上限額です".format(
                sum(other_deductions.values())))

        with st.expander("計算の詳細"):
            st.markdown(f"""
- 年収: ¥{annual_income:,.0f}
- 課税所得: ¥{limit_result['taxable_income']:,.0f}
- 所得税率（限界税率）: {limit_result['tax_rate']*100:.0f}%
- 自己負担額: ¥{limit_result['self_pay']:,.0f}
""")
    else:
        st.info("年収を入力すると控除上限を計算できます。")

    st.markdown("---")

    # === セクション2: 寄附記録管理 ===
    st.markdown(f"### 📝 寄附記録（{year}年）")

    all_donations = st.session_state.get("furusato_donations", [])
    # 年度でフィルタ（日付が対象年のもの）
    donations = [d for d in all_donations if str(d.get('date', '')).startswith(str(year))]

    if donations:
        rows = []
        for d in donations:
            rows.append({
                "日付": d.get('date', ''),
                "自治体": d.get('municipality', ''),
                "金額": d.get('amount', 0),
                "返礼品": d.get('return_item', ''),
                "ワンストップ": "✓" if d.get('one_stop_submitted') else "—",
            })
        import pandas as pd_local
        df_d = pd_local.DataFrame(rows)
        st.dataframe(
            df_d.style.format({"金額": "¥{:,.0f}"}),
            use_container_width=True, hide_index=True
        )

        # 編集・削除
        st.markdown("##### 寄附の削除")
        del_labels = [f"{d.get('municipality', '')} ¥{d.get('amount', 0):,.0f}" for d in donations]
        del_idx = st.selectbox("対象を選択", range(len(donations)),
                               format_func=lambda i: del_labels[i], key="furu_del_select")
        if st.button("🗑️ 削除", key="furu_del_btn"):
            # 全リスト内の実際のインデックスを見つけて削除
            target = donations[del_idx]
            all_list = st.session_state.furusato_donations
            for i, d in enumerate(all_list):
                if d is target or (d.get('date') == target.get('date') and d.get('municipality') == target.get('municipality') and d.get('amount') == target.get('amount')):
                    all_list.pop(i)
                    break
            save_user_settings(get_current_settings())
            st.rerun()
    else:
        st.info("まだ寄附記録がありません。下のフォームから追加してください。")

    # 追加フォーム
    st.markdown("##### 寄附を追加")
    with st.form("add_furusato_form", clear_on_submit=True):
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            f_date = st.date_input("寄附日", key="furu_date")
            f_muni = st.text_input("自治体名", placeholder="例: 北海道紋別市", key="furu_muni")
        with col_f2:
            f_amount = st.number_input("寄附金額（円）", min_value=2000, step=5000, key="furu_amount")
            f_item = st.text_input("返礼品（任意）", placeholder="例: ズワイガニ", key="furu_item")
        f_onestop = st.checkbox("ワンストップ特例申請済み", key="furu_onestop")

        if st.form_submit_button("➕ 追加"):
            if f_muni:
                st.session_state.furusato_donations.append({
                    "date": str(f_date),
                    "municipality": f_muni,
                    "amount": f_amount,
                    "return_item": f_item,
                    "one_stop_submitted": f_onestop,
                })
                save_user_settings(get_current_settings())
                # 年末調整にも反映
                total_d = sum(d.get('amount', 0) for d in st.session_state.furusato_donations)
                has_onestop = any(d.get('one_stop_submitted') for d in st.session_state.furusato_donations)
                adj.set_furusato_nouzei(total_d, has_onestop)
                adj.save_to_yaml()
                st.rerun()
            else:
                st.warning("自治体名を入力してください")

    st.markdown("---")

    # === セクション3: ワンストップ vs 確定申告 ===
    st.markdown("### 📋 ワンストップ特例 vs 確定申告")

    municipalities = len(set(d.get('municipality', '') for d in donations))
    has_medical = med_exp.get('total', 0) > 0

    if has_medical:
        st.error("⚠️ 医療費控除を利用する場合、ワンストップ特例は使えません。**確定申告が必要**です。")
    elif municipalities > 5:
        st.warning(f"⚠️ 寄附先が{municipalities}自治体（5超）のため、ワンストップ特例は使えません。確定申告が必要です。")

    if annual_income > 0 and donated_total > 0:
        col_c1, col_c2 = st.columns(2)

        savings_onestop = calculator.calculate_furusato_savings(
            donated_total, annual_income, other_deductions, one_stop=True)
        savings_filing = calculator.calculate_furusato_savings(
            donated_total, annual_income, other_deductions, one_stop=False)

        with col_c1:
            st.markdown("#### ワンストップ特例")
            if not has_medical and municipalities <= 5:
                st.metric("住民税控除", f"¥{savings_onestop['resident_tax_reduction']:,.0f}")
                st.metric("実質負担", f"¥{savings_onestop['effective_cost']:,.0f}")
                st.caption("5自治体以内、確定申告不要")
            else:
                st.info("利用条件を満たしていません")

        with col_c2:
            st.markdown("#### 確定申告")
            st.metric("所得税還付", f"¥{savings_filing['income_tax_refund']:,.0f}")
            st.metric("住民税控除", f"¥{savings_filing['resident_tax_reduction']:,.0f}")
            st.metric("実質負担", f"¥{savings_filing['effective_cost']:,.0f}")
            st.caption("自治体数・他の控除に関わらず利用可能")


def show_integrated_tax_tab() -> None:
    """税金・年末調整 統合タブ"""
    calculator: TaxCalculator = st.session_state.tax_calculator
    manager: AssetManager = st.session_state.asset_manager
    adj: YearEndAdjustment = st.session_state.year_end_adjustment

    # --- 年度セレクタ ---
    current_year = datetime.now().year
    year_options = list(range(current_year - 3, current_year + 1))
    default_idx = year_options.index(adj.year) if adj.year in year_options else len(year_options) - 1
    tax_year = st.selectbox(
        "📅 対象年度", year_options, index=default_idx, key="tax_year_select",
        format_func=lambda y: f"{y}年（令和{y - 2018}年）"
    )
    # 年末調整の年度も同期
    if tax_year != adj.year:
        adj.year = tax_year
        adj.save_to_yaml()

    # 年末調整から年収を取得（あれば）
    yea_income = adj.get_annual_income()

    # サブタブで機能を分割
    sub_tabs = st.tabs(["📊 総合サマリー", "📝 年末調整", "🏥 医療費控除", "🏡 ふるさと納税", "📅 税金カレンダー", "⚙️ 詳細設定"])

    with sub_tabs[0]:
        _show_tax_summary(calculator, manager, adj, yea_income, tax_year)

    with sub_tabs[1]:
        _show_year_end_adjustment(adj)

    with sub_tabs[2]:
        _show_medical_deduction(calculator, adj, tax_year)

    with sub_tabs[3]:
        _show_furusato_nouzei(calculator, adj, tax_year)

    with sub_tabs[4]:
        _show_tax_calendar(calculator, manager, yea_income or st.session_state.annual_income or 0)

    with sub_tabs[5]:
        _show_tax_settings(calculator, manager)


def _show_tax_summary(calculator: TaxCalculator, manager: AssetManager,
                      adj: YearEndAdjustment, yea_income: int, tax_year: int = None) -> None:
    """税金総合サマリー"""
    year_label = f"（{tax_year}年度）" if tax_year else ""
    st.markdown(f"## 💴 税金・年末調整サマリー{year_label}")

    # 年収の自動同期
    if yea_income > 0:
        st.success(f"📋 年末調整データから年収を取得: ¥{yea_income:,}")
        annual_income = yea_income
        st.session_state.annual_income = annual_income
    else:
        annual_income = st.number_input(
            "年収（円）",
            min_value=0,
            step=100000,
            value=st.session_state.annual_income or 0,
            help="年末調整タブでデータを入力すると自動連携されます"
        )
        st.session_state.annual_income = annual_income if annual_income > 0 else None

    if not annual_income or annual_income == 0:
        st.info("年収を入力するか、年末調整タブでデータをインポートしてください。")
        return

    # 詳細設定・医療費控除・ふるさと納税から控除を収集
    deductions = dict(st.session_state.get("tax_deductions", {}))
    # 医療費控除タブからの控除
    med_exp = adj.deductions.get('medical_expense', {})
    if med_exp.get('total', 0) > 0:
        med_result = calculator.calculate_medical_deduction(
            med_exp['total'], med_exp.get('insurance_reimbursement', 0),
            annual_income, med_exp.get('self_medication', 0))
        med_ded = med_result['self_medication']['deduction'] if med_exp.get('use_self_medication') else med_result['standard']['deduction']
        if med_ded > 0 and '医療費控除' not in deductions:
            deductions['医療費控除'] = med_ded
    # ふるさと納税の寄附額
    furu = adj.deductions.get('furusato_nouzei', {})
    if furu.get('total_donation', 0) > 0 and 'ふるさと納税' not in deductions:
        deductions['ふるさと納税'] = max(0, furu['total_donation'] - 2000)

    if deductions:
        st.info(f"適用中の控除: {', '.join(f'{k} ¥{v:,}' for k, v in deductions.items())}")

    # 年末調整計算結果
    if yea_income > 0:
        yea_result = adj.calculate_adjustment()
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("年間給与収入", f"¥{yea_result['年間給与収入']:,}")
        with col2:
            st.metric("課税所得", f"¥{yea_result['課税所得']:,}")
        with col3:
            delta_color = "normal" if yea_result['過不足額'] >= 0 else "inverse"
            st.metric(
                "年末調整",
                f"¥{abs(yea_result['過不足額']):,}",
                delta=yea_result['結果'],
                delta_color=delta_color
            )
    else:
        # TaxCalculatorで計算（控除適用）
        tax_result = calculator.calculate_total_tax(annual_income, deductions if deductions else None)
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("年収", f"¥{annual_income:,}")
        with col2:
            st.metric("課税所得", f"¥{tax_result['課税所得']:,}")
        with col3:
            st.metric("実効税率", f"{tax_result['実効税率']}%")

    st.markdown("---")

    # 税金内訳
    st.markdown("### 税金内訳")
    if yea_income > 0:
        yea_result = adj.calculate_adjustment()
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("所得税", f"¥{yea_result['年税額']:,}")
        with col2:
            st.metric("復興特別所得税", f"¥{yea_result['復興特別所得税']:,}")
        with col3:
            # 住民税は TaxCalculator で計算
            resident_tax = calculator.calculate_resident_tax(yea_result['課税所得'])
            st.metric("住民税（予想）", f"¥{resident_tax:,}")
        with col4:
            social_ins = adj.get_total_social_insurance()
            st.metric("社会保険料", f"¥{social_ins:,}")
    else:
        tax_result = calculator.calculate_total_tax(annual_income, deductions if deductions else None)
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("所得税", f"¥{tax_result['所得税']:,}")
        with col2:
            st.metric("復興特別所得税", f"¥{tax_result['復興特別所得税']:,}")
        with col3:
            st.metric("住民税", f"¥{tax_result['住民税']:,}")
        with col4:
            monthly = annual_income // 12
            social = calculator.calculate_social_insurance(monthly)
            st.metric("社会保険料（概算）", f"¥{social['年間社会保険']:,}")

    # 車両関連税
    assets_df = st.session_state.assets_df
    vehicle_tax_total = 0
    weight_tax_total = 0

    if assets_df is not None:
        vehicle_df = manager.get_assets_by_type("vehicle")
        if len(vehicle_df) > 0:
            st.markdown("### 車両関連税")
            col1, col2 = st.columns(2)

            for _, vehicle in vehicle_df.iterrows():
                details = vehicle.get("details_parsed", {})
                cc = details.get("cc", 0)
                weight_kg = details.get("weight_kg", 0)
                if cc > 0:
                    v_tax = calculator.calculate_vehicle_tax(cc)
                    vehicle_tax_total += v_tax
                if weight_kg > 0:
                    w_tax = calculator.calculate_weight_tax(weight_kg)
                    weight_tax_total += w_tax // 2

            with col1:
                st.metric("自動車税（年額）", f"¥{vehicle_tax_total:,}")
            with col2:
                st.metric("重量税（年額換算）", f"¥{weight_tax_total:,}")

    # 年間税金合計
    st.markdown("### 年間税金総額")
    if yea_income > 0:
        yea_result = adj.calculate_adjustment()
        income_tax = yea_result['年調年税額']
        resident_tax = calculator.calculate_resident_tax(yea_result['課税所得'])
        social_ins = adj.get_total_social_insurance()
    else:
        tax_result = calculator.calculate_total_tax(annual_income, deductions if deductions else None)
        income_tax = tax_result['所得税'] + tax_result['復興特別所得税']
        resident_tax = tax_result['住民税']
        monthly = annual_income // 12
        social_ins = calculator.calculate_social_insurance(monthly)['年間社会保険']

    total_tax = income_tax + resident_tax + vehicle_tax_total + weight_tax_total
    total_with_social = total_tax + social_ins
    take_home = annual_income - total_with_social

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("税金合計", f"¥{total_tax:,}")
    with col2:
        st.metric("税金+社保合計", f"¥{total_with_social:,}")
    with col3:
        st.metric("手取り（税・社保引後）", f"¥{take_home:,}")


def _show_year_end_adjustment(adj: YearEndAdjustment) -> None:
    """年末調整セクション"""
    st.markdown("## 📝 年末調整")

    # ファイルインポート
    st.markdown("### 📥 源泉徴収票インポート")

    uploaded_file = st.file_uploader(
        "源泉徴収票をアップロード（CSV または PDF）",
        type=['csv', 'pdf'],
        key="year_end_file",
        help="令和X年度年末調整形式のCSVまたはPDFファイルをアップロードしてください"
    )

    if uploaded_file:
        file_type = uploaded_file.name.split('.')[-1].lower()

        if file_type == 'csv':
            content = uploaded_file.read().decode('utf-8')
            uploaded_file.seek(0)

            with st.expander("CSVプレビュー", expanded=True):
                st.code(content, language=None)

            if st.button("📥 インポート実行", type="primary", key="import_file_btn"):
                try:
                    result = adj.import_from_csv(uploaded_file)
                    st.success(f"インポート完了: 年収 ¥{result.get('annual_income', 0):,}")
                    st.rerun()
                except Exception as e:
                    logger.error(f"インポートエラー: {e}")
                    st.error("インポートに失敗しました。ファイル形式を確認してください。")

        elif file_type == 'pdf':
            st.info("📄 PDFファイルが選択されました")

            if st.button("📥 PDFからインポート", type="primary", key="import_pdf_btn"):
                try:
                    result = adj.import_from_pdf(uploaded_file)
                    st.success(f"インポート完了: 年収 ¥{result.get('annual_income', 0):,}")

                    with st.expander("抽出されたデータ", expanded=True):
                        for key, value in result.items():
                            label = {
                                'annual_income': '支払金額',
                                'withheld_tax': '源泉徴収税額',
                                'social_insurance': '社会保険料',
                                'small_enterprise': '小規模企業共済等掛金',
                                'life_insurance_deduction': '生命保険料控除額'
                            }.get(key, key)
                            st.write(f"- {label}: ¥{value:,}")

                    st.rerun()
                except Exception as e:
                    logger.error(f"PDFインポートエラー: {e}")
                    st.error("PDFのインポートに失敗しました。ファイルを確認してください。")

    st.markdown("---")

    # 年度選択
    current_year = datetime.now().year
    year = st.selectbox("対象年度", options=list(range(current_year - 2, current_year + 1)),
                        index=2, key="yea_year")
    adj.year = year

    # 年間給与入力（源泉徴収票の年間合計のみ）
    with st.expander("📅 年間給与データ（源泉徴収票ベース）", expanded=adj.get_annual_income() == 0):
        st.caption("源泉徴収票の年間合計のみを入力します。月別の給与内訳は保持しません。")
        _cur_ann_salary = sum(d.get('salary', 0) for d in adj.monthly_data)
        _cur_ann_bonus = sum(d.get('bonus', 0) for d in adj.monthly_data)
        _cur_ann_tax = sum(d.get('withheld_tax', 0) for d in adj.monthly_data)
        _cur_ann_si = sum(d.get('social_insurance', 0) for d in adj.monthly_data)

        _ye1, _ye2 = st.columns(2)
        with _ye1:
            ann_salary = st.number_input("年間給与（賞与除く）", min_value=0, step=10000,
                                          value=int(_cur_ann_salary), key="yea_ann_salary", format="%d")
            ann_bonus = st.number_input("年間賞与", min_value=0, step=10000,
                                         value=int(_cur_ann_bonus), key="yea_ann_bonus", format="%d")
        with _ye2:
            ann_tax = st.number_input("源泉徴収税額（年間合計）", min_value=0, step=1000,
                                       value=int(_cur_ann_tax), key="yea_ann_tax", format="%d")
            ann_si = st.number_input("社会保険料（年間合計）", min_value=0, step=1000,
                                      value=int(_cur_ann_si), key="yea_ann_si", format="%d")

        # monthly_data を単一エントリ（12月にまとめて保持）で集約。get_annual_income() は合計で動作するため互換。
        adj.monthly_data = []
        if ann_salary > 0 or ann_bonus > 0:
            adj.add_monthly_salary(
                month=12,
                salary=int(ann_salary),
                bonus=int(ann_bonus),
                withheld_tax=int(ann_tax),
                social_insurance=int(ann_si),
            )
        st.caption(f"年間合計: 給与 ¥{ann_salary:,.0f} ／ 賞与 ¥{ann_bonus:,.0f} ／ 源泉 ¥{ann_tax:,.0f} ／ 社保 ¥{ann_si:,.0f}")

    # 控除証明書
    with st.expander("📄 控除証明書"):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### 生命保険料控除")
            life_general = st.number_input("一般生命保険料", min_value=0, step=1000,
                                           value=adj.deductions['life_insurance'].get('general', 0),
                                           key="life_general")
            life_medical = st.number_input("介護医療保険料", min_value=0, step=1000,
                                           value=adj.deductions['life_insurance'].get('medical', 0),
                                           key="life_medical")
            life_pension = st.number_input("個人年金保険料", min_value=0, step=1000,
                                           value=adj.deductions['life_insurance'].get('pension', 0),
                                           key="life_pension")
            adj.set_life_insurance(life_general, life_medical, life_pension)

            st.markdown("#### 地震保険料控除")
            earthquake = st.number_input("地震保険料", min_value=0, step=1000,
                                         value=adj.deductions.get('earthquake_insurance', 0),
                                         key="earthquake")
            adj.set_earthquake_insurance(earthquake)

        with col2:
            st.markdown("#### 住宅ローン控除")
            housing_balance = st.number_input("年末残高", min_value=0, step=100000,
                                              value=adj.deductions['housing_loan'].get('balance', 0),
                                              key="housing_balance")
            housing_rate = st.number_input("控除率（%）", min_value=0.0, max_value=1.0, step=0.1,
                                           value=adj.deductions['housing_loan'].get('rate', 0.007) * 100,
                                           key="housing_rate") / 100
            if housing_balance > 0:
                adj.set_housing_loan(housing_balance, housing_rate)

            st.markdown("#### 小規模企業共済等")
            small_ent = st.number_input("掛金額", min_value=0, step=10000,
                                        value=adj.deductions.get('small_enterprise', 0),
                                        key="small_ent")
            adj.set_small_enterprise(small_ent)

    # 計算実行
    if adj.get_annual_income() > 0:
        st.markdown("---")
        result = adj.calculate_adjustment()

        st.markdown("### 📊 年末調整計算結果")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("年間給与収入", f"¥{result['年間給与収入']:,}")
        with col2:
            st.metric("課税所得", f"¥{result['課税所得']:,}")
        with col3:
            st.metric("年調年税額", f"¥{result['年調年税額']:,}")
        with col4:
            delta_color = "normal" if result['過不足額'] >= 0 else "inverse"
            st.metric(
                "過不足額",
                f"¥{abs(result['過不足額']):,}",
                delta=result['結果'],
                delta_color=delta_color
            )

        with st.expander("所得控除の内訳"):
            for name, amount in result['所得控除'].items():
                if amount > 0:
                    st.write(f"- {name}: ¥{amount:,}")

        with st.expander("詳細レポート"):
            st.text(adj.generate_report())

    # 保存ボタン
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 データを保存", key="save_yea"):
            adj.save_to_yaml()
            st.success("年末調整データを保存しました。")
    with col2:
        if st.button("📂 データを読み込み", key="load_yea"):
            if adj.load_from_yaml():
                st.success("データを読み込みました。")
                st.rerun()
            else:
                st.warning("保存データがありません。")


def _show_tax_calendar(calculator: TaxCalculator, manager: AssetManager, annual_income: int) -> None:
    """税金カレンダー"""
    st.markdown("## 📅 税金カレンダー")

    if annual_income == 0:
        st.info("年収を入力すると税金カレンダーが表示されます。")
        return

    # 車両データを準備
    vehicles_for_calendar = None
    assets_df = st.session_state.assets_df
    if assets_df is not None:
        vehicle_df = manager.get_assets_by_type("vehicle")
        if len(vehicle_df) > 0:
            vehicles_for_calendar = pd.DataFrame()
            for _, v in vehicle_df.iterrows():
                details = v.get("details_parsed", {})
                vehicles_for_calendar = pd.concat([vehicles_for_calendar, pd.DataFrame([{
                    "name": v.get("name", ""),
                    "cc": details.get("cc", 0),
                    "weight_kg": details.get("weight_kg", 0)
                }])], ignore_index=True)

    calendar_df = calculator.generate_tax_calendar(
        vehicles_df=vehicles_for_calendar,
        annual_income=annual_income
    )

    visualizer = AssetVisualizer(asset_manager=manager, tax_calculator=calculator)
    st.plotly_chart(visualizer.tax_calendar_chart(calendar_df), use_container_width=True)

    # 表形式でも表示
    if len(calendar_df) > 0:
        st.markdown("### 月別支払いスケジュール")
        display_df = calendar_df.copy()
        display_df['金額'] = display_df['金額'].apply(lambda x: f"¥{x:,}")
        st.dataframe(display_df, use_container_width=True, hide_index=True)


def _show_tax_settings(calculator: TaxCalculator, manager: AssetManager) -> None:
    """税金詳細設定"""
    st.markdown("## ⚙️ 詳細設定")

    st.markdown("### 控除項目（簡易計算用）")
    col1, col2, col3 = st.columns(3)
    with col1:
        medical_deduction = st.checkbox("医療費控除", key="med_ded")
        medical_amount = st.number_input("医療費控除額", min_value=0, step=10000,
                                         disabled=not medical_deduction, key="med_amt") if medical_deduction else 0
    with col2:
        furusato = st.checkbox("ふるさと納税", key="furu_ded")
        furusato_amount = st.number_input("ふるさと納税額", min_value=0, step=10000,
                                          disabled=not furusato, key="furu_amt") if furusato else 0
    with col3:
        life_insurance = st.checkbox("生命保険料控除", key="life_ded")
        life_insurance_amount = st.number_input("生命保険料控除額", min_value=0, step=10000,
                                                 disabled=not life_insurance, key="life_amt") if life_insurance else 0

    # 控除額をセッションに保存（総合サマリーで使用）
    deductions = {}
    if medical_deduction and medical_amount > 0:
        deductions["医療費控除"] = medical_amount
    if furusato and furusato_amount > 0:
        deductions["ふるさと納税"] = furusato_amount
    if life_insurance and life_insurance_amount > 0:
        deductions["生命保険料控除"] = life_insurance_amount
    st.session_state.tax_deductions = deductions

    if deductions:
        st.success(f"控除合計: ¥{sum(deductions.values()):,}（総合サマリーに反映されます）")

    st.markdown("### 年収別実効税率比較")
    visualizer = AssetVisualizer(asset_manager=manager, tax_calculator=calculator)
    st.plotly_chart(visualizer.tax_rate_comparison(), use_container_width=True)


def show_tax_tab() -> None:
    """税金計算タブ（後方互換性のため残す）"""
    calculator: TaxCalculator = st.session_state.tax_calculator
    manager: AssetManager = st.session_state.asset_manager

    st.markdown("### 年収入力")
    annual_income = st.number_input(
        "年収（円）",
        min_value=0,
        step=100000,
        value=st.session_state.annual_income or 0,
        help="給与収入（額面）を入力してください"
    )
    st.session_state.annual_income = annual_income if annual_income > 0 else None

    # 控除チェックボックス
    st.markdown("### 控除項目")
    col1, col2, col3 = st.columns(3)
    with col1:
        medical_deduction = st.checkbox("医療費控除")
        medical_amount = st.number_input("医療費控除額", min_value=0, step=10000, disabled=not medical_deduction) if medical_deduction else 0
    with col2:
        furusato = st.checkbox("ふるさと納税")
        furusato_amount = st.number_input("ふるさと納税額", min_value=0, step=10000, disabled=not furusato) if furusato else 0
    with col3:
        life_insurance = st.checkbox("生命保険料控除")
        life_insurance_amount = st.number_input("生命保険料控除額", min_value=0, step=10000, disabled=not life_insurance) if life_insurance else 0

    # 控除辞書を構築
    deductions = {}
    if medical_deduction and medical_amount > 0:
        deductions["医療費控除"] = medical_amount
    if furusato and furusato_amount > 0:
        deductions["ふるさと納税"] = furusato_amount
    if life_insurance and life_insurance_amount > 0:
        deductions["生命保険料控除"] = life_insurance_amount

    if annual_income and annual_income > 0:
        st.markdown("---")
        st.markdown("### 税金計算結果")

        # 税金計算
        tax_result = calculator.calculate_total_tax(annual_income, deductions if deductions else None)

        # 基本税金メトリック
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("所得税", f"¥{tax_result['所得税']:,.0f}")
        with col2:
            st.metric("復興特別所得税", f"¥{tax_result['復興特別所得税']:,.0f}")
        with col3:
            st.metric("住民税", f"¥{tax_result['住民税']:,.0f}")

        # 車両税（車両データがある場合）
        assets_df = st.session_state.assets_df
        vehicle_tax_total = 0
        weight_tax_total = 0
        if assets_df is not None:
            vehicle_df = manager.get_assets_by_type("vehicle")
            if len(vehicle_df) > 0:
                st.markdown("#### 車両関連税")
                col1, col2 = st.columns(2)

                for _, vehicle in vehicle_df.iterrows():
                    details = vehicle.get("details_parsed", {})
                    cc = details.get("cc", 0)
                    weight_kg = details.get("weight_kg", 0)
                    if cc > 0:
                        v_tax = calculator.calculate_vehicle_tax(cc)
                        vehicle_tax_total += v_tax
                    if weight_kg > 0:
                        w_tax = calculator.calculate_weight_tax(weight_kg)
                        weight_tax_total += w_tax // 2  # 年額換算

                with col1:
                    st.metric("自動車税（年額）", f"¥{vehicle_tax_total:,.0f}")
                with col2:
                    st.metric("重量税（年額換算）", f"¥{weight_tax_total:,.0f}")

        # 合計
        st.markdown("#### 総合計")
        total_tax = tax_result["税金合計"] + vehicle_tax_total + weight_tax_total
        take_home = annual_income - total_tax
        effective_rate = (total_tax / annual_income * 100) if annual_income > 0 else 0

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("税金合計", f"¥{total_tax:,.0f}")
        with col2:
            st.metric("手取り（税引後）", f"¥{take_home:,.0f}")
        with col3:
            st.metric("実効税率", f"{effective_rate:.1f}%")

        # グラフ
        st.markdown("---")
        st.markdown("### 税金可視化")

        # 税金カレンダー
        visualizer = AssetVisualizer(asset_manager=manager, tax_calculator=calculator)

        # 車両データフレームを準備
        vehicles_for_calendar = None
        if assets_df is not None:
            vehicle_df = manager.get_assets_by_type("vehicle")
            if len(vehicle_df) > 0:
                vehicles_for_calendar = pd.DataFrame()
                for _, v in vehicle_df.iterrows():
                    details = v.get("details_parsed", {})
                    vehicles_for_calendar = pd.concat([vehicles_for_calendar, pd.DataFrame([{
                        "name": v.get("name", ""),
                        "cc": details.get("cc", 0),
                        "weight_kg": details.get("weight_kg", 0)
                    }])], ignore_index=True)

        calendar_df = calculator.generate_tax_calendar(
            vehicles_df=vehicles_for_calendar,
            annual_income=annual_income
        )
        st.plotly_chart(visualizer.tax_calendar_chart(calendar_df), use_container_width=True)

        # 税率比較グラフ
        st.markdown("#### 年収別実効税率比較")
        st.plotly_chart(visualizer.tax_rate_comparison(), use_container_width=True)
    else:
        st.info("年収を入力すると税金計算結果が表示されます。")


def show_year_end_adjustment_tab() -> None:
    """年末調整タブ"""
    adj: YearEndAdjustment = st.session_state.year_end_adjustment

    # ファイルインポートセクション
    st.markdown("### 📥 源泉徴収票インポート")

    uploaded_file = st.file_uploader(
        "源泉徴収票をアップロード（CSV または PDF）",
        type=['csv', 'pdf'],
        key="year_end_file",
        help="令和X年度年末調整形式のCSVまたはPDFファイルをアップロードしてください"
    )

    if uploaded_file:
        file_type = uploaded_file.name.split('.')[-1].lower()

        if file_type == 'csv':
            # CSVプレビュー表示
            content = uploaded_file.read().decode('utf-8')
            uploaded_file.seek(0)

            with st.expander("CSVプレビュー", expanded=True):
                st.code(content, language=None)

            if st.button("📥 インポート実行", type="primary", key="import_file_btn"):
                try:
                    result = adj.import_from_csv(uploaded_file)
                    st.success(f"インポート完了: 年収 ¥{result.get('annual_income', 0):,}")
                    st.rerun()
                except Exception as e:
                    logger.error(f"インポートエラー: {e}")
                    st.error("インポートに失敗しました。ファイル形式を確認してください。")

        elif file_type == 'pdf':
            st.info("📄 PDFファイルが選択されました")

            if st.button("📥 PDFからインポート", type="primary", key="import_pdf_btn"):
                try:
                    result = adj.import_from_pdf(uploaded_file)
                    st.success(f"インポート完了: 年収 ¥{result.get('annual_income', 0):,}")

                    # 抽出された項目を表示
                    with st.expander("抽出されたデータ", expanded=True):
                        for key, value in result.items():
                            label = {
                                'annual_income': '支払金額',
                                'withheld_tax': '源泉徴収税額',
                                'social_insurance': '社会保険料',
                                'small_enterprise': '小規模企業共済等掛金',
                                'life_insurance_deduction': '生命保険料控除額'
                            }.get(key, key)
                            st.write(f"- {label}: ¥{value:,}")

                    st.rerun()
                except Exception as e:
                    logger.error(f"PDFインポートエラー: {e}")
                    st.error("PDFのインポートに失敗しました。ファイルを確認してください。")

    st.markdown("---")

    st.markdown("### 📅 給与・賞与入力")

    # 年度選択
    current_year = datetime.now().year
    year = st.selectbox("対象年度", options=list(range(current_year - 2, current_year + 1)),
                        index=2, key="yea_year")
    adj.year = year

    # 月別給与入力テーブル
    st.markdown("#### 月別給与データ")

    # 既存データをDataFrameに変換
    existing_df = adj.generate_monthly_df()

    # 12ヶ月分のデータを準備
    months_data = []
    for month in range(1, 13):
        existing = next((d for d in adj.monthly_data if d['month'] == month), None)
        if existing:
            months_data.append({
                '月': month,
                '給与': existing.get('salary', 0),
                '賞与': existing.get('bonus', 0),
                '源泉徴収税額': existing.get('withheld_tax', 0),
                '社会保険料': existing.get('social_insurance', 0)
            })
        else:
            months_data.append({
                '月': month,
                '給与': 0,
                '賞与': 0,
                '源泉徴収税額': 0,
                '社会保険料': 0
            })

    edit_df = pd.DataFrame(months_data)

    # データエディター
    edited_df = st.data_editor(
        edit_df,
        use_container_width=True,
        num_rows="fixed",
        column_config={
            "月": st.column_config.NumberColumn("月", disabled=True, width="small"),
            "給与": st.column_config.NumberColumn("給与", min_value=0, step=1000, format="¥%d"),
            "賞与": st.column_config.NumberColumn("賞与", min_value=0, step=10000, format="¥%d"),
            "源泉徴収税額": st.column_config.NumberColumn("源泉徴収", min_value=0, step=100, format="¥%d"),
            "社会保険料": st.column_config.NumberColumn("社保", min_value=0, step=1000, format="¥%d"),
        },
        key="salary_editor"
    )

    # データを更新
    adj.monthly_data = []
    for _, row in edited_df.iterrows():
        if row['給与'] > 0 or row['賞与'] > 0:
            adj.add_monthly_salary(
                month=int(row['月']),
                salary=int(row['給与']),
                bonus=int(row['賞与']),
                withheld_tax=int(row['源泉徴収税額']),
                social_insurance=int(row['社会保険料'])
            )

    st.markdown("---")
    st.markdown("### 📄 控除証明書")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 生命保険料控除")
        life_general = st.number_input("一般生命保険料", min_value=0, step=1000,
                                       value=adj.deductions['life_insurance'].get('general', 0))
        life_medical = st.number_input("介護医療保険料", min_value=0, step=1000,
                                       value=adj.deductions['life_insurance'].get('medical', 0))
        life_pension = st.number_input("個人年金保険料", min_value=0, step=1000,
                                       value=adj.deductions['life_insurance'].get('pension', 0))
        adj.set_life_insurance(life_general, life_medical, life_pension)

        st.markdown("#### 地震保険料控除")
        earthquake = st.number_input("地震保険料", min_value=0, step=1000,
                                     value=adj.deductions.get('earthquake_insurance', 0))
        adj.set_earthquake_insurance(earthquake)

    with col2:
        st.markdown("#### 住宅ローン控除")
        housing_balance = st.number_input("年末残高", min_value=0, step=100000,
                                          value=adj.deductions['housing_loan'].get('balance', 0))
        housing_rate = st.number_input("控除率（%）", min_value=0.0, max_value=1.0, step=0.1,
                                       value=adj.deductions['housing_loan'].get('rate', 0.007) * 100) / 100
        if housing_balance > 0:
            adj.set_housing_loan(housing_balance, housing_rate)

        st.markdown("#### 小規模企業共済等")
        small_ent = st.number_input("掛金額", min_value=0, step=10000,
                                    value=adj.deductions.get('small_enterprise', 0))
        adj.set_small_enterprise(small_ent)

    st.markdown("---")

    # 計算実行
    if st.button("📊 年末調整を計算", type="primary"):
        if adj.get_annual_income() == 0:
            st.warning("給与データを入力してください。")
        else:
            result = adj.calculate_adjustment()

            st.markdown("### 📊 計算結果")

            # メトリクス表示
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("年間給与収入", f"¥{result['年間給与収入']:,}")
                st.metric("給与所得", f"¥{result['給与所得']:,}")
            with col2:
                st.metric("課税所得", f"¥{result['課税所得']:,}")
                st.metric("年調年税額", f"¥{result['年調年税額']:,}")
            with col3:
                st.metric("源泉徴収税額", f"¥{result['源泉徴収税額']:,}")
                delta_color = "normal" if result['過不足額'] >= 0 else "inverse"
                st.metric(
                    "過不足額",
                    f"¥{abs(result['過不足額']):,}",
                    delta=result['結果'],
                    delta_color=delta_color
                )

            # 控除内訳
            with st.expander("所得控除の内訳"):
                for name, amount in result['所得控除'].items():
                    if amount > 0:
                        st.write(f"- {name}: ¥{amount:,}")

            # レポート表示
            with st.expander("詳細レポート"):
                st.text(adj.generate_report())

    # 保存ボタン
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 データを保存"):
            adj.save_to_yaml()
            st.success("年末調整データを保存しました。")
    with col2:
        if st.button("📂 データを読み込み"):
            if adj.load_from_yaml():
                st.success("データを読み込みました。")
                st.rerun()
            else:
                st.warning("保存データがありません。")


def show_bank_management_tab() -> None:
    """口座管理タブ"""
    bm: BankManager = st.session_state.bank_manager

    # 残高サマリー
    totals = bm.get_total_balance()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("総資産", f"¥{totals['総資産']:,.0f}")
    with col2:
        st.metric("総負債", f"¥{totals['総負債']:,.0f}")
    with col3:
        st.metric("純資産", f"¥{totals['純資産']:,.0f}")

    # サブタブ
    sub_tabs = st.tabs(["📊 口座一覧", "📥 CSV取り込み", "📄 PDF・画像取り込み", "📋 取引履歴", "📤 家計へ連携", "➕ 口座追加"])

    with sub_tabs[0]:
        st.markdown("### 口座一覧")

        if bm.accounts_df is not None and len(bm.accounts_df) > 0:
            for acc_type, acc_name in BankManager.ACCOUNT_TYPES.items():
                accounts = bm.get_accounts_by_type(acc_type)
                if len(accounts) > 0:
                    st.markdown(f"#### {acc_name}")
                    display_df = accounts[['account_id', 'name', 'bank_name', 'current_balance']].copy()
                    display_df.columns = ['ID', '口座名', '金融機関', '残高']
                    display_df['残高'] = display_df['残高'].apply(lambda x: f"¥{x:,.0f}")
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.info("口座が登録されていません。「口座追加」タブから追加してください。")

    with sub_tabs[1]:
        st.markdown("### CSV取り込み")

        if bm.accounts_df is None or len(bm.accounts_df) == 0:
            st.warning("先に口座を登録してください。")
        else:
            # 口座選択
            account_options = {
                row['account_id']: f"{row['name']} ({row['bank_name']})"
                for _, row in bm.accounts_df.iterrows()
            }
            selected_account = st.selectbox(
                "取り込み先口座",
                options=list(account_options.keys()),
                format_func=lambda x: account_options[x]
            )

            # 口座タイプを取得
            account_info = bm.get_account(selected_account)
            account_type = account_info.get('account_type', 'bank') if account_info else 'bank'

            # フォーマット選択
            formats = bm.get_format_list(account_type)
            format_options = {f['id']: f['name'] for f in formats}
            selected_format = st.selectbox(
                "CSVフォーマット",
                options=list(format_options.keys()),
                format_func=lambda x: format_options[x]
            )

            # ファイルアップロード
            uploaded_file = st.file_uploader("CSVファイルをアップロード", type=['csv'])

            if uploaded_file is not None:
                if st.button("📥 インポート実行", type="primary"):
                    count, errors = bm.import_from_bytes(
                        uploaded_file.read(),
                        selected_account,
                        selected_format,
                        account_type
                    )

                    if count > 0:
                        st.success(f"{count}件の取引をインポートしました。")
                        bm.save_to_csv()
                    if errors:
                        with st.expander("エラー詳細"):
                            for err in errors[:10]:
                                st.write(f"- {err}")

    with sub_tabs[2]:
        st.markdown("### 📄 PDF・画像取り込み")
        st.caption("口座取引履歴やカード明細のPDF・画像をAIで解析してインポートします")

        if bm.accounts_df is None or len(bm.accounts_df) == 0:
            st.warning("先に口座を登録してください。")
        else:
            # 全口座を選択肢に
            all_acc_options = {
                row['account_id']: f"{row['name']}（{row.get('bank_name', '')}）[{'カード' if row.get('account_type') == 'credit_card' else '銀行'}]"
                for _, row in bm.accounts_df.iterrows()
            }
            selected_acc = st.selectbox(
                "取り込み先口座",
                options=list(all_acc_options.keys()),
                format_func=lambda x: all_acc_options[x],
                key="pdf_acc_select"
            )

            acc_info = bm.get_account(selected_acc)
            is_credit = acc_info.get('account_type') == 'credit_card' if acc_info else False

            gemini_key = st.session_state.get("gemini_api_key", "")
            if not gemini_key:
                st.warning("サイドバーでGemini APIキーを設定してください")
            else:
                pdf_tab, img_tab = st.tabs(["📄 PDF取り込み", "🖼️ 画像取り込み"])

                # --- PDF取り込み ---
                with pdf_tab:
                    uploaded_pdfs = st.file_uploader(
                        "PDF明細をアップロード（複数可）",
                        type=['pdf'],
                        accept_multiple_files=True,
                        key="statement_pdf_upload"
                    )

                    if uploaded_pdfs:
                        for up in uploaded_pdfs:
                            st.info(f"📄 {html.escape(up.name)} ({up.size / 1024:.1f} KB)")

                        split_pdf = st.checkbox("PDFを分割して解析（推奨）", value=True, key="stmt_pdf_split")
                        chunk_pages = 3
                        if split_pdf:
                            chunk_pages = st.slider("1チャンクあたりのページ数", 1, 10, 3, key="stmt_pdf_chunk")

                        if st.button("🔍 PDFを解析してインポート", type="primary", key="import_stmt_pdf_btn"):
                            total_all = 0
                            all_errors = []
                            for up in uploaded_pdfs:
                                with st.spinner(f"解析中: {up.name}..."):
                                    if is_credit:
                                        count, errs = bm.import_pdf_from_bytes(
                                            up.read(), selected_acc, gemini_key,
                                            split=split_pdf, chunk_pages=chunk_pages,
                                        )
                                    else:
                                        count, errs = bm.import_bank_pdf(
                                            up.read(), selected_acc, gemini_key,
                                            is_credit_card=False,
                                            split=split_pdf, chunk_pages=chunk_pages,
                                        )
                                    total_all += count
                                    all_errors.extend(errs)

                            if total_all > 0:
                                bm.save_to_csv()
                                st.success(f"✓ 合計 {total_all}件の取引をインポートしました")
                                st.rerun()
                            elif all_errors:
                                st.error("インポートに失敗しました")
                                for err in all_errors:
                                    st.write(f"- {html.escape(str(err))}")
                            else:
                                st.warning("取引データが見つかりませんでした")

                # --- 画像取り込み ---
                with img_tab:
                    uploaded_images = st.file_uploader(
                        "取引明細の画像をアップロード（複数可）",
                        type=['jpg', 'jpeg', 'png'],
                        accept_multiple_files=True,
                        key="statement_img_upload"
                    )

                    if uploaded_images:
                        for up in uploaded_images:
                            st.info(f"🖼️ {html.escape(up.name)} ({up.size / 1024:.1f} KB)")

                        st.caption(f"📸 {len(uploaded_images)}枚（自動圧縮してAPI送信します）")

                        if st.button("🔍 画像を解析してインポート", type="primary", key="import_stmt_img_btn"):
                            import time as _time
                            total_all = 0
                            all_errors = []
                            progress_bar = st.progress(0, text="準備中...")
                            for i, up in enumerate(uploaded_images):
                                if up.size > 10 * 1024 * 1024:
                                    all_errors.append(f"{up.name}: ファイルサイズが10MBを超えています")
                                    continue
                                progress_bar.progress(i / len(uploaded_images), text=f"解析中: {up.name}（{i+1}/{len(uploaded_images)}）")
                                count, errs = bm.import_statement_image(
                                    up.read(), selected_acc, gemini_key,
                                    is_credit_card=is_credit,
                                )
                                total_all += count
                                all_errors.extend(errs)
                                if i < len(uploaded_images) - 1:
                                    _time.sleep(5)
                            progress_bar.empty()

                            if total_all > 0:
                                bm.save_to_csv()
                                st.success(f"✓ 合計 {total_all}件の取引をインポートしました")
                                st.rerun()
                            elif all_errors:
                                st.error("インポートに失敗しました")
                                for err in all_errors:
                                    st.write(f"- {html.escape(str(err))}")
                            else:
                                st.warning("取引データが見つかりませんでした")

    with sub_tabs[3]:
        st.markdown("### 取引履歴")

        if bm.transactions_df is not None and len(bm.transactions_df) > 0:
            # ⚠️ 高額振込の使途未記入チェック
            large_transfers = bm.transactions_df[
                (bm.transactions_df['amount'].abs() >= 300000) &
                (bm.transactions_df['description'].str.contains('振込', na=False))
            ]
            unpurposed = large_transfers[
                large_transfers['memo'].isna() | (large_transfers['memo'].astype(str).str.strip() == '')
            ]
            if len(unpurposed) > 0:
                st.warning(f"⚠️ 使途未記入の高額振込が **{len(unpurposed)}件** あります")

            # 高額振込セクション
            if len(large_transfers) > 0:
                with st.expander(f"💸 高額振込一覧（30万円以上）{' ⚠️ 未記入あり' if len(unpurposed) > 0 else ' ✅ 全件記入済み'}", expanded=len(unpurposed) > 0):
                    st.caption("30万円以上の振込について使途を記録してください")
                    for _, row in large_transfers.iterrows():
                        tid = row['transaction_id']
                        current_memo = str(row.get('memo', '') or '').strip()
                        col_a, col_b, col_c = st.columns([2, 3, 1])
                        with col_a:
                            date_str = pd.to_datetime(row['date']).strftime('%Y-%m-%d') if pd.notna(row['date']) else '-'
                            amt_str = f"¥{abs(row['amount']):,.0f}" if row['amount'] < 0 else f"+¥{row['amount']:,.0f}"
                            st.markdown(f"**{date_str}**  \n{html.escape(str(row['description']))}  \n{amt_str}")
                        with col_b:
                            new_memo = st.text_input(
                                "使途・目的",
                                value=current_memo,
                                placeholder="例: 車検費用、引越し費用、投資資金など",
                                key=f"purpose_{tid}"
                            )
                        with col_c:
                            st.write("")
                            st.write("")
                            if st.button("💾", key=f"save_purpose_{tid}", help="使途を保存"):
                                bm.transactions_df.loc[
                                    bm.transactions_df['transaction_id'] == tid, 'memo'
                                ] = new_memo
                                bm.save_to_csv()
                                st.success("保存しました")
                                st.rerun()

                st.markdown("---")

            # データ管理ボタン
            col_btn1, col_btn2, col_btn3 = st.columns([2, 1, 1])

            other_count = len(bm.transactions_df[bm.transactions_df['category'] == 'その他'])
            with col_btn1:
                if other_count > 0:
                    st.caption(f"⚠️ 「その他」カテゴリの取引が {other_count}件 あります")

            with col_btn2:
                if st.button("🔄 カテゴリ再分類", key="reclassify_btn"):
                    count = bm.reclassify_transactions(only_other=False)
                    if count > 0:
                        bm.save_to_csv()
                        st.success(f"✓ {count}件のカテゴリを更新しました")
                        st.rerun()
                    else:
                        st.info("再分類できる取引はありませんでした")

            with col_btn3:
                if st.button("🗑️ 重複削除", key="remove_duplicates_btn"):
                    removed = bm.remove_duplicates()
                    if removed > 0:
                        bm.save_to_csv()
                        st.success(f"✓ {removed}件の重複データを削除しました")
                        st.rerun()
                    else:
                        st.info("重複データはありませんでした")

            st.markdown("---")

            # フィルター
            col1, col2 = st.columns(2)
            with col1:
                def _acct_label(x):
                    if x == 'すべて':
                        return '全口座'
                    _a = bm.get_account(x)
                    if _a is None:
                        return str(x)
                    _n = _a.get('name', x)
                    if _n is None or (isinstance(_n, float) and pd.isna(_n)) or str(_n).strip() in ('', 'None', 'nan'):
                        return str(x)
                    return str(_n)
                filter_account = st.selectbox(
                    "口座でフィルター",
                    options=['すべて'] + bm.accounts_df['account_id'].tolist(),
                    format_func=_acct_label
                )
            with col2:
                filter_category = st.selectbox(
                    "カテゴリでフィルター",
                    options=['すべて'] + list(bm.transactions_df['category'].unique())
                )

            # データ取得
            trans = bm.get_transactions(
                account_id=None if filter_account == 'すべて' else filter_account,
                category=None if filter_category == 'すべて' else filter_category
            )

            if len(trans) > 0:
                # 編集可能テーブル（カテゴリ・メモを直接編集）
                edit_df = trans[['transaction_id', 'date', 'description', 'amount', 'balance', 'category', 'memo']].copy()
                edit_df['date'] = pd.to_datetime(edit_df['date']).dt.strftime('%Y-%m-%d')
                edit_df['memo'] = edit_df['memo'].fillna('')

                bank_categories = sorted(bm.transactions_df['category'].dropna().unique().tolist())

                edited_trans = st.data_editor(
                    edit_df,
                    column_config={
                        "transaction_id": st.column_config.TextColumn("ID", disabled=True, width="small"),
                        "date": st.column_config.TextColumn("日付", disabled=True, width="small"),
                        "description": st.column_config.TextColumn("摘要", disabled=True),
                        "amount": st.column_config.NumberColumn("金額", format="¥%d", disabled=True, width="small"),
                        "balance": st.column_config.NumberColumn("残高", format="¥%d", disabled=True, width="small"),
                        "category": st.column_config.SelectboxColumn("カテゴリ", options=bank_categories, width="small"),
                        "memo": st.column_config.TextColumn("メモ・使途"),
                    },
                    use_container_width=True,
                    hide_index=True,
                    key="trans_data_editor"
                )

                if st.button("💾 取引履歴を保存", key="save_trans_edits"):
                    for _, row in edited_trans.iterrows():
                        tid = row['transaction_id']
                        bm.transactions_df.loc[bm.transactions_df['transaction_id'] == tid, 'category'] = row['category']
                        bm.transactions_df.loc[bm.transactions_df['transaction_id'] == tid, 'memo'] = row['memo']
                    bm.save_to_csv()
                    st.success("✓ 取引履歴を保存しました")
                    st.rerun()

                # カテゴリ別集計
                st.markdown("#### カテゴリ別支出")
                breakdown = bm.get_category_breakdown(
                    account_id=None if filter_account == 'すべて' else filter_account
                )
                if len(breakdown) > 0:
                    st.dataframe(breakdown, use_container_width=True, hide_index=True)
            else:
                st.info("該当する取引がありません。")
        else:
            st.info("取引データがありません。CSVを取り込んでください。")

    with sub_tabs[4]:
        st.markdown("### 📤 口座支出を家計データへ連携")
        st.caption("口座のマイナス取引（支出）を家計データに追加します")

        if bm.transactions_df is None or len(bm.transactions_df) == 0:
            st.info("取引データがありません。まずCSVを取り込んでください。")
        else:
            # 支出データをプレビュー
            expense_df = bm.export_expenses_to_budget()

            if len(expense_df) == 0:
                st.info("連携可能な支出データがありません。")
            else:
                st.markdown(f"**{len(expense_df)}件** の支出データが見つかりました")

                # フィルター
                col1, col2 = st.columns(2)
                with col1:
                    if bm.accounts_df is not None:
                        account_options = ['すべて'] + bm.accounts_df['account_id'].tolist()
                        selected_account = st.selectbox(
                            "口座を選択",
                            options=account_options,
                            format_func=lambda x: '全口座' if x == 'すべて' else bm.get_account(x).get('name', x),
                            key="budget_export_account"
                        )
                    else:
                        selected_account = 'すべて'

                with col2:
                    # 期間フィルタ
                    date_range = st.date_input(
                        "期間",
                        value=[],
                        key="budget_export_date"
                    )

                # フィルタ適用
                account_ids = None if selected_account == 'すべて' else [selected_account]
                start_date = date_range[0] if len(date_range) >= 1 else None
                end_date = date_range[1] if len(date_range) >= 2 else None

                filtered_df = bm.export_expenses_to_budget(
                    start_date=start_date,
                    end_date=end_date,
                    account_ids=account_ids
                )

                if len(filtered_df) > 0:
                    # プレビュー表示
                    st.markdown("#### プレビュー")
                    preview_df = filtered_df.copy()
                    preview_df['日付'] = pd.to_datetime(preview_df['日付']).dt.strftime('%Y-%m-%d')
                    preview_df['金額'] = preview_df['金額'].apply(lambda x: f"¥{x:,.0f}")
                    st.dataframe(preview_df, use_container_width=True, hide_index=True)

                    # カテゴリ別集計
                    st.markdown("#### カテゴリ別集計")
                    category_summary = filtered_df.groupby('カテゴリ')['金額'].sum().reset_index()
                    category_summary['金額'] = category_summary['金額'].apply(lambda x: f"¥{x:,.0f}")
                    st.dataframe(category_summary, use_container_width=True, hide_index=True)

                    # 連携ボタン
                    st.markdown("---")
                    if st.button("📤 家計データに追加", type="primary", key="export_to_budget_btn"):
                        # 既存の家計データに追加
                        current_df = st.session_state.df
                        if current_df is not None:
                            new_df = pd.concat([current_df, filtered_df], ignore_index=True)
                            new_df = new_df.sort_values('日付').reset_index(drop=True)
                        else:
                            new_df = filtered_df

                        st.session_state.df = new_df

                        # 保存
                        loader: DataLoader = st.session_state.data_loader
                        loader.save_data(new_df)

                        st.success(f"✓ {len(filtered_df)}件の支出データを家計データに追加しました")
                        st.rerun()
                else:
                    st.info("選択した条件に該当する支出データがありません。")

    with sub_tabs[5]:
        st.markdown("### 口座追加")

        with st.form("add_account_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                acc_type = st.selectbox(
                    "口座種別",
                    options=['bank', 'securities', 'credit_card'],
                    format_func=lambda x: BankManager.ACCOUNT_TYPES.get(x, x)
                )
                acc_name = st.text_input("口座名", placeholder="例: 三菱UFJ普通")
            with col2:
                bank_name = st.text_input("金融機関名", placeholder="例: 三菱UFJ銀行")
                initial_balance = st.number_input("初期残高", min_value=0, step=10000)

            submitted = st.form_submit_button("口座を追加")
            if submitted and acc_name:
                account_id = bm.add_account(acc_name, acc_type, bank_name, initial_balance)
                bm.save_to_csv()
                st.success(f"口座「{acc_name}」を追加しました。(ID: {account_id})")
                st.rerun()

    # 保存ボタン
    st.markdown("---")
    if st.button("💾 口座データを保存"):
        bm.save_to_csv()
        st.success("口座データを保存しました。")


def _get_bank_account_options() -> list:
    """支出連携に使える口座のラベル一覧 [(id, label)]"""
    bm: BankManager = st.session_state.get("bank_manager")
    options = []
    if bm and bm.accounts_df is not None and not bm.accounts_df.empty:
        for _, acc in bm.accounts_df.iterrows():
            if acc.get('account_type') == 'credit_card':
                continue
            label = f"{acc.get('name', '')}（{acc.get('bank_name', '')}）"
            options.append((acc['account_id'], label))
    return options


def _find_account_id_by_label(label: str) -> str:
    """ラベルから口座IDを検索。見つからなければ空文字。"""
    if not label:
        return ''
    for aid, lbl in _get_bank_account_options():
        if lbl == label:
            return aid
    return ''


def _show_account_balance_editor() -> None:
    """支出タブ先頭: 銀行口座の現在預金額を直接編集できる表。"""
    bm: BankManager = st.session_state.get("bank_manager")
    if bm is None or bm.accounts_df is None or bm.accounts_df.empty:
        return

    with st.expander("🏦 口座の現在預金額（直接編集 / 支出連携先）", expanded=False):
        st.caption("数値を直接編集して「💾 残高を保存」で反映できます。ここで表示される口座名は、データ一覧・手入力の「口座」欄からも選択できます。")

        bank_rows = bm.accounts_df[bm.accounts_df['account_type'] != 'credit_card'].copy()
        if bank_rows.empty:
            st.info("登録済みの預貯金口座がありません。「🏦 資産・税金・保険」→「🏦 預貯金・口座」から追加してください。")
            return

        edit_df = pd.DataFrame({
            '口座ID': bank_rows['account_id'].values,
            '口座名': bank_rows['name'].fillna('').astype(str).values,
            '金融機関': bank_rows['bank_name'].fillna('').astype(str).values,
            '現在預金額': pd.to_numeric(bank_rows['current_balance'], errors='coerce').fillna(0).astype(float).values,
        })

        edited = st.data_editor(
            edit_df,
            column_config={
                '口座ID': st.column_config.TextColumn('ID', disabled=True, width='small'),
                '口座名': st.column_config.TextColumn('口座名'),
                '金融機関': st.column_config.TextColumn('金融機関'),
                '現在預金額': st.column_config.NumberColumn('現在預金額', format='¥%d', min_value=0, step=1000),
            },
            hide_index=True,
            use_container_width=True,
            key='_exp_acct_balance_editor',
        )

        if st.button('💾 残高を保存', type='primary', key='_exp_acct_balance_save'):
            changed = 0
            for _, row in edited.iterrows():
                aid = row['口座ID']
                def _clean_str(v):
                    if v is None:
                        return ''
                    if isinstance(v, float) and pd.isna(v):
                        return ''
                    s = str(v).strip()
                    return '' if s.lower() in ('none', 'nan') else s
                name_val = _clean_str(row.get('口座名', ''))
                bank_val = _clean_str(row.get('金融機関', ''))
                bal_raw = row.get('現在預金額', 0)
                try:
                    bal_val = float(bal_raw) if bal_raw is not None and not (isinstance(bal_raw, float) and pd.isna(bal_raw)) else 0.0
                except (TypeError, ValueError):
                    bal_val = 0.0
                # 現行の値を取得し、空文字になった項目は既存値を維持
                cur_acc = bm.get_account(aid) or {}
                if not name_val:
                    name_val = _clean_str(cur_acc.get('name', '')) or aid
                if not bank_val:
                    bank_val = _clean_str(cur_acc.get('bank_name', ''))
                updates = {
                    'name': name_val,
                    'bank_name': bank_val,
                    'current_balance': bal_val,
                }
                if bm.update_account(aid, updates):
                    changed += 1
            try:
                bm.save_to_csv()
                st.success(f"✓ {changed}件の口座情報を保存しました")
                st.rerun()
            except Exception as e:
                st.error(f"保存に失敗しました: {e}")


def show_expense_tab() -> None:
    """支出管理タブ"""
    # 口座現在預金額の直接編集パネル
    _show_account_balance_editor()

    sub_tabs = st.tabs(["📷 画像・PDF読み取り", "📥 CSV・Excel取り込み", "✏️ 手入力", "📄 データ一覧"])

    with sub_tabs[0]:
        _show_receipt_reader_main()
        st.markdown("---")
        st.subheader("📄 銀行明細 PDF・画像取り込み")
        st.caption("銀行やカードの明細PDF/画像を取り込む場合は、「🏦 資産・税金・保険」→「🏦 預貯金・口座」の口座管理機能をご利用ください。")

    with sub_tabs[1]:
        _show_file_import()

    with sub_tabs[2]:
        _show_manual_entry()

    with sub_tabs[3]:
        _show_data_list_section()


def _show_receipt_reader_main() -> None:
    """レシート読み取り（複数画像対応）"""
    st.subheader("📷 レシート読み取り")

    gemini_key = st.session_state.get("gemini_api_key", "")
    if not gemini_key:
        st.warning("サイドバーの「🤖 AI アドバイス」セクションで Gemini API キーを入力してください。")
        return

    uploaded_images = st.file_uploader(
        "レシート画像またはPDFをアップロード（複数可）",
        type=["jpg", "jpeg", "png", "webp", "pdf"],
        accept_multiple_files=True,
        key="_exp_receipt_images"
    )

    if uploaded_images:
        # プレビュー表示（PDFはアイコン表示）
        cols = st.columns(min(len(uploaded_images), 4))
        for i, img in enumerate(uploaded_images):
            with cols[i % len(cols)]:
                if img.name.lower().endswith(".pdf"):
                    st.markdown(f"📄 **{img.name}**")
                else:
                    st.image(img, caption=img.name, use_container_width=True)

        if st.button(f"🔍 {len(uploaded_images)}件を一括読み取り", type="primary", key="_exp_receipt_read"):
            results = []
            progress = st.progress(0, text="読み取り中...")
            reader = ReceiptReader(gemini_key)
            for i, img in enumerate(uploaded_images):
                progress.progress((i + 1) / len(uploaded_images), text=f"読み取り中... ({i+1}/{len(uploaded_images)})")
                try:
                    result = reader.read_receipt(img.read(), filename=img.name)
                    result["_filename"] = img.name
                    results.append(result)
                except Exception as e:
                    logger.error(f"レシート読み取りエラー ({img.name}): {e}")
                    results.append({"_filename": img.name, "_error": str(e)})
            progress.empty()
            st.session_state._exp_receipt_results = results
            ok_count = sum(1 for r in results if "_error" not in r)
            st.success(f"✓ {ok_count}/{len(results)}件の読み取り完了")

    # 読み取り結果の表示と一括追加
    results = st.session_state.get("_exp_receipt_results", [])
    if results:
        st.markdown("---")
        st.subheader(f"📋 読み取り結果（{len(results)}件）")
        loader: DataLoader = st.session_state.data_loader
        categories = loader.get_category_list()
        from datetime import datetime as _dt

        # 結果をテーブルで編集可能に表示
        edit_rows = []
        for i, r in enumerate(results):
            if "_error" in r:
                st.error(f"❌ {r['_filename']}: 読み取り失敗")
                continue
            date_value = r.get("date")
            try:
                date_str = _dt.strptime(date_value, "%Y-%m-%d").strftime("%Y-%m-%d") if date_value else _dt.now().strftime("%Y-%m-%d")
            except Exception:
                date_str = _dt.now().strftime("%Y-%m-%d")
            edit_rows.append({
                "追加": True,
                "日付": date_str,
                "カテゴリ": r.get("category", "その他"),
                "金額": float(r.get("amount", 0)),
                "メモ": f"{r.get('store_name', '')} - {r.get('memo', '')}".strip(" -"),
                "信頼度": f"{r.get('confidence', 0) * 100:.0f}%",
            })

        if edit_rows:
            edit_df = pd.DataFrame(edit_rows)
            edited = st.data_editor(
                edit_df,
                column_config={
                    "追加": st.column_config.CheckboxColumn("追加", default=True, width="small"),
                    "日付": st.column_config.TextColumn("日付"),
                    "カテゴリ": st.column_config.SelectboxColumn("カテゴリ", options=categories),
                    "金額": st.column_config.NumberColumn("金額", format="¥%.0f", min_value=0),
                    "メモ": st.column_config.TextColumn("メモ"),
                    "信頼度": st.column_config.TextColumn("信頼度", disabled=True, width="small"),
                },
                use_container_width=True,
                hide_index=True,
                key="_exp_receipt_editor"
            )

            selected = edited[edited["追加"] == True]
            if st.button(f"✅ 選択した {len(selected)}件を支出に追加", type="primary", key="_exp_receipt_add_all"):
                df = st.session_state.df if st.session_state.df is not None else loader.create_empty_dataframe()
                added = 0
                for _, row in selected.iterrows():
                    try:
                        date_obj = _dt.strptime(row["日付"], "%Y-%m-%d").date()
                        df = loader.add_entry(df, date_obj, row["カテゴリ"], row["金額"], row["メモ"])
                        added += 1
                    except Exception:
                        pass
                st.session_state.df = df
                st.session_state._exp_receipt_results = []
                st.success(f"✓ {added}件の支出を追加しました")
                st.rerun()


def _show_file_import() -> None:
    """CSV・Excelファイル取り込み（AI自動整形対応）"""
    st.subheader("📥 CSV・Excel ファイル取り込み")
    st.caption("列名や形式が違っていても、AIが自動で「日付・カテゴリ・金額・メモ」に整形します。")

    loader: DataLoader = st.session_state.data_loader
    gemini_key = st.session_state.get("gemini_api_key", "")

    uploaded_files = st.file_uploader(
        "CSV / Excel ファイルをアップロード（複数可）",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=True,
        key="_exp_file_upload"
    )

    if not uploaded_files:
        st.info("アップロードされたファイルの形式を自動判定します。列名が「日付・カテゴリ・金額・メモ」でなくてもOKです。")
        if st.button("📊 サンプルデータを読み込む", key="_exp_sample"):
            try:
                st.session_state.df = load_sample_data()
                st.success("サンプルデータを読み込みました。")
                st.rerun()
            except Exception:
                st.error("サンプルデータの読み込みに失敗しました。")
        return

    # 複数ファイルを結合して読み込む
    import io as _io
    all_dfs = []
    for uploaded in uploaded_files:
        if uploaded.size > 10 * 1024 * 1024:
            st.error(f"⚠ {uploaded.name}: ファイルサイズが10MBを超えています。スキップします。")
            continue
        suffix = Path(uploaded.name).suffix.lower()
        try:
            raw_bytes = uploaded.read()
            if suffix == ".csv":
                for enc in ['utf-8', 'utf-8-sig', 'shift_jis', 'cp932']:
                    try:
                        one_df = pd.read_csv(_io.BytesIO(raw_bytes), encoding=enc)
                        break
                    except (UnicodeDecodeError, Exception):
                        continue
                else:
                    st.error(f"⚠ {uploaded.name}: 文字コードを判定できませんでした")
                    continue
            else:
                one_df = pd.read_excel(_io.BytesIO(raw_bytes))
            one_df["_source"] = uploaded.name
            one_df["_raw_bytes"] = [raw_bytes] * len(one_df)  # 標準取り込み用に保持
            all_dfs.append((uploaded.name, suffix, raw_bytes, one_df))
        except Exception as e:
            st.error(f"⚠ {uploaded.name}: 読み込み失敗 ({e})")

    if not all_dfs:
        st.warning("有効なファイルがありませんでした。")
        return

    # 最初のファイルの構造で全体の列名を判定
    first_name, first_suffix, first_bytes, raw_df = all_dfs[0]
    # 複数ファイルの場合、同じ列構造なら結合
    if len(all_dfs) > 1:
        combinable = all(set(d.columns) == set(raw_df.columns) for _, _, _, d in all_dfs)
        if combinable:
            raw_df = pd.concat([d for _, _, _, d in all_dfs], ignore_index=True)
            st.info(f"✓ {len(all_dfs)}ファイルを結合しました（合計 {len(raw_df)} 行）")
        else:
            st.warning(f"⚠ ファイル間で列構造が異なります。最初のファイル（{first_name}）のみ処理します。")

    # _source, _raw_bytes列は表示前に除去
    display_df = raw_df.drop(columns=["_source", "_raw_bytes"], errors="ignore")

    st.markdown("##### 📄 読み込んだデータ（先頭5行）")
    st.dataframe(display_df.head(), use_container_width=True)
    st.caption(f"全 {len(display_df)} 行 × {len(display_df.columns)} 列 ｜ 列名: {', '.join(display_df.columns.astype(str))}")

    # 標準形式（日付・カテゴリ・金額・メモ）かどうか判定
    standard_cols = {'日付', 'カテゴリ', '金額', 'メモ'}
    is_standard = standard_cols.issubset(set(display_df.columns))

    if is_standard:
        st.success("✓ 標準形式（日付・カテゴリ・金額・メモ）を検出しました。")
        if st.button("📥 このまま取り込む", type="primary", key="_exp_direct_import"):
            try:
                if len(all_dfs) == 1:
                    df = loader.load_from_bytes(first_bytes, file_type="csv" if first_suffix == ".csv" else "xlsx")
                else:
                    df = display_df[['日付', 'カテゴリ', '金額', 'メモ']].copy()
                    df['日付'] = pd.to_datetime(df['日付'], errors='coerce')
                    df = df.dropna(subset=['日付'])
                st.session_state.df = df
                st.success(f"✓ {len(df)}件のデータを取り込みました。")
                st.rerun()
            except Exception as e:
                st.error(f"取り込みに失敗しました: {e}")
    else:
        st.warning("⚠ 標準形式と異なる列名です。列のマッピングを指定してください。")

        # 手動マッピングUI
        col_options = ["（使わない）"] + list(display_df.columns.astype(str))
        mc1, mc2, mc3, mc4 = st.columns(4)
        with mc1:
            date_col = st.selectbox("日付の列", col_options, key="_exp_map_date")
        with mc2:
            cat_col = st.selectbox("カテゴリの列", col_options, key="_exp_map_cat")
        with mc3:
            amount_col = st.selectbox("金額の列", col_options, key="_exp_map_amount")
        with mc4:
            memo_col = st.selectbox("メモの列", col_options, key="_exp_map_memo")

        # AI自動マッピング（Gemini利用可能な場合）
        if gemini_key:
            if st.button("🤖 AIで列を自動判定", key="_exp_ai_map"):
                with st.spinner("Gemini APIで列名を解析中..."):
                    try:
                        from modules.gemini_utils import call_gemini_with_retry
                        from google import genai
                        client = genai.Client(api_key=gemini_key)
                        sample_text = display_df.head(3).to_csv(index=False)
                        prompt = f"""以下のCSVデータのヘッダーを見て、「日付」「カテゴリ（支出種別）」「金額」「メモ（摘要・説明）」に該当する列名をJSON形式で回答してください。該当なしは null にしてください。

{sample_text}

回答形式（JSONのみ、説明不要）:
{{"date": "列名", "category": "列名", "amount": "列名", "memo": "列名"}}"""
                        response = call_gemini_with_retry(client, prompt)
                        import json, re
                        match = re.search(r'\{[\s\S]*?\}', response.text)
                        if match:
                            mapping = json.loads(match.group())
                            st.session_state._exp_ai_mapping = mapping
                            st.success("✓ AI判定完了。下の「マッピングして取り込む」を押してください。")
                            st.rerun()
                    except Exception as e:
                        st.error(f"AI判定に失敗しました: {e}")

        # AI判定結果があればマッピングに反映
        ai_map = st.session_state.get("_exp_ai_mapping")
        if ai_map:
            st.info(f"🤖 AI判定: 日付={ai_map.get('date')}, カテゴリ={ai_map.get('category')}, 金額={ai_map.get('amount')}, メモ={ai_map.get('memo')}")

        if st.button("📥 マッピングして取り込む", type="primary", key="_exp_mapped_import"):
            # AIマッピングまたは手動マッピングを使用
            if ai_map:
                d_col = ai_map.get("date")
                c_col = ai_map.get("category")
                a_col = ai_map.get("amount")
                m_col = ai_map.get("memo")
            else:
                d_col = date_col if date_col != "（使わない）" else None
                c_col = cat_col if cat_col != "（使わない）" else None
                a_col = amount_col if amount_col != "（使わない）" else None
                m_col = memo_col if memo_col != "（使わない）" else None

            if not d_col or not a_col:
                st.error("少なくとも「日付」と「金額」の列を指定してください。")
            else:
                try:
                    mapped_df = pd.DataFrame()
                    mapped_df["日付"] = pd.to_datetime(display_df[d_col], errors='coerce')
                    mapped_df["金額"] = pd.to_numeric(display_df[a_col].astype(str).str.replace(',', '').str.replace('¥', '').str.replace('円', ''), errors='coerce').fillna(0).abs()
                    mapped_df["カテゴリ"] = display_df[c_col].fillna("その他") if c_col and c_col in display_df.columns else "その他"
                    mapped_df["メモ"] = display_df[m_col].fillna("") if m_col and m_col in display_df.columns else ""
                    mapped_df = mapped_df.dropna(subset=["日付"])

                    if len(mapped_df) > 0:
                        st.session_state.df = mapped_df.reset_index(drop=True)
                        loader.save_data(st.session_state.df)
                        st.session_state._exp_ai_mapping = None
                        st.success(f"✓ {len(mapped_df)}件のデータを取り込みました。")
                        st.rerun()
                    else:
                        st.error("有効なデータが0件でした。日付列を確認してください。")
                except Exception as e:
                    st.error(f"マッピング取り込みに失敗しました: {e}")

    st.markdown("---")
    st.caption("💡 銀行やカードのCSV明細は「🏦 資産・税金・保険・保険」→「🏦 預貯金・口座」の口座管理から取り込めます。")


def _show_manual_entry() -> None:
    """手入力フォーム"""
    st.subheader("✏️ 支出を手入力")
    loader: DataLoader = st.session_state.data_loader

    acct_options = _get_bank_account_options()
    acct_labels = ["（口座連携なし）"] + [lbl for _, lbl in acct_options]

    with st.form("_exp_manual_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            date = st.date_input("日付", key="_exp_m_date")
            category = st.selectbox("カテゴリ", loader.get_category_list(), key="_exp_m_cat")
        with col2:
            amount = st.number_input("金額（円）", min_value=0.0, step=100.0, key="_exp_m_amount")
            memo = st.text_input("メモ（任意）", key="_exp_m_memo")
        col3, col4 = st.columns([2, 1])
        with col3:
            acct_label = st.selectbox("引き落とし口座（任意）", acct_labels, key="_exp_m_acct")
        with col4:
            deduct_now = st.checkbox("即時残高反映", value=True, key="_exp_m_deduct")
        submitted = st.form_submit_button("➕ 追加", type="primary")
        if submitted:
            if amount <= 0:
                st.warning("金額を入力してください。")
            else:
                df = st.session_state.df if st.session_state.df is not None else loader.create_empty_dataframe()
                try:
                    acct_stored = acct_label if acct_label != "（口座連携なし）" else ''
                    processed = False
                    if acct_stored and deduct_now:
                        aid = _find_account_id_by_label(acct_stored)
                        bm: BankManager = st.session_state.get("bank_manager")
                        if aid and bm is not None:
                            cur = bm.get_account(aid)
                            if cur is not None:
                                new_bal = float(cur.get('current_balance', 0) or 0) - float(amount)
                                bm.update_account(aid, {'current_balance': new_bal})
                                bm.save_to_csv()
                                processed = True
                    df = loader.add_entry(df, date, category, amount, memo,
                                           account=acct_stored, account_processed=processed)
                    st.session_state.df = df
                    if processed:
                        st.success(f"✓ {category} ¥{amount:,.0f} を追加し、{acct_stored} から引き落としました。")
                    else:
                        st.success(f"✓ {category} ¥{amount:,.0f} を追加しました。")
                except Exception as e:
                    st.error("追加に失敗しました。")

    # 保存・ダウンロード
    st.markdown("---")
    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        if st.button("💾 データを保存", type="primary", key="_exp_save"):
            if st.session_state.df is not None and len(st.session_state.df) > 0:
                if loader.save_data(st.session_state.df):
                    st.success("保存しました。")
                else:
                    st.error("保存に失敗しました。")
            else:
                st.warning("保存するデータがありません。")
    with col_s2:
        if st.button("📂 保存データ読込", key="_exp_load"):
            saved_df = loader.load_saved_data()
            if saved_df is not None:
                st.session_state.df = saved_df
                st.success(f"{len(saved_df)}件のデータを読み込みました。")
                st.rerun()
            else:
                st.warning("保存データがありません。")
    with col_s3:
        if st.session_state.df is not None and len(st.session_state.df) > 0:
            csv_bytes = loader.to_csv_bytes(st.session_state.df)
            st.download_button(label="📥 CSVダウンロード", data=csv_bytes, file_name="expenses.csv", mime="text/csv", key="_exp_dl")


def _show_data_list_section() -> None:
    """データ一覧セクション"""
    st.markdown("### 生データプレビュー")

    df = st.session_state.df
    loader: DataLoader = st.session_state.data_loader

    if df is None or df.empty:
        st.info("データがありません。")
        return

    # データ管理ボタン
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    with col1:
        st.caption(f"📊 全 {len(df)} 件のデータ")
    with col4:
        if st.button("🔄 再カテゴライズ", key="_dl_reclassify"):
            bm: BankManager = st.session_state.bank_manager
            memo_col = 'メモ' if 'メモ' in df.columns else None
            if memo_col:
                original_cats = df['カテゴリ'].copy()
                new_cats = df[memo_col].fillna('').astype(str).map(bm.classify_category)
                mask = new_cats != 'その他'
                changed = (new_cats[mask] != original_cats[mask]).sum()
                df.loc[mask, 'カテゴリ'] = new_cats[mask]
                st.session_state.df = df
                loader.save_data(df)
                st.success(f"✓ {int(changed)}件のカテゴリを更新しました")
                st.rerun()
    with col3:
        if st.button("🗑️ 楽天カード削除", key="_dl_rakuten"):
            import unicodedata
            original_count = len(df)
            def contains_rakuten(memo):
                if pd.isna(memo):
                    return False
                normalized = unicodedata.normalize('NFKC', str(memo)).upper().replace('-', '').replace('ー', '').replace('−', '').replace('‐', '')
                return 'ラクテンカド' in normalized or '楽天カード' in normalized or 'RAKUTENCARD' in normalized
            df_filtered = df[~df['メモ'].apply(contains_rakuten)]
            removed_count = original_count - len(df_filtered)
            if removed_count > 0:
                st.session_state.df = df_filtered.reset_index(drop=True)
                loader.save_data(st.session_state.df)
                st.success(f"✓ {removed_count}件の楽天カードデータを削除しました")
                st.rerun()
            else:
                st.info("楽天カードデータはありませんでした")
    with col2:
        if st.button("🗑️ 重複削除", key="_dl_dedup"):
            import unicodedata
            original_count = len(df)
            df_temp = df.copy()
            df_temp['normalized_memo'] = df_temp['メモ'].apply(lambda x: unicodedata.normalize('NFKC', str(x)).upper().strip() if pd.notna(x) else '')
            df_temp['date_only'] = pd.to_datetime(df_temp['日付']).dt.date
            df_temp['is_other'] = (df_temp['カテゴリ'] == 'その他').astype(int)
            df_temp = df_temp.sort_values(['date_only', 'normalized_memo', '金額', 'is_other'])
            df_dedup = df_temp.drop_duplicates(subset=['date_only', '金額', 'normalized_memo'], keep='first')
            df_dedup = df_dedup.drop(columns=['normalized_memo', 'date_only', 'is_other'])
            removed_count = original_count - len(df_dedup)
            if removed_count > 0:
                st.session_state.df = df_dedup.reset_index(drop=True)
                loader.save_data(st.session_state.df)
                st.success(f"✓ {removed_count}件の重複データを削除しました")
                st.rerun()
            else:
                st.info("重複データはありませんでした")

    st.markdown("---")

    # カテゴリ一覧
    base_categories = list(loader.categories.keys()) if hasattr(loader, 'categories') and loader.categories else ['食費', '交通費', '医療費', '通信費', '光熱費', '住居費', '保険料', '娯楽費', '教育費', '日用品', '衣服', '自己投資', '投資', 'AI費', 'IT費', '雑費', '税金', 'ふるさと納税', '車両費', '給与', 'その他']
    data_categories = df['カテゴリ'].unique().tolist() if not df.empty and 'カテゴリ' in df.columns else []
    all_categories = list(dict.fromkeys(base_categories + [c for c in data_categories if c not in base_categories]))

    # フィルタ
    filter_col1, filter_col2, filter_col3 = st.columns([2, 3, 1])
    with filter_col1:
        search_text = st.text_input("🔍 メモ検索", value="", key="_dl_search", placeholder="キーワードで絞り込み")
    with filter_col2:
        filter_categories = st.multiselect("カテゴリ絞り込み", options=all_categories, default=[], key="_dl_filter_cat")
    with filter_col3:
        st.write("")
        if st.button("🔄 表示リセット", key="_dl_reset"):
            new_ver = st.session_state.get("_dl_editor_version", 0) + 1
            for k in list(st.session_state.keys()):
                if "_dl_data_editor" in k:
                    del st.session_state[k]
            st.session_state._dl_editor_version = new_ver
            saved_df = loader.load_saved_data()
            if saved_df is not None:
                st.session_state.df = saved_df
            st.rerun()

    editor_ver = st.session_state.get("_dl_editor_version", 0)
    base_cols = ['日付', 'カテゴリ', '金額', 'メモ']
    # 口座連携列の正規化
    if '口座' not in df.columns:
        df['口座'] = ''
    df['口座'] = df['口座'].fillna('').astype(str)
    if '口座処理済' not in df.columns:
        df['口座処理済'] = False
    df['口座処理済'] = df['口座処理済'].fillna(False).astype(bool)
    st.session_state.df = df

    edit_cols = base_cols + ['口座', '口座処理済']
    edit_budget_df = df[edit_cols].copy() if all(c in df.columns for c in edit_cols) else df.copy()
    edit_budget_df['元index'] = df.index
    edit_budget_df = edit_budget_df.sort_values('日付', ascending=False).reset_index(drop=True)
    if 'メモ' not in edit_budget_df.columns:
        edit_budget_df['メモ'] = ''
    edit_budget_df['メモ'] = edit_budget_df['メモ'].fillna('')
    edit_budget_df.insert(0, '削除', False)

    if search_text:
        edit_budget_df = edit_budget_df[edit_budget_df['メモ'].str.contains(search_text, case=False, na=False)]
    if filter_categories:
        edit_budget_df = edit_budget_df[edit_budget_df['カテゴリ'].isin(filter_categories)]

    acct_options_for_list = _get_bank_account_options()
    acct_choices = [""] + [lbl for _, lbl in acct_options_for_list]

    edited_budget = st.data_editor(
        edit_budget_df,
        column_config={
            "削除": st.column_config.CheckboxColumn("🗑️", default=False, width="small"),
            "日付": st.column_config.DateColumn("日付", format="YYYY-MM-DD"),
            "カテゴリ": st.column_config.SelectboxColumn("カテゴリ", options=all_categories),
            "金額": st.column_config.NumberColumn("金額", format="¥%d"),
            "メモ": st.column_config.TextColumn("メモ"),
            "口座": st.column_config.SelectboxColumn("口座", options=acct_choices, help="引き落とし口座（空欄=連携なし）"),
            "口座処理済": st.column_config.CheckboxColumn("済", help="この行は既に口座残高へ反映済み", default=False, width="small"),
            "元index": None,
        },
        use_container_width=True,
        num_rows="dynamic",
        key=f"_dl_data_editor_v{editor_ver}",
    )

    col_save1, col_save2, col_save3, col_save4 = st.columns([1, 1, 1.2, 2])
    with col_save1:
        if st.button("💾 変更を保存", type="primary", key="_dl_save_edits"):
            full_df = df.copy()
            edited_valid = edited_budget.dropna(subset=['カテゴリ', '金額'])
            update_count = 0
            for _, row in edited_valid.iterrows():
                orig_idx = row.get('元index')
                if orig_idx is None or pd.isna(orig_idx):
                    continue
                orig_idx = int(orig_idx)
                if orig_idx not in full_df.index:
                    continue
                for col in ['日付', 'カテゴリ', '金額', 'メモ', '口座', '口座処理済']:
                    if col in row and col in full_df.columns:
                        if str(full_df.at[orig_idx, col]) != str(row[col]):
                            full_df.at[orig_idx, col] = row[col]
                            update_count += 1
            full_df = full_df.sort_values('日付').reset_index(drop=True)
            st.session_state.df = full_df
            loader.save_data(full_df)
            st.success(f"✓ 変更を保存しました（{update_count}箇所更新、全{len(full_df)}件を保持）")
            st.rerun()
    with col_save2:
        delete_count = edited_budget['削除'].sum() if '削除' in edited_budget.columns else 0
        if st.button(f"🗑️ 選択削除（{int(delete_count)}件）", key="_dl_delete_selected", disabled=delete_count == 0, type="secondary"):
            delete_indices = edited_budget[edited_budget['削除'] == True]['元index'].tolist()
            save_df = df.drop(index=delete_indices).reset_index(drop=True)
            st.session_state.df = save_df
            loader.save_data(save_df)
            st.success(f"✓ {int(delete_count)}件を削除しました（残り{len(save_df)}件）")
            st.rerun()
    with col_save3:
        # 未処理で口座が設定されている行の件数
        pending_mask = edited_budget['口座'].fillna('').astype(str).str.len().gt(0) & ~edited_budget['口座処理済'].fillna(False).astype(bool)
        pending_count = int(pending_mask.sum())
        if st.button(f"🏦 口座から一括引き落とし（{pending_count}件）",
                     key="_dl_deduct_accounts", disabled=pending_count == 0):
            bm: BankManager = st.session_state.get("bank_manager")
            if bm is None:
                st.error("BankManager が初期化されていません")
            else:
                full_df = df.copy()
                # まず編集中の変更（口座・金額等）を full_df に反映
                for _, row in edited_budget.iterrows():
                    orig_idx = row.get('元index')
                    if orig_idx is None or pd.isna(orig_idx):
                        continue
                    orig_idx = int(orig_idx)
                    if orig_idx not in full_df.index:
                        continue
                    for col in ['日付', 'カテゴリ', '金額', 'メモ', '口座', '口座処理済']:
                        if col in row and col in full_df.columns:
                            full_df.at[orig_idx, col] = row[col]

                applied = 0
                errors = 0
                for idx, row in full_df.iterrows():
                    acct_label = str(row.get('口座', '') or '')
                    processed = bool(row.get('口座処理済', False))
                    if not acct_label or processed:
                        continue
                    aid = _find_account_id_by_label(acct_label)
                    if not aid:
                        errors += 1
                        continue
                    cur = bm.get_account(aid)
                    if cur is None:
                        errors += 1
                        continue
                    amt = float(row.get('金額', 0) or 0)
                    new_bal = float(cur.get('current_balance', 0) or 0) - amt
                    bm.update_account(aid, {'current_balance': new_bal})
                    full_df.at[idx, '口座処理済'] = True
                    applied += 1

                try:
                    bm.save_to_csv()
                except Exception as e:
                    st.error(f"口座保存に失敗: {e}")
                st.session_state.df = full_df
                loader.save_data(full_df)
                msg = f"✓ {applied}件を口座から引き落としました"
                if errors:
                    msg += f"（{errors}件は口座IDを特定できず未処理）"
                st.success(msg)
                st.rerun()
    with col_save4:
        st.caption("口座欄で引き落とし先を選び、「🏦 口座から一括引き落とし」で残高を減算。「済」で処理済み管理。")


def show_assets_tax_tab() -> None:
    """資産・税金・保険 統合タブ"""
    import plotly.graph_objects as go

    # === 税金セットアップ（show_integrated_tax_tabから） ===
    calculator: TaxCalculator = st.session_state.tax_calculator
    asset_manager: AssetManager = st.session_state.asset_manager
    adj: YearEndAdjustment = st.session_state.year_end_adjustment
    current_year = datetime.now().year
    year_options = list(range(current_year - 3, current_year + 1))
    default_idx = year_options.index(adj.year) if adj.year in year_options else len(year_options) - 1
    tax_year = st.selectbox("📅 対象年度", year_options, index=default_idx, key="_at_tax_year", format_func=lambda y: f"{y}年（令和{y - 2018}年）")
    if tax_year != adj.year:
        adj.year = tax_year
        adj.save_to_yaml()
    yea_income = adj.get_annual_income()

    # === 全資産データ収集（show_assets_tabから） ===
    bank_manager = st.session_state.get("bank_manager")
    bank_accounts = []
    bank_total = 0
    if bank_manager and bank_manager.accounts_df is not None and not bank_manager.accounts_df.empty:
        for _, acc in bank_manager.accounts_df.iterrows():
            balance = acc.get('current_balance', 0) or 0
            acc_type = acc.get('account_type', '')
            if balance > 0 and acc_type != 'credit_card':
                bank_accounts.append({'name': acc.get('name', ''), 'bank_name': acc.get('bank_name', ''), 'type': acc_type, 'balance': balance})
                bank_total += balance

    financial_assets = st.session_state.get("financial_assets", [])
    fa_total = sum(fa.get("current_value", 0) for fa in financial_assets)

    insurance_list = st.session_state.get("insurance_list", [])
    usd_rate = st.session_state.get("usd_rate", 150.0)
    savings_insurances = []
    insurance_total = 0
    for ins in insurance_list:
        if ins.get("type") == "貯蓄型":
            if ins.get("currency") == "USD":
                value = int(ins.get("value_usd", 0) * usd_rate)
                annual = int(ins.get("annual_usd", 0) * usd_rate)
            else:
                value = ins.get("value", 0)
                annual = ins.get("annual", 0)
            savings_insurances.append({'name': ins.get('name', '不明'), 'value': value, 'annual': annual, 'currency': ins.get('currency', '円')})
            insurance_total += value

    manager: AssetManager = st.session_state.asset_manager
    assets_df = st.session_state.assets_df
    other_assets_value = 0
    if assets_df is not None and len(assets_df) > 0:
        other_assets_value = manager.get_total_assets_value()

    loans = st.session_state.get("loans_data", [])
    loan_total = sum(l.get('remaining_balance', 0) for l in loans)
    grand_total = bank_total + fa_total + insurance_total + other_assets_value
    net_total = grand_total - loan_total

    # === 8サブタブ ===
    sub_tabs = st.tabs(["📊 資産サマリー", "🏦 預貯金・口座", "💹 金融資産", "🛡️ 保険", "🏠 ローン", "💴 税金サマリー", "📝 年末調整", "🏥 医療費・ふるさと"])

    # --- 📊 資産サマリー ---
    with sub_tabs[0]:
        st.markdown("### 📊 資産サマリー")
        ct1, ct2, ct3 = st.columns(3)
        ct1.metric("総資産", f"¥{grand_total:,.0f}")
        ct2.metric("🏠 負債", f"¥{loan_total:,.0f}")
        delta = f"¥{net_total - grand_total:,.0f}" if loan_total > 0 else None
        ct3.metric("純資産", f"¥{net_total:,.0f}", delta=delta)
        cm1, cm2, cm3, cm4 = st.columns(4)
        cm1.metric("🔵 預貯金", f"¥{bank_total:,.0f}")
        cm2.metric("🟢 金融資産", f"¥{fa_total:,.0f}")
        cm3.metric("🔴 貯蓄型保険", f"¥{insurance_total:,.0f}")
        cm4.metric("🟠 その他", f"¥{other_assets_value:,.0f}")

        # ドーナツチャート
        pie_labels, pie_values, pie_colors = [], [], []
        blue_p = ["#2980b9", "#3498db", "#5dade2", "#85c1e9"]
        green_p = ["#27ae60", "#2ecc71", "#58d68d", "#82e0aa"]
        red_p = ["#c0392b", "#e74c3c", "#ec7063", "#f1948a"]
        orange_p = ["#e67e22", "#f39c12", "#f5b041", "#f8c471"]
        for i, acc in enumerate(bank_accounts):
            pie_labels.append(acc['name']); pie_values.append(acc['balance']); pie_colors.append(blue_p[i % len(blue_p)])
        for i, fa in enumerate(financial_assets):
            if fa.get("current_value", 0) > 0:
                pie_labels.append(fa['name']); pie_values.append(fa['current_value']); pie_colors.append(green_p[i % len(green_p)])
        for i, ins in enumerate(savings_insurances):
            if ins['value'] > 0:
                short = ins['name'][:8] + '…' if len(ins['name']) > 8 else ins['name']
                pie_labels.append(short); pie_values.append(ins['value']); pie_colors.append(red_p[i % len(red_p)])
        if assets_df is not None and len(assets_df) > 0:
            for i, (_, row) in enumerate(assets_df.iterrows()):
                val = row.get('current_value', 0)
                if val and val > 0:
                    pie_labels.append(row.get('name', 'その他')); pie_values.append(val); pie_colors.append(orange_p[i % len(orange_p)])
        if pie_labels:
            fig = go.Figure(data=[go.Pie(labels=pie_labels, values=pie_values, hole=0.4, textinfo='label+percent', textposition='inside', insidetextorientation='radial', marker=dict(colors=pie_colors), textfont=dict(size=11))])
            fig.update_layout(height=350, showlegend=True, legend=dict(orientation='h', y=-0.05, xanchor='center', x=0.5, font=dict(size=10)), margin=dict(t=10, b=50, l=10, r=10))
            st.plotly_chart(fig, use_container_width=True)

        with st.expander("📋 全資産一覧"):
            all_rows = []
            for acc in bank_accounts:
                bn = acc.get('bank_name', '')
                all_rows.append({"カテゴリ": "🔵 預貯金", "名称": f"{acc['name']}（{bn}）" if bn and bn != acc['name'] else acc['name'], "評価額": acc['balance']})
            for fa in financial_assets:
                all_rows.append({"カテゴリ": "🟢 金融資産", "名称": f"{fa['name']}（{fa.get('type', '')}）", "評価額": fa.get('current_value', 0)})
            for ins in savings_insurances:
                all_rows.append({"カテゴリ": "🔴 貯蓄型保険", "名称": ins['name'], "評価額": ins['value']})
            if all_rows:
                st.dataframe(pd.DataFrame(all_rows).style.format({"評価額": "¥{:,.0f}"}), use_container_width=True, hide_index=True)

    # --- 🏦 預貯金・口座 ---
    with sub_tabs[1]:
        st.markdown("#### 🏦 預貯金（直接編集可）")
        if bank_manager is not None and bank_manager.accounts_df is not None and not bank_manager.accounts_df.empty:
            _dep_df_src = bank_manager.accounts_df[bank_manager.accounts_df['account_type'] != 'credit_card'].copy()
            if _dep_df_src.empty:
                st.info("預貯金口座が登録されていません。")
            else:
                _dep_edit_df = pd.DataFrame({
                    '口座ID': _dep_df_src['account_id'].values,
                    '口座名': _dep_df_src['name'].fillna('').astype(str).replace({'None': '', 'nan': ''}).values,
                    '金融機関': _dep_df_src['bank_name'].fillna('').astype(str).replace({'None': '', 'nan': ''}).values,
                    '種別': _dep_df_src['account_type'].map({'bank': '銀行口座', 'securities': '証券口座'}).fillna(_dep_df_src['account_type']).astype(str).values,
                    '残高': pd.to_numeric(_dep_df_src['current_balance'], errors='coerce').fillna(0).astype(float).values,
                })
                _dep_edited = st.data_editor(
                    _dep_edit_df,
                    column_config={
                        '口座ID': st.column_config.TextColumn('ID', disabled=True, width='small'),
                        '口座名': st.column_config.TextColumn('口座名'),
                        '金融機関': st.column_config.TextColumn('金融機関'),
                        '種別': st.column_config.TextColumn('種別', disabled=True, width='small'),
                        '残高': st.column_config.NumberColumn('残高', format='¥%d', min_value=0, step=1000),
                    },
                    hide_index=True,
                    use_container_width=True,
                    key='_at_deposit_editor',
                )
                _dep_total_live = float(pd.to_numeric(_dep_edited['残高'], errors='coerce').fillna(0).sum())
                _mc1, _mc2 = st.columns([1, 3])
                with _mc1:
                    st.metric("預貯金合計（編集中）", f"¥{_dep_total_live:,.0f}")
                with _mc2:
                    if st.button('💾 預貯金を保存', type='primary', key='_at_deposit_save'):
                        def _c(v):
                            if v is None:
                                return ''
                            if isinstance(v, float) and pd.isna(v):
                                return ''
                            s = str(v).strip()
                            return '' if s.lower() in ('none', 'nan') else s
                        saved = 0
                        for _, _row in _dep_edited.iterrows():
                            _aid = _row['口座ID']
                            _cur = bank_manager.get_account(_aid) or {}
                            _name = _c(_row.get('口座名', '')) or _c(_cur.get('name', '')) or _aid
                            _bank = _c(_row.get('金融機関', '')) or _c(_cur.get('bank_name', ''))
                            try:
                                _bal_raw = _row.get('残高', 0)
                                _bal = float(_bal_raw) if _bal_raw is not None and not (isinstance(_bal_raw, float) and pd.isna(_bal_raw)) else 0.0
                            except (TypeError, ValueError):
                                _bal = 0.0
                            if bank_manager.update_account(_aid, {'name': _name, 'bank_name': _bank, 'current_balance': _bal}):
                                saved += 1
                        try:
                            bank_manager.save_to_csv()
                            st.success(f"✓ {saved}件の預貯金口座を保存しました")
                            st.rerun()
                        except Exception as _e:
                            st.error(f"保存に失敗しました: {_e}")
            st.metric("預貯金合計（保存済み）", f"¥{bank_total:,.0f}")
        else:
            st.info("口座が登録されていません。下の「💳 口座管理」→「➕ 口座追加」で登録してください。")

        # 口座管理（show_bank_management_tabから統合）
        if bank_manager:
            st.markdown("---")
            st.markdown("#### 💳 口座管理")
            show_bank_management_tab()

    # --- 💹 金融資産 ---
    with sub_tabs[2]:
        st.markdown("#### 💹 金融資産（iDeCo・NISA・株式等）")
        if financial_assets:
            rows = [{"資産名": fa['name'], "種別": fa.get('type', ''), "評価額": fa.get('current_value', 0)} for fa in financial_assets]
            st.dataframe(pd.DataFrame(rows).style.format({"評価額": "¥{:,.0f}"}), use_container_width=True, hide_index=True)
            st.metric("金融資産合計", f"¥{fa_total:,.0f}")
        else:
            st.info("金融資産が登録されていません。")

        st.markdown("---")
        # 編集・削除
        if financial_assets:
            st.markdown("##### 既存の金融資産を編集・削除")
            fa_names = [f"{fa['name']}（{fa.get('type', '')}）" for fa in financial_assets]
            edit_idx = st.selectbox("対象を選択", range(len(financial_assets)), format_func=lambda i: fa_names[i], key="_at_fa_edit_select")
            if edit_idx is not None:
                target = financial_assets[edit_idx]
                FA_TYPES = ["確定拠出年金（iDeCo）", "NISA", "株式", "投資信託", "債券", "外貨預金", "その他"]
                ce1, ce2, ce3 = st.columns([2, 2, 1])
                with ce1:
                    edit_name = st.text_input("資産名", value=target['name'], key="_at_fa_edit_name")
                with ce2:
                    type_idx = FA_TYPES.index(target.get('type', 'その他')) if target.get('type', 'その他') in FA_TYPES else len(FA_TYPES) - 1
                    edit_type = st.selectbox("種別", FA_TYPES, index=type_idx, key="_at_fa_edit_type")
                with ce3:
                    edit_value = st.number_input("評価額（円）", min_value=0, step=10000, value=int(target.get('current_value', 0)), key="_at_fa_edit_value")
                cb1, cb2, _ = st.columns([1, 1, 3])
                with cb1:
                    if st.button("💾 更新", key="_at_fa_update"):
                        st.session_state.financial_assets[edit_idx] = {"name": edit_name, "type": edit_type, "current_value": edit_value}
                        save_user_settings(get_current_settings())
                        st.success(f"「{edit_name}」を更新しました")
                        st.rerun()
                with cb2:
                    if st.button("🗑️ 削除", key="_at_fa_delete", type="secondary"):
                        removed = st.session_state.financial_assets.pop(edit_idx)
                        save_user_settings(get_current_settings())
                        st.success(f"「{removed['name']}」を削除しました")
                        st.rerun()

        st.markdown("##### 金融資産を追加")
        with st.form("_at_add_fa_form", clear_on_submit=True):
            FA_TYPES = ["確定拠出年金（iDeCo）", "NISA", "株式", "投資信託", "債券", "外貨預金", "その他"]
            ca1, ca2, ca3 = st.columns([2, 2, 1])
            with ca1:
                new_name = st.text_input("資産名", placeholder="例: iDeCo, 楽天NISA")
            with ca2:
                new_type = st.selectbox("種別", FA_TYPES)
            with ca3:
                new_value = st.number_input("評価額（円）", min_value=0, step=10000)
            if st.form_submit_button("➕ 追加"):
                if new_name:
                    st.session_state.financial_assets.append({"name": new_name, "type": new_type, "current_value": new_value})
                    save_user_settings(get_current_settings())
                    st.success(f"「{new_name}」を追加しました")
                    st.rerun()

        with st.expander("📦 その他資産（暗号化: 車両・不動産）"):
            crypto: CryptoManager = st.session_state.crypto_manager
            if crypto.has_encrypted_data() and not st.session_state.asset_unlocked:
                st.info("🔐 暗号化された資産データがあります")
                with st.form("_at_unlock_form"):
                    password = st.text_input("パスワード", type="password")
                    if st.form_submit_button("🔓 復号"):
                        if password and manager.load_encrypted(crypto, password):
                            st.session_state.assets_df = manager.df
                            st.session_state.asset_password = password
                            st.session_state.asset_unlocked = True
                            st.rerun()
                        else:
                            st.error("パスワードが違います")
            elif assets_df is not None and len(assets_df) > 0:
                for asset_type, label, icon in [("vehicle", "車両・バイク", "🚗"), ("real_estate", "不動産", "🏠")]:
                    type_df = manager.get_assets_by_type(asset_type)
                    if len(type_df) > 0:
                        st.markdown(f"**{icon} {label}**")
                        display_df = type_df[["name", "purchase_date", "purchase_price", "current_value"]].copy()
                        display_df.columns = ["名称", "購入日", "購入価格", "現在価値"]
                        st.dataframe(display_df.style.format({"購入価格": "¥{:,.0f}", "現在価値": "¥{:,.0f}"}), use_container_width=True, hide_index=True)

    # --- 🛡️ 保険 ---
    with sub_tabs[3]:
        st.markdown("#### 🛡️ 保険一覧")
        all_insurance = st.session_state.get("insurance_list", [])
        _usd_rate = st.session_state.get("usd_rate", 150.0)

        if all_insurance:
            # 全保険をテーブル表示
            ins_rows = []
            savings_annual = 0
            term_annual = 0
            for ins in all_insurance:
                if ins.get("currency") == "USD":
                    current_annual = int(ins.get("annual_usd", 0) * _usd_rate)
                    current_value = int(ins.get("value_usd", 0) * _usd_rate)
                else:
                    current_annual = ins.get("annual", 0)
                    current_value = ins.get("value", 0)
                ins_rows.append({
                    "保険名": ins.get("name", ""),
                    "種類": ins.get("type", ""),
                    "通貨": "🇺🇸 USD" if ins.get("currency") == "USD" else "🇯🇵 円",
                    "年間保険料": current_annual,
                    "解約返戻金/積立額": current_value if ins.get("type") == "貯蓄型" else 0,
                })
                if ins.get("type") == "貯蓄型":
                    savings_annual += current_annual
                else:
                    term_annual += current_annual

            st.dataframe(
                pd.DataFrame(ins_rows).style.format({"年間保険料": "¥{:,.0f}", "解約返戻金/積立額": "¥{:,.0f}"}),
                use_container_width=True, hide_index=True
            )

            im1, im2, im3 = st.columns(3)
            im1.metric("貯蓄型 年額", f"¥{savings_annual:,}")
            im2.metric("掛け捨て 年額", f"¥{term_annual:,}")
            im3.metric("合計 年額", f"¥{savings_annual + term_annual:,}")
            if insurance_total > 0:
                st.metric("貯蓄型 資産価値合計", f"¥{insurance_total:,.0f}")

            # 削除
            st.markdown("---")
            st.markdown("##### 保険を削除")
            ins_names = [f"{ins.get('name', '')}（{ins.get('type', '')}）" for ins in all_insurance]
            del_idx = st.selectbox("削除する保険", range(len(all_insurance)), format_func=lambda i: ins_names[i], key="_at_ins_del_select")
            if st.button("🗑️ 削除", key="_at_ins_del_btn", type="secondary"):
                removed = st.session_state.insurance_list.pop(del_idx)
                save_user_settings(get_current_settings())
                st.success(f"「{removed.get('name', '')}」を削除しました")
                st.rerun()
        else:
            st.info("保険が登録されていません。")

        # 保険追加フォーム
        st.markdown("---")
        st.markdown("##### 保険を追加")
        with st.form("_at_add_insurance_form", clear_on_submit=True):
            ac1, ac2 = st.columns(2)
            with ac1:
                new_ins_name = st.text_input("保険名", placeholder="例: オリックス生命")
                new_ins_type = st.selectbox("種類", ["貯蓄型", "掛け捨て"])
                new_ins_currency = st.radio("通貨", ["円", "USD"], horizontal=True)
            with ac2:
                if new_ins_currency == "USD":
                    new_annual_usd = st.number_input("年額（USD）", min_value=0.0, step=100.0)
                    new_annual_jpy = int(new_annual_usd * _usd_rate)
                    st.caption(f"円換算: ¥{new_annual_jpy:,}")
                else:
                    new_annual_jpy = st.number_input("年額（円）", min_value=0, step=10000)
                    new_annual_usd = 0.0
                if new_ins_type == "貯蓄型":
                    if new_ins_currency == "USD":
                        new_value_usd = st.number_input("解約返戻金/積立額（USD）", min_value=0.0, step=100.0)
                        new_value_jpy = int(new_value_usd * _usd_rate)
                        st.caption(f"円換算: ¥{new_value_jpy:,}")
                    else:
                        new_value_jpy = st.number_input("解約返戻金/積立額（円）", min_value=0, step=10000)
                        new_value_usd = 0.0
                else:
                    new_value_jpy = 0
                    new_value_usd = 0.0

            if st.form_submit_button("➕ 追加"):
                if new_ins_name and new_annual_jpy > 0:
                    st.session_state.insurance_list.append({
                        "name": new_ins_name, "type": new_ins_type,
                        "annual": new_annual_jpy, "value": new_value_jpy,
                        "currency": new_ins_currency,
                        "annual_usd": new_annual_usd if new_ins_currency == "USD" else 0,
                        "value_usd": new_value_usd if new_ins_currency == "USD" and new_ins_type == "貯蓄型" else 0,
                    })
                    save_user_settings(get_current_settings())
                    st.success(f"「{new_ins_name}」を追加しました")
                    st.rerun()
                else:
                    st.warning("保険名と年額を入力してください")

        # 為替レート設定
        with st.expander("💱 為替レート設定"):
            new_rate = st.number_input("USD/JPY レート", min_value=1.0, max_value=500.0, value=_usd_rate, step=0.1, key="_at_usd_rate")
            if new_rate != _usd_rate:
                st.session_state.usd_rate = new_rate
                save_user_settings(get_current_settings())

    # --- 🏠 ローン ---
    with sub_tabs[4]:
        _show_loan_tab()

    # --- 💴 税金サマリー ---
    with sub_tabs[5]:
        _show_tax_summary(calculator, asset_manager, adj, yea_income, tax_year)
        with st.expander("📅 税金カレンダー"):
            _show_tax_calendar(calculator, asset_manager, yea_income or st.session_state.annual_income or 0)
        with st.expander("⚙️ 詳細設定"):
            _show_tax_settings(calculator, asset_manager)

    # --- 📝 年末調整 ---
    with sub_tabs[6]:
        _show_year_end_adjustment(adj)

    # --- 🏥 医療費・ふるさと ---
    with sub_tabs[7]:
        st.subheader("🏥 医療費控除")
        _show_medical_deduction(calculator, adj, tax_year)
        st.markdown("---")
        st.subheader("🏡 ふるさと納税")
        _show_furusato_nouzei(calculator, adj, tax_year)


def load_profiles() -> list:
    """プロファイル一覧を読み込み"""
    import json
    if PROFILES_PATH.exists():
        with open(PROFILES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    # profiles.json が未作成 → テンプレートがあればコピーして使う
    template_path = PROFILES_PATH.parent / "profiles_template.json"
    if template_path.exists():
        import shutil
        shutil.copy2(template_path, PROFILES_PATH)
        with open(PROFILES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return [{"id": "default", "name": "自分のデータ", "data_dir": "data", "description": ""}]


def save_profiles(profiles: list) -> None:
    """プロファイル一覧を保存"""
    import json
    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROFILES_PATH, 'w', encoding='utf-8') as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)


def create_profile(name: str, description: str = "") -> dict:
    """新規プロファイルを作成してデータディレクトリを初期化"""
    import re
    profiles = load_profiles()

    # ID生成（既存と被らないようにする）
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', name.lower().strip())[:50]
    base_id = safe_name if safe_name and not safe_name.startswith(('.', '/')) else "user"
    profile_id = base_id
    existing_ids = {p["id"] for p in profiles}
    counter = 2
    while profile_id in existing_ids:
        profile_id = f"{base_id}_{counter}"
        counter += 1

    data_dir_rel = f"data/users/{profile_id}"
    data_dir = BASE_DIR / data_dir_rel
    data_dir.mkdir(parents=True, exist_ok=True)

    new_profile = {
        "id": profile_id,
        "name": name,
        "data_dir": data_dir_rel,
        "description": description,
    }
    profiles.append(new_profile)
    save_profiles(profiles)
    return new_profile


def delete_profile(profile_id: str) -> bool:
    """プロファイルを削除（default と sample は削除不可）"""
    if profile_id in ("default", "sample"):
        return False
    profiles = load_profiles()
    new_profiles = [p for p in profiles if p["id"] != profile_id]
    if len(new_profiles) == len(profiles):
        return False
    save_profiles(new_profiles)
    return True


def show_profile_selector() -> bool:
    """プロファイル選択画面を表示。選択済みならTrue"""
    if "profile_selected" in st.session_state and st.session_state.profile_selected:
        return True

    profiles = load_profiles()

    st.markdown("## 👤 ユーザーを選択してください")
    st.markdown("")

    # 既存ユーザー選択
    max_cols = min(len(profiles), 4)
    for row_start in range(0, len(profiles), max_cols):
        row_profiles = profiles[row_start:row_start + max_cols]
        cols = st.columns(max_cols)
        for i, profile in enumerate(row_profiles):
            with cols[i]:
                label = profile["name"]
                desc = profile.get("description", "")
                if st.button(label, key=f"profile_{profile['id']}", use_container_width=True):
                    st.session_state.data_dir_rel = profile["data_dir"]
                    st.session_state.profile_selected = True
                    st.session_state.profile_name = profile["name"]
                    st.session_state.profile_id = profile["id"]
                    st.rerun()
                if desc:
                    st.caption(desc)

    # 新規登録
    st.markdown("---")
    st.markdown("### ➕ 新しいユーザーを登録")
    with st.form("new_profile_form"):
        new_name = st.text_input("名前", placeholder="例: 田中花子")
        new_desc = st.text_input("説明（任意）", placeholder="例: 妻のデータ")
        submitted = st.form_submit_button("登録して開始")
        if submitted:
            if not new_name.strip():
                st.error("名前を入力してください")
            else:
                existing_names = {p["name"] for p in profiles}
                if new_name.strip() in existing_names:
                    st.error(f"「{new_name.strip()}」は既に登録されています")
                else:
                    new_profile = create_profile(new_name.strip(), new_desc.strip())
                    st.session_state.data_dir_rel = new_profile["data_dir"]
                    st.session_state.profile_selected = True
                    st.session_state.profile_name = new_profile["name"]
                    st.session_state.profile_id = new_profile["id"]
                    st.rerun()

    # ユーザー削除（default, sample以外）
    deletable = [p for p in profiles if p["id"] not in ("default", "sample")]
    if deletable:
        with st.expander("🗑️ ユーザーを削除"):
            del_target = st.selectbox(
                "削除するユーザー",
                options=deletable,
                format_func=lambda p: p["name"],
                key="del_profile_select",
            )
            if st.button("削除", key="delete_profile_btn"):
                if delete_profile(del_target["id"]):
                    st.success(f"「{del_target['name']}」を削除しました")
                    st.rerun()

    return False


def main() -> None:
    st.set_page_config(
        page_title="家計管理アプリ",
        page_icon="🏠",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    if not show_profile_selector():
        return

    init_session_state()
    sidebar_data_input()

    # サイドバー下部にプロファイル切り替え
    st.sidebar.markdown("---")
    profile_name = st.session_state.get("profile_name", "自分のデータ")
    st.sidebar.caption(f"👤 {profile_name}")
    if st.sidebar.button("ユーザー切り替え", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    st.title(APP_TITLE)
    st.caption(APP_DESCRIPTION)

    df: Optional[pd.DataFrame] = st.session_state.df

    # データがない場合は空DataFrameで代替（全タブを常に表示するため）
    loader: DataLoader = st.session_state.data_loader
    if df is None or df.empty:
        df = loader.create_empty_dataframe()
    has_data = len(df) > 0

    # メイン分析オブジェクト
    analyzer = BudgetAnalyzer(df, loader.get_ideal_ratios())
    visualizer = BudgetVisualizer(analyzer)
    advisor = FinancialAdvisor(
        analyzer,
        st.session_state.monthly_income,
        api_key=st.session_state.get("api_key"),
        gemini_api_key=st.session_state.get("gemini_api_key"),
        asset_manager=st.session_state.asset_manager,
        tax_calculator=st.session_state.tax_calculator,
        year_end_adjustment=st.session_state.year_end_adjustment,
        bank_manager=st.session_state.bank_manager,
        financial_assets=st.session_state.get("financial_assets", []),
        insurance_list=st.session_state.get("insurance_list", []),
        furusato_donations=st.session_state.get("furusato_donations", []),
    )

    tabs = st.tabs(["📋 概要", "💰 収入管理", "💳 支出管理", "🏦 資産・税金・保険", "🧭 アドバイス"])

    with tabs[0]:
        if has_data:
            show_overview_tab(analyzer, visualizer)
        else:
            st.info(
                "まだ支出データがありません。\n\n"
                "**「💳 支出管理」タブ** からデータを取り込むか、手入力で登録してみてください。\n\n"
                "- 📷 画像・PDF読み取り — レシート写真やPDFから自動入力\n"
                "- 📥 CSV・Excel取り込み — 銀行の明細ファイルを取り込み\n"
                "- ✏️ 手入力 — 1件ずつ入力\n\n"
                "「💰 収入管理」タブや「🏦 資産・税金・保険」タブも、"
                "データがなくても使い始められます。"
            )

    with tabs[1]:
        show_income_tab(analyzer)

    with tabs[2]:
        show_expense_tab()

    with tabs[3]:
        show_assets_tax_tab()

    with tabs[4]:
        if has_data:
            show_advice_tab(analyzer, advisor)
        else:
            st.info("支出データを入力すると、AIアドバイスや家計診断が利用できるようになります。")


if __name__ == "__main__":
    main()



