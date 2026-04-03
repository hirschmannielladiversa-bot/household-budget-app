"""月別支出インポートモジュール"""
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import re


class MonthlyImporter:
    """月別支出データのインポートと変換を行うクラス"""

    # デフォルトのカテゴリマッピング
    DEFAULT_CATEGORY_MAPPING = {
        "住居費": "住居費",
        "通信費": "通信費",
        "食費": "食費",
        "食費（Nash、スーパー）": "食費",
        "保険料": "保険料",
        "コンビニ": "食費",
        "AI費": "通信費",
        "サブスク": "娯楽費",
        "アマゾン": "日用品",
        "スターバックス": "食費",
        "楽天PEY": "その他",
        "楽天PAY": "その他",
        "交通費": "交通費",
        "その他": "その他",
        "医療費": "医療費",
        "光熱費": "光熱費",
        "娯楽費": "娯楽費",
        "教育費": "教育費",
        "日用品": "日用品",
        "衣服": "衣服",
    }

    STANDARD_CATEGORIES = [
        "食費", "交通費", "医療費", "通信費", "光熱費",
        "住居費", "保険料", "娯楽費", "教育費", "日用品",
        "衣服", "その他"
    ]

    def __init__(self, category_mapping: Optional[Dict[str, str]] = None):
        """初期化

        Args:
            category_mapping: カスタムカテゴリマッピング（Noneの場合はデフォルト使用）
        """
        self.category_mapping = category_mapping or self.DEFAULT_CATEGORY_MAPPING.copy()

    def load_excel(self, file_path: str, sheet_name: str = "Table 1") -> pd.DataFrame:
        """Excelファイルを読み込み

        Args:
            file_path: Excelファイルパス
            sheet_name: シート名

        Returns:
            読み込んだDataFrame
        """
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=0)
        return df

    def load_from_bytes(self, file_bytes: bytes, sheet_name: str = None) -> pd.DataFrame:
        """バイトデータから読み込み

        Args:
            file_bytes: Excelのバイトデータ
            sheet_name: シート名（Noneの場合は最初のシート）

        Returns:
            読み込んだDataFrame
        """
        import io
        xlsx = pd.ExcelFile(io.BytesIO(file_bytes))

        if sheet_name is None:
            # 最初のシートを使用（ソース参照シートは除外）
            for name in xlsx.sheet_names:
                if "ソース" not in name and "参照" not in name:
                    sheet_name = name
                    break
            else:
                sheet_name = xlsx.sheet_names[0]

        return pd.read_excel(xlsx, sheet_name=sheet_name, header=0)

    def parse_month(self, month_str: str) -> Optional[str]:
        """月の文字列をYYYY-MM形式に変換

        Args:
            month_str: "2025年08月" 形式の文字列

        Returns:
            "2025-08" 形式の文字列
        """
        if pd.isna(month_str):
            return None

        # "2025年08月" -> "2025-08"
        match = re.search(r'(\d{4})年(\d{1,2})月', str(month_str))
        if match:
            year, month = match.groups()
            return f"{year}-{int(month):02d}"

        # "2025-08" 形式
        match = re.search(r'(\d{4})-(\d{1,2})', str(month_str))
        if match:
            year, month = match.groups()
            return f"{year}-{int(month):02d}"

        return None

    def convert_to_standard_format(self, df: pd.DataFrame) -> pd.DataFrame:
        """横持ちデータを縦持ちの標準フォーマットに変換

        Args:
            df: 横持ちの月別データ

        Returns:
            縦持ちの標準フォーマット（日付, カテゴリ, 金額, メモ）
        """
        records = []

        # 最初の列を月として扱う
        month_col = df.columns[0]

        for _, row in df.iterrows():
            month_str = self.parse_month(row[month_col])
            if not month_str:
                continue

            # 月の初日を日付として使用
            date_str = f"{month_str}-01"

            # 各カテゴリの金額を取得
            for col in df.columns[1:]:
                if col == "ソース" or pd.isna(col):
                    continue

                amount = row[col]
                if pd.isna(amount) or amount == 0:
                    continue

                # 金額を数値に変換
                if isinstance(amount, str):
                    amount = float(amount.replace(",", "").replace("円", ""))

                # カテゴリをマッピング
                mapped_category = self.map_category(str(col))

                records.append({
                    "日付": date_str,
                    "カテゴリ": mapped_category,
                    "金額": float(amount),
                    "メモ": f"{col}（{month_str}）"
                })

        result_df = pd.DataFrame(records)

        # 日付を datetime に変換し、年月カラムを追加
        if len(result_df) > 0:
            result_df["日付"] = pd.to_datetime(result_df["日付"])
            result_df["年月"] = result_df["日付"].dt.to_period("M").astype(str)

        return result_df

    def map_category(self, original: str) -> str:
        """カテゴリをマッピング

        Args:
            original: 元のカテゴリ名

        Returns:
            マッピング後のカテゴリ名
        """
        # 完全一致
        if original in self.category_mapping:
            return self.category_mapping[original]

        # 部分一致
        for key, value in self.category_mapping.items():
            if key in original or original in key:
                return value

        # マッチしない場合は「その他」
        return "その他"

    def get_monthly_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """月別サマリーを取得

        Args:
            df: 標準フォーマットのDataFrame

        Returns:
            月別・カテゴリ別の集計DataFrame
        """
        if df is None or len(df) == 0:
            return pd.DataFrame()

        # 年月列を追加
        df = df.copy()
        df["年月"] = df["日付"].dt.to_period("M").astype(str)

        # 月別・カテゴリ別に集計
        summary = df.groupby(["年月", "カテゴリ"])["金額"].sum().unstack(fill_value=0)

        # 合計列を追加
        summary["合計"] = summary.sum(axis=1)

        return summary

    def get_category_mapping_preview(self, df: pd.DataFrame) -> List[Dict]:
        """カテゴリマッピングのプレビューを取得

        Args:
            df: 横持ちの元データ

        Returns:
            マッピング情報のリスト
        """
        previews = []
        month_col = df.columns[0]

        for col in df.columns[1:]:
            if col == "ソース" or pd.isna(col):
                continue

            mapped = self.map_category(str(col))
            previews.append({
                "元カテゴリ": str(col),
                "マッピング先": mapped,
                "サンプル金額": df[col].iloc[0] if len(df) > 0 else 0
            })

        return previews

    def update_category_mapping(self, original: str, mapped: str) -> None:
        """カテゴリマッピングを更新

        Args:
            original: 元のカテゴリ名
            mapped: マッピング先のカテゴリ名
        """
        self.category_mapping[original] = mapped


def is_monthly_format(df: pd.DataFrame) -> bool:
    """DataFrameが月別フォーマットかどうかを判定

    Args:
        df: 判定するDataFrame

    Returns:
        月別フォーマットの場合True
    """
    if df is None or len(df) == 0:
        return False

    first_col = df.columns[0]
    if pd.isna(first_col):
        return False

    # 最初の列に「年」「月」が含まれるか、YYYY-MM形式か
    first_value = str(df.iloc[0, 0]) if len(df) > 0 else ""

    return ("月" in str(first_col) or
            "年" in first_value or
            re.search(r'\d{4}[-/]\d{1,2}', first_value) is not None)
