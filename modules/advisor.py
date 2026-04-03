"""ファイナンシャルアドバイスモジュール"""

from __future__ import annotations

import os
import json
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

import pandas as pd

from .analyzer import BudgetAnalyzer

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    try:
        import google.generativeai as genai
        GEMINI_AVAILABLE = True
    except ImportError:
        genai = None
        GEMINI_AVAILABLE = False

from .gemini_utils import call_gemini_with_retry


# デフォルトデータ保存パス
_DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"


def _get_data_dir() -> Path:
    """現在のデータディレクトリを取得（Streamlit session_state対応）"""
    try:
        import streamlit as st
        data_dir = st.session_state.get("data_dir")
        if data_dir:
            return Path(data_dir)
    except Exception:
        pass
    return _DEFAULT_DATA_DIR


def get_chat_history_path() -> Path:
    return _get_data_dir() / "chat_history.json"


def get_user_profile_path() -> Path:
    return _get_data_dir() / "user_profile.json"


def get_history_summary_path() -> Path:
    return _get_data_dir() / "history_summary.json"


# 後方互換: app.pyからimportされている
HISTORY_SUMMARY_PATH = _DEFAULT_DATA_DIR / "history_summary.json"


# デフォルトプロフィール
DEFAULT_PROFILE = {
    "name": "ユーザー",
    "goals": [],  # 財務目標
    "concerns": [],  # 気になること
    "preferences": {},  # 好みや制約
    "life_events": [],  # ライフイベント予定
    "notes": "",  # メモ
    "created_at": None,
    "updated_at": None,
}


@dataclass
class RuleBasedAdvice:
    """ルールベースアドバイス結果"""

    summary: str
    category_warnings: List[Dict[str, Any]]
    savings_analysis: Dict[str, Any]
    anomalies: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FinancialAdvisor:
    """ファイナンシャルアドバイザー

    家計データ、資産、税金、年末調整、口座情報を統合して
    包括的なファイナンシャルアドバイスを提供します。
    """

    # システムプロンプト
    SYSTEM_PROMPT = """あなたは専属のファイナンシャルプランナーです。
お客様の家計・資産・税金・保険に関する全ての情報を把握しており、
長期的な視点で資産形成と家計改善をサポートします。

【コミュニケーションスタイル】
- 丁寧な敬語で対応してください
- 親しみやすく、でも専門的なアドバイスを心がけてください
- 具体的な数字を使って説明してください
- 不安を煽らず、前向きな提案を心がけてください
- 日本の税制・社会保険制度を踏まえたアドバイスをしてください

【得意分野】
- 家計の見直し・最適化
- 資産運用（NISA、iDeCo、投資信託）
- 税金対策（所得税、住民税、各種控除）
- 年末調整・確定申告
- 保険の見直し
- 老後資金計画
"""

    def __init__(
        self,
        analyzer: BudgetAnalyzer,
        monthly_income: Optional[float] = None,
        claude_model: str = "claude-3-5-sonnet-20241022",
        api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        asset_manager: Optional[Any] = None,
        tax_calculator: Optional[Any] = None,
        year_end_adjustment: Optional[Any] = None,
        bank_manager: Optional[Any] = None,
        financial_assets: Optional[List] = None,
        insurance_list: Optional[List] = None,
        furusato_donations: Optional[List] = None,
    ) -> None:
        self.analyzer = analyzer
        self.monthly_income = monthly_income
        self.claude_model = claude_model
        self.api_key = api_key
        self.gemini_api_key = gemini_api_key
        self.asset_manager = asset_manager
        self.tax_calculator = tax_calculator
        self.year_end_adjustment = year_end_adjustment
        self.bank_manager = bank_manager
        self.financial_assets = financial_assets or []
        self.insurance_list = insurance_list or []
        self.furusato_donations = furusato_donations or []

    def _build_comprehensive_context(self) -> str:
        """全データソースから包括的なコンテキストを構築（匿名化版）

        注意: 外部APIに送信されるため、個人特定情報は含めない。
        金額は概算レンジ、名称は匿名化して送信する。
        """
        sections = []

        # 0. プロフィール（目標のみ、個人名を除去）
        profile_context = self._build_profile_context()
        if profile_context:
            sections.append(profile_context)

        # 1. 家計データ（比率中心、概算で送信）
        stats = self.analyzer.statistics_summary()
        comparison = self.analyzer.compare_with_ideal()

        def _round_amount(val):
            """金額を概算に丸める（万円単位）"""
            return round(val / 10000) * 10000

        income_text = f"約¥{_round_amount(self.monthly_income):,.0f}" if self.monthly_income else "未設定"

        sections.append(f"""【家計概要】
- 推定月収: {income_text}
- 月平均支出: 約¥{_round_amount(stats['average_monthly']):,.0f}
- 記録件数: {stats['num_transactions']}件
- トレンド: {stats['trend'].get('trend', '不明')} （変化率 {stats['trend'].get('change', 0):.1f}%）
""")

        # カテゴリ別支出（比率のみ、金額は送信しない）
        comp_rows = []
        for category, row in comparison.iterrows():
            comp_rows.append(f"  - {category}: 実際 {row['実際']*100:.1f}% / 理想 {row['理想']*100:.1f}% → {row['評価']}")
        sections.append("【カテゴリ別支出比率】\n" + "\n".join(comp_rows[:10]))

        # 2. 資産データ（カテゴリ合計のみ、個別名称は送信しない）
        if self.asset_manager and hasattr(self.asset_manager, 'df') and self.asset_manager.df is not None:
            total_assets = self.asset_manager.get_total_assets_value()

            asset_lines = [f"- 総資産: 約¥{_round_amount(total_assets):,.0f}"]

            for asset_type in ['financial', 'vehicle', 'real_estate']:
                type_df = self.asset_manager.get_assets_by_type(asset_type)
                if len(type_df) > 0:
                    type_total = type_df['current_value'].sum()
                    type_name = {'financial': '金融資産', 'vehicle': '車両', 'real_estate': '不動産'}[asset_type]
                    asset_lines.append(f"  - {type_name}: 約¥{_round_amount(type_total):,.0f}（{len(type_df)}件）")

            sections.append("【資産状況】\n" + "\n".join(asset_lines))

        # 3. 口座残高（合計のみ、口座名・銀行名は送信しない）
        if self.bank_manager and hasattr(self.bank_manager, 'accounts_df') and self.bank_manager.accounts_df is not None:
            totals = self.bank_manager.get_total_balance()
            bank_lines = [
                f"- 預貯金合計: 約¥{_round_amount(totals['総資産']):,.0f}",
                f"- 負債合計: 約¥{_round_amount(totals['総負債']):,.0f}",
                f"- 純資産: 約¥{_round_amount(totals['純資産']):,.0f}",
            ]

            sections.append("【口座残高】\n" + "\n".join(bank_lines))

        # 4. 年末調整・税金（概算のみ、控除種別のみ）
        if self.year_end_adjustment:
            yea = self.year_end_adjustment
            annual_income = yea.get_annual_income()
            if annual_income > 0:
                yea_lines = [
                    f"- 年間給与収入: 約¥{_round_amount(annual_income):,.0f}",
                    f"- 実効税率: 約{(yea.get_total_withheld_tax() / annual_income * 100):.1f}%",
                ]

                if yea.deductions:
                    deduction_types = []
                    if any(yea.deductions.get('life_insurance', {}).values()):
                        deduction_types.append("生命保険料控除")
                    if yea.deductions.get('earthquake_insurance', 0) > 0:
                        deduction_types.append("地震保険料控除")
                    if yea.deductions.get('small_enterprise', 0) > 0:
                        deduction_types.append("小規模企業共済")
                    housing = yea.deductions.get('housing_loan', {})
                    if housing.get('balance', 0) > 0:
                        deduction_types.append("住宅ローン控除")
                    if deduction_types:
                        yea_lines.append(f"- 適用控除: {', '.join(deduction_types)}")

                sections.append("【年末調整情報】\n" + "\n".join(yea_lines))

        # 5. 税金計算（概算）
        if self.tax_calculator and self.year_end_adjustment:
            annual_income = self.year_end_adjustment.get_annual_income()
            if annual_income > 0:
                tax_result = self.tax_calculator.calculate_total_tax(annual_income)
                sections.append(f"【税金概算】\n- 年間税負担: 約¥{_round_amount(tax_result['税金合計']):,.0f}")

        # 6. 金融資産（種別と合計のみ、個別名称は送信しない）
        if self.financial_assets:
            fa_total = sum(fa.get('current_value', 0) for fa in self.financial_assets)
            fa_types = set(fa.get('type', '') for fa in self.financial_assets if fa.get('type'))
            fa_lines = [
                f"- 金融資産合計: 約¥{_round_amount(fa_total):,.0f}",
                f"- 種別: {', '.join(fa_types) if fa_types else '未分類'}（{len(self.financial_assets)}件）",
            ]
            sections.append("【金融資産】\n" + "\n".join(fa_lines))

        # 7. 保険（合計と件数のみ、保険会社名は送信しない）
        if self.insurance_list:
            savings_count = sum(1 for i in self.insurance_list if i.get('type') == '貯蓄型')
            term_count = len(self.insurance_list) - savings_count
            savings_total = sum(i.get('value', 0) for i in self.insurance_list if i.get('type') == '貯蓄型')
            term_total = sum(i.get('annual', 0) for i in self.insurance_list if i.get('type') != '貯蓄型')
            ins_lines = [
                f"- 貯蓄型保険: {savings_count}件、資産価値合計 約¥{_round_amount(savings_total):,.0f}",
                f"- 掛け捨て保険: {term_count}件、年間保険料合計 約¥{_round_amount(term_total):,.0f}",
            ]
            sections.append("【保険概要】\n" + "\n".join(ins_lines))

        # 8. 医療費控除
        if self.year_end_adjustment:
            med_exp = self.year_end_adjustment.deductions.get('medical_expense', {})
            if med_exp.get('total', 0) > 0:
                annual_income = self.year_end_adjustment.get_annual_income() or 0
                med_lines = [f"- 医療費総額: ¥{med_exp['total']:,.0f}"]
                if med_exp.get('insurance_reimbursement', 0) > 0:
                    med_lines.append(f"- 保険補填額: ¥{med_exp['insurance_reimbursement']:,.0f}")
                if annual_income > 0 and self.tax_calculator:
                    med_result = self.tax_calculator.calculate_medical_deduction(
                        med_exp['total'], med_exp.get('insurance_reimbursement', 0),
                        annual_income, med_exp.get('self_medication', 0))
                    ded = med_result['standard']['deduction']
                    sav = med_result['standard']['savings']
                    med_lines.append(f"- 医療費控除額: ¥{ded:,.0f}")
                    med_lines.append(f"- 節税効果: ¥{sav:,.0f}")
                sections.append("【医療費控除】\n" + "\n".join(med_lines))

        # 9. ふるさと納税
        if self.furusato_donations:
            furu_total = sum(d.get('amount', 0) for d in self.furusato_donations)
            furu_lines = [
                f"- 寄附総額: ¥{furu_total:,.0f}",
                f"- 寄附先数: {len(set(d.get('municipality', '') for d in self.furusato_donations))}自治体",
            ]
            if self.tax_calculator and self.year_end_adjustment:
                annual_income = self.year_end_adjustment.get_annual_income() or 0
                if annual_income > 0:
                    limit = self.tax_calculator.calculate_furusato_limit(annual_income)
                    furu_lines.append(f"- 控除上限目安: ¥{limit['limit']:,.0f}")
                    furu_lines.append(f"- 残り寄附可能額: ¥{max(0, limit['limit'] - furu_total):,.0f}")
                    savings = self.tax_calculator.calculate_furusato_savings(
                        furu_total, annual_income, one_stop=False)
                    furu_lines.append(f"- 節税効果: ¥{savings['total_savings']:,.0f}")
            for d in self.furusato_donations[:5]:
                furu_lines.append(f"  - {d.get('municipality', '')}: ¥{d.get('amount', 0):,.0f}")
            sections.append("【ふるさと納税】\n" + "\n".join(furu_lines))

        return "\n\n".join(sections)

    # == チャット履歴管理 ==
    @staticmethod
    def save_chat_history(chat_history: List[Dict[str, str]]) -> bool:
        """チャット履歴を保存"""
        try:
            path = get_chat_history_path()
            path.parent.mkdir(parents=True, exist_ok=True)

            save_data = {
                "last_updated": datetime.now().isoformat(),
                "messages": chat_history
            }

            with open(path, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    @staticmethod
    def load_chat_history() -> List[Dict[str, str]]:
        """チャット履歴を読み込み"""
        try:
            path = get_chat_history_path()
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get("messages", [])
        except Exception:
            pass
        return []

    @staticmethod
    def clear_chat_history() -> bool:
        """画面のチャット履歴をクリア（JSONファイルは保持）"""
        return True

    # == ユーザープロフィール管理 ==
    @staticmethod
    def load_profile() -> Dict[str, Any]:
        """ユーザープロフィールを読み込み"""
        try:
            path = get_user_profile_path()
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return DEFAULT_PROFILE.copy()

    @staticmethod
    def save_profile(profile: Dict[str, Any]) -> bool:
        """ユーザープロフィールを保存"""
        try:
            data_dir = _get_data_dir()
            data_dir.mkdir(parents=True, exist_ok=True)
            profile["updated_at"] = datetime.now().isoformat()
            if not profile.get("created_at"):
                profile["created_at"] = profile["updated_at"]
            with open(get_user_profile_path(), 'w', encoding='utf-8') as f:
                json.dump(profile, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    # == 履歴要約管理 ==
    @staticmethod
    def load_history_summary() -> Dict[str, Any]:
        """履歴要約を読み込み"""
        try:
            path = get_history_summary_path()
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {
            "key_insights": [],
            "action_items": [],
            "discussed_topics": [],
            "financial_snapshot": {},
            "last_updated": None,
        }

    @staticmethod
    def save_history_summary(summary: Dict[str, Any]) -> bool:
        """履歴要約を保存"""
        try:
            data_dir = _get_data_dir()
            data_dir.mkdir(parents=True, exist_ok=True)
            summary["last_updated"] = datetime.now().isoformat()
            with open(get_history_summary_path(), 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def generate_history_summary(self, chat_history: List[Dict[str, str]]) -> Optional[str]:
        """チャット履歴から要約を生成してJSON形式で保存"""
        if not chat_history:
            return None

        if not GEMINI_AVAILABLE or genai is None:
            return None

        api_key = self.gemini_api_key
        if not api_key:
            return None

        # 直近の会話を取得
        recent_history = chat_history[-30:]  # 直近30件
        history_text = "\n".join(
            f"{'ユーザー' if m['role'] == 'user' else 'アドバイザー'}: {m['content']}"
            for m in recent_history
        )

        prompt = f"""以下はユーザーとファイナンシャルアドバイザーの会話履歴です。
これを分析して、次回のセッションで役立つ情報を抽出してください。

【会話履歴】
{history_text}

以下のJSON形式で出力してください（説明文なし、JSONのみ）:
{{
    "key_insights": ["ユーザーについて分かった重要な情報（3-5個）"],
    "action_items": ["ユーザーが取り組むべきこと、検討中のこと（0-3個）"],
    "discussed_topics": ["話題にしたトピック（キーワード、3-5個）"],
    "concerns": ["ユーザーが気にしていること（0-3個）"],
    "preferences": ["判明した好みや制約（0-3個）"]
}}
"""

        try:
            client = genai.Client(api_key=api_key)
            response = call_gemini_with_retry(client, prompt)
            result_text = response.text

            # JSONを抽出
            import re
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                summary_data = json.loads(json_match.group())
                summary_data["last_updated"] = datetime.now().isoformat()

                # 既存の要約とマージ
                existing = self.load_history_summary()
                for key in ["key_insights", "action_items", "discussed_topics", "concerns", "preferences"]:
                    if key in summary_data:
                        existing_items = existing.get(key, [])
                        new_items = summary_data[key]
                        # 重複を避けてマージ（最新を優先、最大10件）
                        merged = new_items + [x for x in existing_items if x not in new_items]
                        summary_data[key] = merged[:10]

                self.save_history_summary(summary_data)
                return json.dumps(summary_data, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"Summary generation error: {type(e).__name__}: {e}")
            return "[Error] サマリーの生成に失敗しました。再試行してください。"

        return None

    def _build_profile_context(self) -> str:
        """プロフィールと履歴要約からコンテキストを構築"""
        sections = []

        # プロフィール
        profile = self.load_profile()
        if profile.get("goals"):
            sections.append("【財務目標】\n" + "\n".join(f"- {g}" for g in profile["goals"]))
        if profile.get("concerns"):
            sections.append("【気になっていること】\n" + "\n".join(f"- {c}" for c in profile["concerns"]))
        if profile.get("life_events"):
            sections.append("【予定しているライフイベント】\n" + "\n".join(f"- {e}" for e in profile["life_events"]))
        if profile.get("notes"):
            sections.append(f"【メモ】\n{profile['notes']}")

        # 履歴要約
        summary = self.load_history_summary()
        if summary.get("key_insights"):
            sections.append("【これまでの相談で分かったこと】\n" + "\n".join(f"- {i}" for i in summary["key_insights"][:5]))
        if summary.get("action_items"):
            sections.append("【検討中・取り組み中のこと】\n" + "\n".join(f"- {a}" for a in summary["action_items"][:3]))
        if summary.get("discussed_topics"):
            sections.append(f"【過去に相談したトピック】\n{', '.join(summary['discussed_topics'][:5])}")

        return "\n\n".join(sections) if sections else ""

    # == ルールベースアドバイス ==
    def generate_rule_based_advice(
        self,
        anomaly_threshold: float = 2.0,
    ) -> RuleBasedAdvice:
        """統計情報と理想比率に基づくルールベースアドバイスを生成"""
        stats = self.analyzer.statistics_summary()
        comparison = self.analyzer.compare_with_ideal()

        category_warnings: List[Dict[str, Any]] = []
        for category, row in comparison.iterrows():
            eval_label = str(row["評価"])
            if eval_label == "適正":
                continue

            message = ""
            diff_pct = float(row["差分"]) * 100
            if eval_label == "超過":
                message = (
                    f"「{category}」の支出比率が理想より約 {diff_pct:.1f}% ポイント高めです。"
                    "固定費か変動費かを切り分け、翌月以降 5〜10% 程度の縮小を目標に見直してみましょう。"
                )
            elif eval_label == "節約":
                message = (
                    f"「{category}」は理想比率より抑えられています。"
                    "無理のない範囲でこの水準を維持できると、長期的な貯蓄余力が高まります。"
                )

            category_warnings.append(
                {
                    "category": category,
                    "status": eval_label,
                    "diff_ratio": float(row["差分"]),
                    "actual_ratio": float(row["実際"]),
                    "ideal_ratio": float(row["理想"]),
                    "message": message,
                }
            )

        if self.monthly_income is not None and self.monthly_income > 0:
            savings_analysis = self.analyzer.savings_potential(self.monthly_income)
        else:
            total = self.analyzer.total_spending()
            savings_analysis = {
                "current_monthly_spending": total,
                "current_monthly_savings": None,
                "current_savings_rate": None,
                "potential_additional_savings": None,
                "reduction_targets": [],
            }

        anomalies_df = self.analyzer.anomaly_detection(threshold=anomaly_threshold)
        anomalies: List[Dict[str, Any]] = []
        if isinstance(anomalies_df, pd.DataFrame) and not anomalies_df.empty:
            for _, row in anomalies_df.iterrows():
                anomalies.append(
                    {
                        "date": row["日付"],
                        "category": row["カテゴリ"],
                        "amount": float(row["金額"]),
                        "memo": row.get("メモ", ""),
                        "z_score": float(row.get("z_score", 0)),
                    }
                )

        total = float(stats["total"])
        avg_monthly = float(stats["average_monthly"])
        num_tx = int(stats["num_transactions"])
        trend = stats["trend"]
        trend_label = trend.get("trend", "不明")
        change = float(trend.get("change", 0.0))

        summary_lines = [
            f"直近のデータでは合計支出は約 ¥{total:,.0f}、月平均は約 ¥{avg_monthly:,.0f}、"
            f"記録件数は {num_tx} 件です。",
            f"全体のトレンドは「{trend_label}」（前後比較で約 {change:.1f}% の変化）と見られます。",
        ]

        if self.monthly_income:
            rate = savings_analysis.get("current_savings_rate")
            if rate is not None:
                summary_lines.append(
                    f"月収に対する現在の貯蓄率はおおよそ {rate * 100:.1f}% 程度と推定されます。"
                )

        if anomalies:
            summary_lines.append(
                f"統計的に目立つ高額支出が {len(anomalies)} 件検出されています。"
            )

        summary = "\n".join(summary_lines)

        return RuleBasedAdvice(
            summary=summary,
            category_warnings=category_warnings,
            savings_analysis=savings_analysis,
            anomalies=anomalies,
        )

    # == Claude API 連携 ==
    def _get_anthropic_client(self) -> Optional["anthropic.Anthropic"]:
        """Anthropic クライアントを初期化"""
        if anthropic is None:
            return None

        api_key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return None

        try:
            client = anthropic.Anthropic(api_key=api_key)
        except Exception:
            return None
        return client

    def generate_ai_advice(
        self,
        rule_based: Optional[RuleBasedAdvice] = None,
        max_tokens: int = 2000,
    ) -> Optional[str]:
        """Claude API を利用して包括的なアドバイスを生成"""
        client = self._get_anthropic_client()
        if client is None:
            return None

        if rule_based is None:
            rule_based = self.generate_rule_based_advice()

        context = self._build_comprehensive_context()

        user_prompt = f"""財務データを分析して、包括的なアドバイスをお願いします。

{context}

【ルールベース分析結果】
{rule_based.summary}

以下の構成でアドバイスをお願いします：

1. **現状の総合評価**（家計・資産・税金を含めた全体像）
2. **強みと改善ポイント**（具体的な数字を使って）
3. **優先度の高いアクション**（すぐにできること3つ）
4. **中長期的な提案**（3ヶ月〜1年の視点で）

Markdown形式で、見出しや箇条書きを使って読みやすくしてください。
"""

        try:
            response = client.messages.create(
                model=self.claude_model,
                max_tokens=max_tokens,
                temperature=0.4,
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except Exception as e:
            logger.error(f"Claude API Error: {type(e).__name__}: {e}")
            return "[API Error] APIとの通信に失敗しました。APIキーとネットワーク接続を確認してください。"

        try:
            if response.content and len(response.content) > 0:
                return response.content[0].text
        except Exception as e:
            logger.error(f"Claude Response Error: {type(e).__name__}: {e}")
            return "[Response Error] レスポンスの処理に失敗しました。再試行してください。"

        return None

    def generate_gemini_advice(
        self,
        rule_based: Optional[RuleBasedAdvice] = None,
    ) -> Optional[str]:
        """Gemini API を利用して包括的なアドバイスを生成"""
        if not GEMINI_AVAILABLE or genai is None:
            return "[Error] google-genai ライブラリがインストールされていません。pip install google-genai を実行してください。"

        api_key = self.gemini_api_key
        if not api_key:
            return None

        if rule_based is None:
            rule_based = self.generate_rule_based_advice()

        context = self._build_comprehensive_context()

        prompt = f"""{self.SYSTEM_PROMPT}

財務データを分析して、包括的なアドバイスをお願いします。

{context}

【ルールベース分析結果】
{rule_based.summary}

【気になるポイント】
{chr(10).join('- ' + w['message'] for w in rule_based.category_warnings[:10])}

以下の構成でアドバイスをお願いします：

1. **現状の総合評価**（家計・資産・税金を含めた全体像）
2. **強みと改善ポイント**（具体的な数字を使って）
3. **優先度の高いアクション**（すぐにできること3つ）
4. **中長期的な提案**（3ヶ月〜1年の視点で）

Markdown形式で、見出しや箇条書きを使って読みやすくしてください。
ユーザーに寄り添う形でアドバイスしてください。
"""

        try:
            client = genai.Client(api_key=api_key)
            models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]
            for model_name in models:
                try:
                    response = call_gemini_with_retry(client, prompt, model_name=model_name)
                    return response.text
                except Exception as e:
                    if '503' in str(e) or 'UNAVAILABLE' in str(e) or 'overloaded' in str(e).lower():
                        continue
                    raise
            return "[Gemini Error] 全モデルが一時的に利用不可です。しばらく待ってから再試行してください。"
        except Exception as e:
            logger.error(f"Gemini Error: {type(e).__name__}: {e}")
            return "[Gemini Error] APIとの通信に失敗しました。再試行してください。"

    def generate_comprehensive_advice(
        self,
        chat_history: List[Dict[str, str]] = None,
        rule_based: Optional[RuleBasedAdvice] = None,
        images: List[Dict] = None,
    ) -> Optional[str]:
        """チャット履歴を読み込み、全データを統合した総合アドバイスを生成"""
        if not GEMINI_AVAILABLE or genai is None:
            return "[Error] google-genai ライブラリがインストールされていません。"

        api_key = self.gemini_api_key
        if not api_key:
            return None

        if rule_based is None:
            rule_based = self.generate_rule_based_advice()

        context = self._build_comprehensive_context()

        # チャット履歴のサマリーを読み込み
        history_summary = self.load_history_summary()
        history_section = ""
        if history_summary.get("key_insights") or history_summary.get("action_items"):
            parts = []
            if history_summary.get("key_insights"):
                parts.append("**これまでの相談で分かったこと:**")
                for item in history_summary["key_insights"][:8]:
                    parts.append(f"- {item}")
            if history_summary.get("action_items"):
                parts.append("**検討中・取り組み中のこと:**")
                for item in history_summary["action_items"][:5]:
                    parts.append(f"- {item}")
            if history_summary.get("discussed_topics"):
                parts.append("**過去に相談したトピック:**")
                for item in history_summary["discussed_topics"][:5]:
                    parts.append(f"- {item}")
            if history_summary.get("concerns"):
                parts.append("**懸念事項:**")
                for item in history_summary["concerns"][:5]:
                    parts.append(f"- {item}")
            if history_summary.get("preferences"):
                parts.append("**傾向・好み:**")
                for item in history_summary["preferences"][:5]:
                    parts.append(f"- {item}")
            history_section = "\n".join(parts)

        # 直近のチャットから追加コンテキスト
        recent_chat = ""
        if chat_history:
            recent = chat_history[-10:]
            for msg in recent:
                role = "ユーザー" if msg["role"] == "user" else "アドバイザー"
                content = msg["content"][:200]
                recent_chat += f"{role}: {content}\n"

        prompt = f"""{self.SYSTEM_PROMPT}

全財務データとこれまでの相談履歴を踏まえた、総合ファイナンシャルアドバイスを生成してください。

{context}

【ルールベース分析結果】
{rule_based.summary}

【カテゴリ別の注意点】
{chr(10).join('- ' + w['message'] for w in rule_based.category_warnings[:10])}

{"【過去の相談履歴サマリー】" + chr(10) + history_section if history_section else ""}

{"【直近の会話】" + chr(10) + recent_chat if recent_chat else ""}

以下の構成で、ユーザー個人に最適化された総合アドバイスを作成してください：

1. **現状の総合評価スコア**（5段階で家計・資産・税金・保険をそれぞれ評価）
2. **前回からの変化・進捗**（過去の相談内容があれば、その後の状況を踏まえて）
3. **今すぐやるべきこと TOP3**（具体的な金額と手順を含めて）
4. **節税・控除の最適化提案**（医療費控除、ふるさと納税、iDeCo、保険料控除を具体的に）
5. **資産形成ロードマップ**（3ヶ月・半年・1年の目標と行動計画）
6. **リスクと注意点**（見落としがちなポイント）

過去の相談で出た懸念や検討事項があれば、必ずフォローアップしてください。
具体的な数字を使い、Markdown形式で読みやすくしてください。
"""

        # 画像がある場合はプロンプトに追記
        n_images = len(images) if images else 0
        if n_images == 1:
            prompt += "\n\n※ 画像が1枚添付されています。画像の内容も分析に含めてください。"
        elif n_images > 1:
            prompt += f"\n\n※ 画像が{n_images}枚添付されています。全ての画像の内容も分析に含めてください。"

        try:
            client = genai.Client(api_key=api_key)

            # 画像がある場合はマルチモーダルコンテンツを構築
            if images:
                from google.genai import types as genai_types
                contents = [prompt]
                for img in images:
                    contents.append(genai_types.Part(inlineData=genai_types.Blob(
                        mimeType=img["mime_type"],
                        data=img["bytes"],
                    )))
            else:
                contents = prompt

            models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]
            last_error = None
            for model_name in models:
                try:
                    response = call_gemini_with_retry(client, contents, model_name=model_name)
                    return response.text
                except Exception as e:
                    last_error = e
                    err_str = str(e)
                    if '429' in err_str or '503' in err_str or 'UNAVAILABLE' in err_str or 'RESOURCE_EXHAUSTED' in err_str or 'overloaded' in err_str.lower():
                        continue
                    raise
            logger.error(f"Gemini all models unavailable: {last_error}")
            return "[Gemini Error] 全モデルが一時的に利用不可です。しばらく待ってから再試行してください。"
        except Exception as e:
            logger.error(f"Gemini Error: {type(e).__name__}: {e}")
            return "[Gemini Error] APIとの通信に失敗しました。再試行してください。"

    def gemini_chat(
        self,
        user_message: str,
        chat_history: List[Dict[str, str]],
        images: List[Dict] = None,
    ) -> Optional[str]:
        """Gemini APIを使った対話形式のアドバイス（複数画像対応）

        Args:
            images: [{"bytes": bytes, "mime_type": str}, ...] のリスト
        """
        if not GEMINI_AVAILABLE or genai is None:
            return "[Error] google-genai ライブラリがインストールされていません。pip install google-genai を実行してください。"

        api_key = self.gemini_api_key
        if not api_key:
            return None

        context = self._build_comprehensive_context()

        history_text = ""
        for msg in chat_history[-15:]:
            role = "ユーザー" if msg["role"] == "user" else "アドバイザー"
            history_text += f"{role}: {msg['content']}\n\n"

        n_images = len(images) if images else 0
        image_instruction = ""
        if n_images == 1:
            image_instruction = "※ 画像が1枚添付されています。画像の内容を分析して回答に含めてください。レシートや明細書の場合は金額・日付・店舗名を抽出してください。"
        elif n_images > 1:
            image_instruction = f"※ 画像が{n_images}枚添付されています。全ての画像の内容を分析して回答に含めてください。レシートや明細書の場合は金額・日付・店舗名を抽出してください。"

        text_prompt = f"""{self.SYSTEM_PROMPT}

【財務状況】
{context}

【これまでの会話】
{history_text}

【質問】
{user_message}

{image_instruction}

上記の質問に対して、財務状況を踏まえた具体的なアドバイスを提供してください。
数字を使って分かりやすく説明してください。
"""

        # コンテンツ構築（テキスト + 複数画像）
        if images:
            from google.genai import types as genai_types
            contents = [text_prompt]
            for img in images:
                contents.append(genai_types.Part(inlineData=genai_types.Blob(
                    mimeType=img["mime_type"],
                    data=img["bytes"],
                )))
        else:
            contents = text_prompt

        try:
            client = genai.Client(api_key=api_key)
            models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]
            last_err = None
            for model_name in models:
                try:
                    response = call_gemini_with_retry(client, contents, model_name=model_name, max_retries=1)
                    return response.text
                except Exception as e:
                    last_err = e
                    err_str = str(e)
                    if '429' in err_str or '503' in err_str or 'UNAVAILABLE' in err_str or 'RESOURCE_EXHAUSTED' in err_str or 'overloaded' in err_str.lower():
                        continue
                    raise
            logger.error(f"Gemini rate limited: {last_err}")
            return "[Gemini Error] 全モデルが利用制限に達しています。しばらく待ってから再試行してください。"
        except Exception as e:
            logger.error(f"Gemini Error: {type(e).__name__}: {e}")
            return "[Gemini Error] APIとの通信に失敗しました。再試行してください。"

    def chat(
        self,
        user_message: str,
        chat_history: List[Dict[str, str]],
        max_tokens: int = 1500,
    ) -> Optional[str]:
        """Claude APIを使った対話形式のアドバイス"""
        client = self._get_anthropic_client()
        if client is None:
            return None

        context = self._build_comprehensive_context()

        system_prompt = f"""{self.SYSTEM_PROMPT}

【財務状況】
{context}
"""

        messages = list(chat_history) + [{"role": "user", "content": user_message}]

        try:
            response = client.messages.create(
                model=self.claude_model,
                max_tokens=max_tokens,
                temperature=0.7,
                system=system_prompt,
                messages=messages,
            )
        except Exception:
            return None

        try:
            if response.content and len(response.content) > 0:
                return response.content[0].text
        except Exception:
            pass

        return None
