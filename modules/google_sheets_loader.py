"""Google Sheets連携モジュール

Google Sheets APIを使用して家計データを直接読み込む。
NotebookLMとの連携を想定し、収入・支出データの取得と
YAML形式でのエクスポート機能を提供する。
"""

import os
import json
import pandas as pd
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime
import re


def is_google_sheets_available() -> bool:
    """Google Sheets APIが利用可能かどうかを確認"""
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        return True
    except ImportError:
        return False


class GoogleSheetsLoader:
    """Google Sheetsから家計データを読み込むクラス"""

    SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

    # デフォルトの列マッピング
    DEFAULT_EXPENSE_COLUMNS = {
        '日付': ['日付', 'date', 'Date', '日時'],
        'カテゴリ': ['カテゴリ', 'category', 'Category', '項目', '分類'],
        '金額': ['金額', 'amount', 'Amount', '支出額', '出金'],
        'メモ': ['メモ', 'memo', 'Memo', '備考', 'note', 'Note']
    }

    DEFAULT_INCOME_COLUMNS = {
        '日付': ['日付', 'date', 'Date', '日時', '入金日'],
        '項目': ['項目', '収入源', 'source', 'Source', 'カテゴリ', '種類'],
        '金額': ['金額', 'amount', 'Amount', '収入額', '入金額'],
        'メモ': ['メモ', 'memo', 'Memo', '備考', 'note', 'Note']
    }

    def __init__(self, credentials_path: Optional[str] = None):
        """初期化

        Args:
            credentials_path: サービスアカウントのJSONキーファイルパス
                             Noneの場合は環境変数 GOOGLE_CREDENTIALS_PATH を使用
        """
        self.credentials_path = credentials_path or os.environ.get(
            'GOOGLE_CREDENTIALS_PATH',
            str(Path(__file__).parent.parent / 'config' / 'google_credentials.json')
        )
        self._service = None
        self._credentials = None

    def _get_service(self):
        """Google Sheets APIサービスを取得"""
        if self._service is not None:
            return self._service

        if not is_google_sheets_available():
            raise ImportError(
                "Google APIライブラリがインストールされていません。\n"
                "pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
            )

        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        if not Path(self.credentials_path).exists():
            raise FileNotFoundError(
                f"認証ファイルが見つかりません: {self.credentials_path}\n"
                "Google Cloud Consoleでサービスアカウントを作成し、"
                "JSONキーファイルをダウンロードしてください。"
            )

        self._credentials = Credentials.from_service_account_file(
            self.credentials_path, scopes=self.SCOPES
        )
        self._service = build('sheets', 'v4', credentials=self._credentials)
        return self._service

    def _validate_sheet_id(self, sheet_id: str) -> bool:
        """シートIDの検証"""
        if not re.match(r'^[a-zA-Z0-9_-]{10,100}$', sheet_id):
            return False
        return True

    def extract_sheet_id(self, url_or_id: str) -> str:
        """URLまたはシートIDからシートIDを抽出

        Args:
            url_or_id: Google SheetsのURLまたはシートID

        Returns:
            シートID
        """
        # URLの場合、Googleドメインか検証
        if url_or_id.startswith('http://') or url_or_id.startswith('https://'):
            if not re.match(r'https?://docs\.google\.com/', url_or_id):
                raise ValueError("Google Sheets以外のURLは許可されていません")

        # URLからIDを抽出
        patterns = [
            r'/spreadsheets/d/([a-zA-Z0-9-_]+)',  # 標準URL
            r'spreadsheets/d/([a-zA-Z0-9-_]+)',
            r'^([a-zA-Z0-9-_]{20,})$'  # IDのみ
        ]

        for pattern in patterns:
            match = re.search(pattern, url_or_id)
            if match:
                sheet_id = match.group(1)
                if not self._validate_sheet_id(sheet_id):
                    raise ValueError(f"無効なシートID形式: {sheet_id}")
                return sheet_id

        raise ValueError(f"無効なGoogle Sheets URLまたはID: {url_or_id}")

    def get_sheet_names(self, spreadsheet_id: str) -> List[str]:
        """スプレッドシート内のシート名一覧を取得

        Args:
            spreadsheet_id: スプレッドシートID

        Returns:
            シート名のリスト
        """
        service = self._get_service()
        spreadsheet_id = self.extract_sheet_id(spreadsheet_id)

        result = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = result.get('sheets', [])

        return [sheet['properties']['title'] for sheet in sheets]

    def read_sheet(self, spreadsheet_id: str, sheet_name: str = None,
                   range_notation: str = None) -> pd.DataFrame:
        """シートのデータを読み込み

        Args:
            spreadsheet_id: スプレッドシートID（URLも可）
            sheet_name: シート名（Noneの場合は最初のシート）
            range_notation: 読み込む範囲（例: 'A1:D100'）

        Returns:
            読み込んだDataFrame
        """
        service = self._get_service()
        spreadsheet_id = self.extract_sheet_id(spreadsheet_id)

        # シート名を取得
        if sheet_name is None:
            sheet_names = self.get_sheet_names(spreadsheet_id)
            sheet_name = sheet_names[0] if sheet_names else 'Sheet1'

        # 範囲を構築
        if range_notation:
            range_str = f"'{sheet_name}'!{range_notation}"
        else:
            range_str = sheet_name

        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_str
        ).execute()

        values = result.get('values', [])

        if not values:
            return pd.DataFrame()

        # 最初の行をヘッダーとして使用
        headers = values[0]
        data = values[1:]

        # データの列数をヘッダーに合わせる
        normalized_data = []
        for row in data:
            if len(row) < len(headers):
                row = row + [''] * (len(headers) - len(row))
            elif len(row) > len(headers):
                row = row[:len(headers)]
            normalized_data.append(row)

        return pd.DataFrame(normalized_data, columns=headers)

    def _map_columns(self, df: pd.DataFrame,
                     column_mapping: Dict[str, List[str]]) -> pd.DataFrame:
        """列名をマッピング

        Args:
            df: 元のDataFrame
            column_mapping: 列名のマッピング辞書

        Returns:
            列名をマッピングしたDataFrame
        """
        result_df = df.copy()
        rename_map = {}

        for target_name, possible_names in column_mapping.items():
            for col in df.columns:
                col_clean = str(col).strip()
                if col_clean in possible_names or col_clean.lower() in [n.lower() for n in possible_names]:
                    rename_map[col] = target_name
                    break

        return result_df.rename(columns=rename_map)

    def load_expenses(self, spreadsheet_id: str, sheet_name: str = None,
                      column_mapping: Dict[str, List[str]] = None) -> pd.DataFrame:
        """支出データを読み込み

        Args:
            spreadsheet_id: スプレッドシートID
            sheet_name: シート名（デフォルトは「支出」または最初のシート）
            column_mapping: カスタム列マッピング

        Returns:
            標準フォーマットのDataFrame
        """
        # シート名の自動検出
        if sheet_name is None:
            try:
                sheet_names = self.get_sheet_names(spreadsheet_id)
                for name in ['支出', '出費', 'expenses', 'Expenses', '家計簿']:
                    if name in sheet_names:
                        sheet_name = name
                        break
            except Exception:
                pass

        df = self.read_sheet(spreadsheet_id, sheet_name)

        if df.empty:
            return pd.DataFrame(columns=['日付', 'カテゴリ', '金額', 'メモ'])

        # 列マッピング
        mapping = column_mapping or self.DEFAULT_EXPENSE_COLUMNS
        df = self._map_columns(df, mapping)

        # 必須列の確認
        required = ['日付', 'カテゴリ', '金額']
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"必須列が見つかりません: {missing}")

        # データ型変換
        df['日付'] = pd.to_datetime(df['日付'], errors='coerce')
        df['金額'] = pd.to_numeric(
            df['金額'].astype(str).str.replace(',', '').str.replace('円', '').str.replace('¥', ''),
            errors='coerce'
        )

        # 欠損値を除去
        df = df.dropna(subset=['日付', '金額'])

        # メモ列がない場合は追加
        if 'メモ' not in df.columns:
            df['メモ'] = ''

        # 年月・曜日を追加
        df['年月'] = df['日付'].dt.to_period('M')
        df['曜日'] = df['日付'].dt.day_name()

        return df[['日付', 'カテゴリ', '金額', 'メモ', '年月', '曜日']].reset_index(drop=True)

    def load_income(self, spreadsheet_id: str, sheet_name: str = None,
                    column_mapping: Dict[str, List[str]] = None) -> pd.DataFrame:
        """収入データを読み込み

        Args:
            spreadsheet_id: スプレッドシートID
            sheet_name: シート名（デフォルトは「収入」または自動検出）
            column_mapping: カスタム列マッピング

        Returns:
            収入データのDataFrame
        """
        # シート名の自動検出
        if sheet_name is None:
            try:
                sheet_names = self.get_sheet_names(spreadsheet_id)
                for name in ['収入', 'income', 'Income', '入金']:
                    if name in sheet_names:
                        sheet_name = name
                        break
            except Exception:
                pass

        df = self.read_sheet(spreadsheet_id, sheet_name)

        if df.empty:
            return pd.DataFrame(columns=['日付', '項目', '金額', 'メモ'])

        # 列マッピング
        mapping = column_mapping or self.DEFAULT_INCOME_COLUMNS
        df = self._map_columns(df, mapping)

        # 必須列の確認
        required = ['日付', '金額']
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"必須列が見つかりません: {missing}")

        # データ型変換
        df['日付'] = pd.to_datetime(df['日付'], errors='coerce')
        df['金額'] = pd.to_numeric(
            df['金額'].astype(str).str.replace(',', '').str.replace('円', '').str.replace('¥', ''),
            errors='coerce'
        )

        # 欠損値を除去
        df = df.dropna(subset=['日付', '金額'])

        # オプション列がない場合は追加
        if '項目' not in df.columns:
            df['項目'] = '給与'
        if 'メモ' not in df.columns:
            df['メモ'] = ''

        # 年月を追加
        df['年月'] = df['日付'].dt.to_period('M').astype(str)

        return df[['日付', '項目', '金額', 'メモ', '年月']].reset_index(drop=True)

    def load_both(self, spreadsheet_id: str,
                  expense_sheet: str = None,
                  income_sheet: str = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """支出と収入の両方を読み込み

        Args:
            spreadsheet_id: スプレッドシートID
            expense_sheet: 支出シート名
            income_sheet: 収入シート名

        Returns:
            (支出DataFrame, 収入DataFrame)のタプル
        """
        expenses = self.load_expenses(spreadsheet_id, expense_sheet)
        income = self.load_income(spreadsheet_id, income_sheet)
        return expenses, income

    def get_monthly_summary(self, expenses_df: pd.DataFrame,
                            income_df: pd.DataFrame = None) -> Dict[str, Any]:
        """月別サマリーを生成

        Args:
            expenses_df: 支出データ
            income_df: 収入データ（オプション）

        Returns:
            月別サマリー辞書
        """
        summary = {}

        if expenses_df is not None and len(expenses_df) > 0:
            # 支出の月別集計
            expenses_df = expenses_df.copy()
            expenses_df['年月'] = expenses_df['日付'].dt.to_period('M').astype(str)
            monthly_expenses = expenses_df.groupby('年月')['金額'].sum()
            category_monthly = expenses_df.groupby(['年月', 'カテゴリ'])['金額'].sum().unstack(fill_value=0)

            summary['支出'] = {
                '月別合計': monthly_expenses.to_dict(),
                'カテゴリ別': category_monthly.to_dict()
            }

        if income_df is not None and len(income_df) > 0:
            # 収入の月別集計
            income_df = income_df.copy()
            if '年月' not in income_df.columns:
                income_df['年月'] = income_df['日付'].dt.to_period('M').astype(str)
            monthly_income = income_df.groupby('年月')['金額'].sum()

            summary['収入'] = {
                '月別合計': monthly_income.to_dict()
            }

            # 収支バランス計算
            if '支出' in summary:
                balance = {}
                all_months = set(summary['支出']['月別合計'].keys()) | set(summary['収入']['月別合計'].keys())
                for month in sorted(all_months):
                    income_val = summary['収入']['月別合計'].get(month, 0)
                    expense_val = summary['支出']['月別合計'].get(month, 0)
                    balance[month] = income_val - expense_val
                summary['収支バランス'] = balance

        return summary


class NotebookLMExporter:
    """NotebookLM連携用のYAMLエクスポーター"""

    def __init__(self):
        pass

    def export_to_yaml(self, expenses_df: pd.DataFrame,
                       income_df: pd.DataFrame = None,
                       output_path: str = None) -> str:
        """NotebookLM用のYAMLを生成

        Args:
            expenses_df: 支出データ
            income_df: 収入データ（オプション）
            output_path: 出力ファイルパス（Noneの場合は文字列を返す）

        Returns:
            YAML形式の文字列
        """
        import yaml

        data = {
            '家計データサマリー': {
                '生成日時': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'データ期間': {}
            }
        }

        # 支出データの処理
        if expenses_df is not None and len(expenses_df) > 0:
            expenses_df = expenses_df.copy()
            expenses_df['年月'] = expenses_df['日付'].dt.to_period('M').astype(str)

            data['家計データサマリー']['データ期間']['支出'] = {
                '開始': str(expenses_df['日付'].min().date()),
                '終了': str(expenses_df['日付'].max().date()),
                '件数': len(expenses_df)
            }

            # カテゴリ別集計
            category_total = expenses_df.groupby('カテゴリ')['金額'].sum().sort_values(ascending=False)
            data['支出カテゴリ別合計'] = {
                cat: int(amount) for cat, amount in category_total.items()
            }

            # 月別集計
            monthly_expenses = expenses_df.groupby('年月')['金額'].sum()
            data['月別支出'] = {
                month: int(amount) for month, amount in monthly_expenses.items()
            }

            # 月別カテゴリ詳細
            monthly_category = expenses_df.groupby(['年月', 'カテゴリ'])['金額'].sum()
            data['月別カテゴリ詳細'] = {}
            for (month, cat), amount in monthly_category.items():
                if month not in data['月別カテゴリ詳細']:
                    data['月別カテゴリ詳細'][month] = {}
                data['月別カテゴリ詳細'][month][cat] = int(amount)

        # 収入データの処理
        if income_df is not None and len(income_df) > 0:
            income_df = income_df.copy()
            if '年月' not in income_df.columns:
                income_df['年月'] = income_df['日付'].dt.to_period('M').astype(str)

            data['家計データサマリー']['データ期間']['収入'] = {
                '開始': str(income_df['日付'].min().date()),
                '終了': str(income_df['日付'].max().date()),
                '件数': len(income_df)
            }

            # 月別収入
            monthly_income = income_df.groupby('年月')['金額'].sum()
            data['月別収入'] = {
                month: int(amount) for month, amount in monthly_income.items()
            }

            # 収入項目別
            if '項目' in income_df.columns:
                item_total = income_df.groupby('項目')['金額'].sum().sort_values(ascending=False)
                data['収入項目別合計'] = {
                    item: int(amount) for item, amount in item_total.items()
                }

            # 収支バランス
            if '月別支出' in data:
                data['月別収支バランス'] = {}
                all_months = set(data.get('月別支出', {}).keys()) | set(data.get('月別収入', {}).keys())
                for month in sorted(all_months):
                    income_val = data.get('月別収入', {}).get(month, 0)
                    expense_val = data.get('月別支出', {}).get(month, 0)
                    data['月別収支バランス'][month] = income_val - expense_val

        # YAML出力
        yaml_str = yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(yaml_str)

        return yaml_str

    def export_monthly_report(self, expenses_df: pd.DataFrame,
                              income_df: pd.DataFrame = None,
                              target_month: str = None) -> str:
        """特定月のレポートをMarkdown形式で生成

        Args:
            expenses_df: 支出データ
            income_df: 収入データ
            target_month: 対象月（YYYY-MM形式、Noneの場合は最新月）

        Returns:
            Markdown形式のレポート
        """
        if expenses_df is None or len(expenses_df) == 0:
            return "データがありません。"

        expenses_df = expenses_df.copy()
        expenses_df['年月'] = expenses_df['日付'].dt.to_period('M').astype(str)

        # 対象月の決定
        if target_month is None:
            target_month = expenses_df['年月'].max()

        # 対象月のデータを抽出
        month_expenses = expenses_df[expenses_df['年月'] == target_month]

        if len(month_expenses) == 0:
            return f"{target_month} のデータがありません。"

        # レポート生成
        lines = [
            f"# {target_month} 家計レポート",
            "",
            "## 支出サマリー",
            "",
            f"- **総支出**: ¥{month_expenses['金額'].sum():,.0f}",
            f"- **取引件数**: {len(month_expenses)}件",
            f"- **平均支出**: ¥{month_expenses['金額'].mean():,.0f}/件",
            "",
            "## カテゴリ別支出",
            "",
            "| カテゴリ | 金額 | 割合 |",
            "|---------|-----:|-----:|"
        ]

        category_total = month_expenses.groupby('カテゴリ')['金額'].sum().sort_values(ascending=False)
        total = category_total.sum()

        for cat, amount in category_total.items():
            ratio = (amount / total * 100) if total > 0 else 0
            lines.append(f"| {cat} | ¥{amount:,.0f} | {ratio:.1f}% |")

        # 収入がある場合
        if income_df is not None and len(income_df) > 0:
            income_df = income_df.copy()
            if '年月' not in income_df.columns:
                income_df['年月'] = income_df['日付'].dt.to_period('M').astype(str)

            month_income = income_df[income_df['年月'] == target_month]

            if len(month_income) > 0:
                total_income = month_income['金額'].sum()
                balance = total_income - total

                lines.extend([
                    "",
                    "## 収支バランス",
                    "",
                    f"- **総収入**: ¥{total_income:,.0f}",
                    f"- **総支出**: ¥{total:,.0f}",
                    f"- **収支**: ¥{balance:+,.0f}",
                    "",
                    f"**貯蓄率**: {(balance / total_income * 100):.1f}%" if total_income > 0 else ""
                ])

        return "\n".join(lines)
