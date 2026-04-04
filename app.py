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
    """サイドバー：データ入力 UI"""
    st.sidebar.header("📁 データ入力")

    loader: DataLoader = st.session_state.data_loader

    # ファイルアップロード
    uploaded = st.sidebar.file_uploader(
        "CSV または Excel ファイルをアップロード",
        type=["csv", "xlsx", "xls"],
    )
    if uploaded is not None and uploaded.size > 10 * 1024 * 1024:
        st.sidebar.error("ファイルサイズが10MBを超えています。")
        uploaded = None
    if uploaded is not None:
        # 拡張子で判定
        suffix = Path(uploaded.name).suffix.lower()
        file_type = "csv" if suffix == ".csv" else "xlsx"
        try:
            df = loader.load_from_bytes(uploaded.read(), file_type=file_type)
            st.session_state.df = df  # type: ignore[assignment]
            st.sidebar.success("データを読み込みました。")
        except Exception as e:
            logger.error(f"ファイル読み込みに失敗しました: {e}")
            st.sidebar.error("ファイル読み込みに失敗しました。ファイル形式を確認してください。")

    # サンプルデータ読込
    if st.sidebar.button("サンプルデータを読み込む"):
        try:
            st.session_state.df = load_sample_data()  # type: ignore[assignment]
            st.sidebar.success("サンプルデータを読み込みました。")
        except Exception as e:
            logger.error(f"サンプルデータの読み込みに失敗しました: {e}")
            st.sidebar.error("サンプルデータの読み込みに失敗しました。")

    st.sidebar.markdown("---")
    st.sidebar.header("💾 データ保存/読み込み")

    # 保存ボタン
    col_save, col_load = st.sidebar.columns(2)
    with col_save:
        if st.button("💾 保存", use_container_width=True):
            if st.session_state.df is not None and len(st.session_state.df) > 0:
                if loader.save_data(st.session_state.df):
                    st.sidebar.success("データを保存しました。")
                else:
                    st.sidebar.error("保存に失敗しました。")
            else:
                st.sidebar.warning("保存するデータがありません。")

    with col_load:
        if st.button("📂 読込", use_container_width=True):
            saved_df = loader.load_saved_data()
            if saved_df is not None:
                st.session_state.df = saved_df
                st.sidebar.success(f"{len(saved_df)}件のデータを読み込みました。")
                st.rerun()
            else:
                st.sidebar.warning("保存データがありません。")

    # ダウンロードボタン
    if st.session_state.df is not None and len(st.session_state.df) > 0:
        csv_bytes = loader.to_csv_bytes(st.session_state.df)
        st.sidebar.download_button(
            label="📥 CSVダウンロード",
            data=csv_bytes,
            file_name="expenses.csv",
            mime="text/csv",
            use_container_width=True
        )

    # 保存データの状態表示
    if loader.has_saved_data():
        st.sidebar.caption("✓ 保存データあり")
    else:
        st.sidebar.caption("保存データなし")

    st.sidebar.markdown("---")
    st.sidebar.header("✏️ 手動入力")

    # 手動入力フォーム
    with st.sidebar.form("manual_input_form", clear_on_submit=True):
        date = st.date_input("日付")
        category = st.selectbox("カテゴリ", loader.get_category_list())
        amount = st.number_input("金額（円）", min_value=0.0, step=100.0)
        memo = st.text_input("メモ（任意）")
        submitted = st.form_submit_button("追加")

        if submitted:
            if st.session_state.df is None:
                df = loader.create_empty_dataframe()
            else:
                df = st.session_state.df
            try:
                df = loader.add_entry(df, date, category, amount, memo)
                st.session_state.df = df  # type: ignore[assignment]
                st.success("エントリを追加しました。")
            except Exception as e:
                logger.error(f"エントリの追加に失敗しました: {e}")
                st.error("エントリの追加に失敗しました。入力内容を確認してください。")

    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ 設定")

    # 総収入（年収）
    if "annual_income" not in st.session_state:
        st.session_state.annual_income = None
    annual_income = st.sidebar.number_input(
        "総収入（年収・円）",
        min_value=0,
        step=100000,
        value=st.session_state.annual_income or 0,
        help="年間の給与収入（額面）"
    )
    new_annual = annual_income if annual_income > 0 else None
    if new_annual != st.session_state.annual_income:
        st.session_state.annual_income = new_annual
        save_user_settings(get_current_settings())
    else:
        st.session_state.annual_income = new_annual

    # 月収（任意）
    monthly_income = st.sidebar.number_input(
        "月収（円）",
        min_value=0.0,
        step=10000.0,
        value=st.session_state.monthly_income or 0.0,
        help="月々の手取り収入"
    )
    new_monthly = monthly_income if monthly_income > 0 else None
    if new_monthly != st.session_state.monthly_income:
        st.session_state.monthly_income = new_monthly
        save_user_settings(get_current_settings())
    else:
        st.session_state.monthly_income = new_monthly

    # 予算（ゲージチャート用）
    budget = st.sidebar.number_input(
        "月の目標予算（円）",
        min_value=0.0,
        step=10000.0,
        value=st.session_state.budget or 0.0,
    )
    new_budget = budget if budget > 0 else None
    if new_budget != st.session_state.budget:
        st.session_state.budget = new_budget
        save_user_settings(get_current_settings())
    else:
        st.session_state.budget = new_budget

    st.sidebar.markdown("---")
    st.sidebar.subheader("🛡️ 保険管理")

    # 保険リストの初期化
    if "insurance_list" not in st.session_state:
        st.session_state.insurance_list = []

    # 為替レート設定
    if "usd_rate" not in st.session_state:
        st.session_state.usd_rate = 150.0

    # 編集モードの初期化
    if "editing_insurance_idx" not in st.session_state:
        st.session_state.editing_insurance_idx = None

    # 為替レート入力
    with st.sidebar.expander("💱 為替レート設定", expanded=False):
        usd_rate = st.number_input(
            "USD/JPY レート",
            min_value=1.0,
            max_value=500.0,
            value=st.session_state.usd_rate,
            step=0.1,
            key="usd_rate_input"
        )
        if usd_rate != st.session_state.usd_rate:
            st.session_state.usd_rate = usd_rate
            save_user_settings(get_current_settings())
        else:
            st.session_state.usd_rate = usd_rate

    # 保険追加フォーム
    with st.sidebar.expander("➕ 保険を追加", expanded=False):
        ins_name = st.text_input("保険名", key="new_ins_name", placeholder="例: オリックス生命")
        ins_type = st.selectbox(
            "種類",
            ["貯蓄型", "掛け捨て"],
            key="new_ins_type",
            help="貯蓄型は資産に計上されます"
        )

        # 通貨選択
        ins_currency = st.radio(
            "通貨",
            ["円", "USD"],
            key="new_ins_currency",
            horizontal=True
        )

        if ins_currency == "USD":
            ins_annual_usd = st.number_input("年額（USD）", min_value=0.0, step=100.0, key="new_ins_annual_usd")
            ins_annual = int(ins_annual_usd * st.session_state.usd_rate)
            st.caption(f"円換算: ¥{ins_annual:,}（@{st.session_state.usd_rate}円）")
        else:
            ins_annual = st.number_input("年額（円）", min_value=0, step=10000, key="new_ins_annual")
            ins_annual_usd = 0.0

        if ins_type == "貯蓄型":
            if ins_currency == "USD":
                ins_value_usd = st.number_input(
                    "解約返戻金/積立額（USD）",
                    min_value=0.0,
                    step=100.0,
                    key="new_ins_value_usd",
                    help="貯蓄型保険の現在価値"
                )
                ins_value = int(ins_value_usd * st.session_state.usd_rate)
                st.caption(f"円換算: ¥{ins_value:,}")
            else:
                ins_value = st.number_input(
                    "解約返戻金/積立額（円）",
                    min_value=0,
                    step=10000,
                    key="new_ins_value",
                    help="貯蓄型保険の現在価値"
                )
                ins_value_usd = 0.0
        else:
            ins_value = 0
            ins_value_usd = 0.0

        if st.button("追加", key="add_insurance"):
            if ins_name and ins_annual > 0:
                st.session_state.insurance_list.append({
                    "name": ins_name,
                    "type": ins_type,
                    "annual": ins_annual,
                    "value": ins_value,
                    "currency": ins_currency,
                    "annual_usd": ins_annual_usd if ins_currency == "USD" else 0,
                    "value_usd": ins_value_usd if ins_currency == "USD" and ins_type == "貯蓄型" else 0
                })
                save_user_settings(get_current_settings())
                st.success(f"「{ins_name}」を追加しました")
                st.rerun()

    # 保険編集フォーム
    if st.session_state.editing_insurance_idx is not None:
        idx = st.session_state.editing_insurance_idx
        if idx < len(st.session_state.insurance_list):
            ins = st.session_state.insurance_list[idx]
            with st.sidebar.expander("✏️ 保険を編集", expanded=True):
                edit_name = st.text_input("保険名", value=ins["name"], key="edit_ins_name")
                edit_type = st.selectbox(
                    "種類",
                    ["貯蓄型", "掛け捨て"],
                    index=0 if ins["type"] == "貯蓄型" else 1,
                    key="edit_ins_type"
                )

                edit_currency = st.radio(
                    "通貨",
                    ["円", "USD"],
                    index=1 if ins.get("currency") == "USD" else 0,
                    key="edit_ins_currency",
                    horizontal=True
                )

                if edit_currency == "USD":
                    edit_annual_usd = st.number_input(
                        "年額（USD）",
                        min_value=0.0,
                        step=100.0,
                        value=float(ins.get("annual_usd", 0)),
                        key="edit_ins_annual_usd"
                    )
                    edit_annual = int(edit_annual_usd * st.session_state.usd_rate)
                    st.caption(f"円換算: ¥{edit_annual:,}（@{st.session_state.usd_rate}円）")
                else:
                    edit_annual = st.number_input(
                        "年額（円）",
                        min_value=0,
                        step=10000,
                        value=ins["annual"],
                        key="edit_ins_annual"
                    )
                    edit_annual_usd = 0.0

                if edit_type == "貯蓄型":
                    if edit_currency == "USD":
                        edit_value_usd = st.number_input(
                            "解約返戻金/積立額（USD）",
                            min_value=0.0,
                            step=100.0,
                            value=float(ins.get("value_usd", 0)),
                            key="edit_ins_value_usd"
                        )
                        edit_value = int(edit_value_usd * st.session_state.usd_rate)
                        st.caption(f"円換算: ¥{edit_value:,}")
                    else:
                        edit_value = st.number_input(
                            "解約返戻金/積立額（円）",
                            min_value=0,
                            step=10000,
                            value=ins.get("value", 0),
                            key="edit_ins_value"
                        )
                        edit_value_usd = 0.0
                else:
                    edit_value = 0
                    edit_value_usd = 0.0

                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.button("💾 保存", key="save_edit_insurance"):
                        st.session_state.insurance_list[idx] = {
                            "name": edit_name,
                            "type": edit_type,
                            "annual": edit_annual,
                            "value": edit_value,
                            "currency": edit_currency,
                            "annual_usd": edit_annual_usd if edit_currency == "USD" else 0,
                            "value_usd": edit_value_usd if edit_currency == "USD" and edit_type == "貯蓄型" else 0
                        }
                        st.session_state.editing_insurance_idx = None
                        save_user_settings(get_current_settings())
                        st.success("保存しました")
                        st.rerun()
                with col_cancel:
                    if st.button("❌ キャンセル", key="cancel_edit_insurance"):
                        st.session_state.editing_insurance_idx = None
                        st.rerun()

    # 保険一覧表示
    if st.session_state.insurance_list:
        savings_total = 0
        term_total = 0
        asset_value_total = 0

        for i, ins in enumerate(st.session_state.insurance_list):
            # USD建ての場合、現在のレートで再計算
            if ins.get("currency") == "USD":
                current_annual = int(ins.get("annual_usd", 0) * st.session_state.usd_rate)
                current_value = int(ins.get("value_usd", 0) * st.session_state.usd_rate)
            else:
                current_annual = ins["annual"]
                current_value = ins.get("value", 0)

            col1, col2, col3 = st.sidebar.columns([2.5, 0.75, 0.75])
            with col1:
                icon = "💰" if ins["type"] == "貯蓄型" else "🛡️"
                currency_icon = "🇺🇸" if ins.get("currency") == "USD" else ""
                st.caption(f"{icon} {ins['name']} {currency_icon}")
                if ins.get("currency") == "USD":
                    st.caption(f"　${ins.get('annual_usd', 0):,.0f}/年 (¥{current_annual:,})")
                else:
                    st.caption(f"　¥{current_annual:,}/年")
                if ins["type"] == "貯蓄型" and current_value > 0:
                    if ins.get("currency") == "USD":
                        st.caption(f"　積立: ${ins.get('value_usd', 0):,.0f} (¥{current_value:,})")
                    else:
                        st.caption(f"　積立: ¥{current_value:,}")
            with col2:
                if st.button("✏️", key=f"edit_ins_{i}"):
                    st.session_state.editing_insurance_idx = i
                    st.rerun()
            with col3:
                if st.button("🗑️", key=f"del_ins_{i}"):
                    st.session_state.insurance_list.pop(i)
                    if st.session_state.editing_insurance_idx == i:
                        st.session_state.editing_insurance_idx = None
                    save_user_settings(get_current_settings())
                    st.rerun()

            if ins["type"] == "貯蓄型":
                savings_total += current_annual
                asset_value_total += current_value
            else:
                term_total += current_annual

        # 合計表示
        st.sidebar.markdown("---")
        st.sidebar.caption(f"📊 貯蓄型: ¥{savings_total:,}/年（資産: ¥{asset_value_total:,}）")
        st.sidebar.caption(f"📊 掛け捨て: ¥{term_total:,}/年")
        st.sidebar.caption(f"📊 **合計: ¥{savings_total + term_total:,}/年**")

        # 貯蓄型保険の資産価値をセッションに保存（資産管理で使用）
        st.session_state.savings_insurance_value = asset_value_total
        st.session_state.savings_insurance_annual = savings_total
        st.session_state.term_insurance_annual = term_total
    else:
        st.sidebar.caption("保険が登録されていません")

    # --- 金融資産管理 ---
    # --- 金融資産サマリー ---
    st.sidebar.subheader("💹 金融資産")

    if st.session_state.financial_assets:
        for fa in st.session_state.financial_assets:
            st.sidebar.caption(f"• **{fa['name']}** ({fa.get('type', '')}) — ¥{fa.get('current_value', 0):,.0f}")
        fa_total = sum(fa.get('current_value', 0) for fa in st.session_state.financial_assets)
        st.sidebar.caption(f"📊 **合計: ¥{fa_total:,}**")
    else:
        st.sidebar.caption("金融資産が登録されていません")

    # クイック追加
    with st.sidebar.expander("➕ クイック追加"):
        FA_TYPES = ["確定拠出年金（iDeCo）", "NISA", "株式", "投資信託", "債券", "外貨預金", "その他"]
        fa_name = st.text_input("資産名", key="sb_fa_name", placeholder="例: iDeCo")
        fa_type = st.selectbox("種別", FA_TYPES, key="sb_fa_type")
        fa_value = st.number_input("評価額（円）", min_value=0, step=10000, key="sb_fa_value")
        if st.button("追加", key="sb_fa_add"):
            if fa_name:
                st.session_state.financial_assets.append(
                    {"name": fa_name, "type": fa_type, "current_value": fa_value})
                save_user_settings(get_current_settings())
                st.rerun()
            else:
                st.warning("資産名を入力してください")

    st.sidebar.caption("※ 編集・削除は「🏦 資産管理」タブの「💹 金融資産」から")
    st.sidebar.markdown("---")

    # AI アドバイス設定
    st.sidebar.subheader("🤖 AI アドバイス")

    # AIプロバイダー選択
    if "ai_provider" not in st.session_state:
        st.session_state.ai_provider = "gemini"  # デフォルトはGemini（無料）

    ai_provider = st.sidebar.radio(
        "AIプロバイダー",
        options=["gemini", "claude"],
        format_func=lambda x: "Gemini (無料)" if x == "gemini" else "Claude (有料)",
        index=0 if st.session_state.ai_provider == "gemini" else 1,
        horizontal=True,
    )
    st.session_state.ai_provider = ai_provider

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
        has_api_key = True  # Geminiの場合は下のsidebar_receipt_readerで設定

    use_ai = st.sidebar.checkbox(
        "AI による自然文アドバイスを有効化",
        value=st.session_state.use_claude,
        disabled=not has_api_key if ai_provider == "claude" else False,
        help=None if has_api_key else "APIキーを入力してください。",
    )
    st.session_state.use_claude = use_ai

    sidebar_security_settings()
    sidebar_receipt_reader()
    sidebar_monthly_import()
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

    # 画像アップロード
    uploaded_image = st.sidebar.file_uploader(
        "レシート画像をアップロード",
        type=["jpg", "jpeg", "png", "webp"],
        key="receipt_image"
    )

    if uploaded_image is not None:
        # 画像プレビュー
        st.sidebar.image(uploaded_image, caption="アップロード画像", use_container_width=True)

        # 読み取り実行ボタン
        if st.sidebar.button("🔍 読み取り実行"):
            with st.sidebar.spinner("Gemini APIで解析中..."):
                try:
                    reader = ReceiptReader(gemini_key)
                    result = reader.read_receipt(uploaded_image.read())
                    st.session_state.receipt_result = result
                    st.sidebar.success("読み取り完了！")
                except Exception as e:
                    logger.error(f"レシート読み取りエラー: {e}")
                    st.sidebar.error("レシートの読み取りに失敗しました。画像を確認してください。")
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

    # 収入計算（手取り月収ベース）
    monthly_income = st.session_state.get("monthly_income", 0) or 0
    if selected_nendo != "全期間":
        # 年度内の月数を計算
        if not df.empty and '日付' in df.columns:
            months_in_nendo = df['日付'].dt.to_period('M').nunique()
            income_total = monthly_income * max(months_in_nendo, 1)
        else:
            income_total = monthly_income * 12
    else:
        income_total = monthly_income * 12  # 年間手取り

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
    savings_insurance_value = st.session_state.get("savings_insurance_value", 0)
    savings_insurance_annual = st.session_state.get("savings_insurance_annual", 0)
    term_insurance_annual = st.session_state.get("term_insurance_annual", 0)
    insurance_list = st.session_state.get("insurance_list", [])
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

    # 既存のグラフ
    col_pie, col_top = st.columns(2)

    with col_pie:
        st.markdown("### カテゴリ別支出割合")
        st.plotly_chart(visualizer.category_pie_chart(), use_container_width=True)

    with col_top:
        st.markdown("### 高額支出一覧")
        st.plotly_chart(visualizer.top_expenses_table(), use_container_width=True)


def show_income_tab(analyzer: BudgetAnalyzer) -> None:
    """収入管理タブ"""
    import json
    import plotly.graph_objects as go

    st.markdown("### 💰 月別収入管理")
    st.caption("月ごとの収入を入力し、支出との比較を確認できます")

    # 収入データの読み込み
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

    # データから月一覧を取得
    if not analyzer.df.empty and '日付' in analyzer.df.columns:
        months = sorted(analyzer.df['日付'].dt.to_period('M').unique(), reverse=True)
    else:
        months = []

    if not months:
        st.info("支出データがありません。")
        return

    # --- 口座データから給与を自動取得 ---
    bm = st.session_state.get("bank_manager")
    auto_income = {}
    if bm and bm.transactions_df is not None and len(bm.transactions_df) > 0:
        import unicodedata as _ud
        trans = bm.transactions_df.copy()
        trans['date'] = pd.to_datetime(trans['date'])
        # 条件: プラス金額 AND 摘要に「給与」を含む
        for _, row in trans[trans['amount'] > 0].iterrows():
            desc_normalized = _ud.normalize('NFKC', str(row['description'])).upper()
            if '給与' in desc_normalized or 'キュウヨ' in desc_normalized:
                ym = str(row['date'].to_period('M'))
                auto_income[ym] = auto_income.get(ym, 0) + int(row['amount'])

    # 口座連携ボタン
    if auto_income:
        new_months = [ym for ym in auto_income if ym not in income_data or income_data[ym] == 0]
        update_months = [ym for ym in auto_income if ym in income_data and income_data[ym] > 0 and income_data[ym] != auto_income[ym]]

        if new_months or update_months:
            with st.expander(f"🔗 口座から給与データを検出（{len(auto_income)}ヶ月分）", expanded=True):
                st.caption("口座のプラス取引で「給与」を含むものを自動検出しました")

                preview_rows = []
                for ym in sorted(auto_income.keys()):
                    current = income_data.get(ym, 0)
                    detected = auto_income[ym]
                    status = "新規" if current == 0 else ("差異あり" if current != detected else "一致")
                    preview_rows.append({"年月": ym, "検出額": f"¥{detected:,.0f}", "現在の入力": f"¥{current:,.0f}", "状態": status})
                st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)

                if st.button("📥 検出した給与データを収入に反映", type="primary", key="sync_income"):
                    for ym, amount in auto_income.items():
                        income_data[ym] = amount
                    st.session_state.monthly_income_data = income_data
                    try:
                        income_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(income_path, 'w', encoding='utf-8') as f:
                            json.dump(income_data, f, ensure_ascii=False, indent=2)
                        st.success(f"✓ {len(auto_income)}ヶ月分の給与データを反映しました")
                        st.rerun()
                    except IOError:
                        st.error("保存に失敗しました。再試行してください。")
        else:
            st.success("🔗 口座の給与データと収入データは同期済みです")

    # --- サマリー ---
    total_income = sum(income_data.values())
    filled_months = len([v for v in income_data.values() if v > 0])
    avg_income = total_income / filled_months if filled_months > 0 else 0

    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("総収入", f"¥{total_income:,.0f}")
    col_m2.metric("月平均収入", f"¥{avg_income:,.0f}")
    col_m3.metric("入力済み月数", f"{filled_months}ヶ月")

    st.markdown("---")

    # --- 月別収入入力 ---
    st.markdown("#### 📝 月別収入入力")

    edit_rows = []
    for m in months:
        key = str(m)
        current = income_data.get(key, 0)
        edit_rows.append({"年月": key, "収入（円）": float(current)})

    income_df = pd.DataFrame(edit_rows)
    edited_income = st.data_editor(
        income_df,
        column_config={
            "年月": st.column_config.TextColumn("年月", disabled=True, width="small"),
            "収入（円）": st.column_config.NumberColumn("収入（円）", min_value=0, step=10000, format="¥%d"),
        },
        use_container_width=True,
        hide_index=True,
        height=min(len(months) * 35 + 40, 400),
        key="income_editor"
    )

    if st.button("💾 収入データを保存", type="primary", key="save_income"):
        new_data = {}
        for _, row in edited_income.iterrows():
            val = row["収入（円）"]
            if pd.notna(val) and val > 0:
                new_data[row["年月"]] = int(val)
        st.session_state.monthly_income_data = new_data
        try:
            income_path.parent.mkdir(parents=True, exist_ok=True)
            with open(income_path, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, ensure_ascii=False, indent=2)
            st.success("✓ 収入データを保存しました")
            st.rerun()
        except IOError:
            st.error("保存に失敗しました。再試行してください。")

    st.markdown("---")

    # --- 収支比較グラフ ---
    st.markdown("#### 📊 月別 収入 vs 支出")

    monthly_expense = analyzer.monthly_spending()
    month_labels = [str(m) for m in monthly_expense.index]
    expense_values = monthly_expense.values.tolist()
    income_values = [income_data.get(m, 0) for m in month_labels]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name='収入',
        x=month_labels,
        y=income_values,
        marker_color='#2196F3',
        hovertemplate='%{x}<br>収入: ¥%{y:,.0f}<extra></extra>'
    ))
    fig.add_trace(go.Bar(
        name='支出',
        x=month_labels,
        y=expense_values,
        marker_color='#FF5252',
        hovertemplate='%{x}<br>支出: ¥%{y:,.0f}<extra></extra>'
    ))
    fig.update_layout(
        barmode='group',
        xaxis_title='月',
        yaxis_title='金額（円）',
        yaxis_tickformat=',',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        height=450,
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- 月別収支差額 ---
    st.markdown("#### 💹 月別収支差額（黒字/赤字）")
    balance_values = [inc - exp for inc, exp in zip(income_values, expense_values)]
    colors = ['#4CAF50' if b >= 0 else '#FF5252' for b in balance_values]

    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        x=month_labels,
        y=balance_values,
        marker_color=colors,
        hovertemplate='%{x}<br>収支: ¥%{y:,.0f}<extra></extra>'
    ))
    fig2.add_hline(y=0, line_dash="dash", line_color="gray")
    fig2.update_layout(
        xaxis_title='月',
        yaxis_title='収支差額（円）',
        yaxis_tickformat=',',
        height=350,
    )
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
        st.caption("家計・資産・税金・年末調整・口座情報を統合して分析します")

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
        st.caption("家計・資産・税金・保険すべてを踏まえてアドバイスします。何でもご相談ください。")

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

    # 月別給与入力
    with st.expander("📅 月別給与データ", expanded=adj.get_annual_income() == 0):
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
                    '月': month, '給与': 0, '賞与': 0, '源泉徴収税額': 0, '社会保険料': 0
                })

        edit_df = pd.DataFrame(months_data)
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
                filter_account = st.selectbox(
                    "口座でフィルター",
                    options=['すべて'] + bm.accounts_df['account_id'].tolist(),
                    format_func=lambda x: '全口座' if x == 'すべて' else bm.get_account(x).get('name', x)
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


def load_profiles() -> list:
    """プロファイル一覧を読み込み"""
    import json
    if PROFILES_PATH.exists():
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

    if df is None or df.empty:
        st.info(
            "左のサイドバーから家計データをアップロードするか、"
            "手動入力で数件登録してください。"
        )
        st.markdown(
            "- データ形式は `日付, カテゴリ, 金額, メモ` の 4 列を基本とします。\n"
            "- NotebookLM と連携する場合は、`templates/google_sheets_template.md` を参照してください。"
        )
        return

    # メイン分析オブジェクト
    loader: DataLoader = st.session_state.data_loader
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

    tabs = st.tabs(["📋 概要", "📈 グラフ", "💰 収入管理", "🧭 アドバイス", "🏦 資産管理", "💴 税金・年末調整", "💳 口座管理", "📄 データ一覧"])

    with tabs[0]:
        show_overview_tab(analyzer, visualizer)

    with tabs[1]:
        show_graphs_tab(analyzer, visualizer)

    with tabs[2]:
        show_income_tab(analyzer)

    with tabs[3]:
        show_advice_tab(analyzer, advisor)

    with tabs[4]:
        show_assets_tab()

    with tabs[5]:
        show_integrated_tax_tab()

    with tabs[6]:
        show_bank_management_tab()

    with tabs[7]:
        st.markdown("### 生データプレビュー")

        # データ管理ボタン
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.caption(f"📊 全 {len(df)} 件のデータ")
        with col3:
            if st.button("🗑️ 楽天カード削除", key="remove_rakuten_card"):
                import unicodedata
                original_count = len(df)

                # 楽天カードを含むエントリを除外
                def contains_rakuten(memo):
                    if pd.isna(memo):
                        return False
                    normalized = unicodedata.normalize('NFKC', str(memo)).upper()
                    # ダッシュ類を統一して削除
                    normalized = normalized.replace('-', '').replace('ー', '').replace('−', '').replace('‐', '')
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
            if st.button("🗑️ 重複削除", key="remove_budget_duplicates"):
                import unicodedata
                original_count = len(df)

                # 正規化してメモを比較用に作成
                df_temp = df.copy()
                df_temp['normalized_memo'] = df_temp['メモ'].apply(
                    lambda x: unicodedata.normalize('NFKC', str(x)).upper().strip() if pd.notna(x) else ''
                )
                df_temp['date_only'] = pd.to_datetime(df_temp['日付']).dt.date

                # 「その他」以外を優先するためのソートキー（その他=1, それ以外=0）
                df_temp['is_other'] = (df_temp['カテゴリ'] == 'その他').astype(int)

                # その他以外を先にソート（その他が後ろに来る）
                df_temp = df_temp.sort_values(['date_only', 'normalized_memo', '金額', 'is_other'])

                # 重複を削除（カテゴリを除外して判定、最初=その他以外を残す）
                df_dedup = df_temp.drop_duplicates(
                    subset=['date_only', '金額', 'normalized_memo'],
                    keep='first'
                )

                # 一時カラムを削除
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

        # カテゴリ一覧取得（categories.yaml + データ内の実カテゴリを統合）
        base_categories = list(loader.categories.keys()) if hasattr(loader, 'categories') and loader.categories else [
            '食費', '交通費', '医療費', '通信費', '光熱費', '住居費', '保険料',
            '娯楽費', '教育費', '日用品', '衣服', '自己投資', '投資', 'AI費', '税金', 'ふるさと納税', '車両費', '給与', 'その他'
        ]
        data_categories = df['カテゴリ'].unique().tolist() if not df.empty and 'カテゴリ' in df.columns else []
        all_categories = list(dict.fromkeys(base_categories + [c for c in data_categories if c not in base_categories]))

        # フィルタ・検索
        filter_col1, filter_col2, filter_col3 = st.columns([2, 3, 1])
        with filter_col1:
            search_text = st.text_input("🔍 メモ検索", value="", key="budget_search", placeholder="キーワードで絞り込み")
        with filter_col2:
            filter_categories = st.multiselect("カテゴリ絞り込み", options=all_categories, default=[], key="budget_filter_cat")
        with filter_col3:
            st.write("")
            if st.button("🔄 表示リセット", key="reset_budget_editor"):
                new_ver = st.session_state.get("editor_version", 0) + 1
                for k in list(st.session_state.keys()):
                    if "budget_data_editor" in k:
                        del st.session_state[k]
                st.session_state.editor_version = new_ver
                saved_df = loader.load_saved_data()
                if saved_df is not None:
                    st.session_state.df = saved_df
                st.rerun()

        # data_editorのキーをバージョン付きにして、リセット時に確実に再生成
        editor_ver = st.session_state.get("editor_version", 0)

        # 最新日付を上に表示
        base_cols = ['日付', 'カテゴリ', '金額', 'メモ']
        edit_budget_df = df[base_cols].copy() if all(c in df.columns for c in base_cols) else df.copy()
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

        edited_budget = st.data_editor(
            edit_budget_df,
            column_config={
                "削除": st.column_config.CheckboxColumn("🗑️", default=False, width="small"),
                "日付": st.column_config.DateColumn("日付", format="YYYY-MM-DD"),
                "カテゴリ": st.column_config.SelectboxColumn("カテゴリ", options=all_categories),
                "金額": st.column_config.NumberColumn("金額", format="¥%d"),
                "メモ": st.column_config.TextColumn("メモ"),
                "元index": None,
            },
            use_container_width=True,
            num_rows="dynamic",
            key=f"budget_data_editor_v{editor_ver}"
        )

        col_save1, col_save2, col_save3 = st.columns([1, 1, 3])
        with col_save1:
            if st.button("💾 変更を保存", type="primary", key="save_budget_edits"):
                save_df = edited_budget.dropna(subset=['カテゴリ', '金額'])
                save_df = save_df.drop(columns=['削除', '元index'], errors='ignore')
                save_df = save_df.sort_values('日付').reset_index(drop=True)
                st.session_state.df = save_df
                loader.save_data(save_df)
                st.success(f"✓ {len(save_df)}件のデータを保存しました")
                st.rerun()
        with col_save2:
            delete_count = edited_budget['削除'].sum() if '削除' in edited_budget.columns else 0
            if st.button(f"🗑️ 選択削除（{int(delete_count)}件）", key="delete_selected_budget",
                         disabled=delete_count == 0, type="secondary"):
                delete_indices = edited_budget[edited_budget['削除'] == True]['元index'].tolist()
                save_df = df.drop(index=delete_indices).reset_index(drop=True)
                st.session_state.df = save_df
                loader.save_data(save_df)
                st.success(f"✓ {int(delete_count)}件を削除しました（残り{len(save_df)}件）")
                st.rerun()
        with col_save3:
            st.caption("チェックで選択→「選択削除」、または直接編集→「変更を保存」")


if __name__ == "__main__":
    main()

