"""データ読み込みモジュール"""

import pandas as pd
import yaml
from pathlib import Path
from typing import Optional, List, Dict, Any
from io import BytesIO


class DataLoader:
    """CSV/Excelファイルからの家計データ読み込み"""

    REQUIRED_COLUMNS = ['日付', 'カテゴリ', '金額']
    OPTIONAL_COLUMNS = ['メモ']

    def __init__(self, config_path: Optional[str] = None, data_dir: Optional[str] = None):
        self.config_path = config_path or self._default_config_path()
        self._data_dir = data_dir
        self.categories = self._load_categories()

    def _default_config_path(self) -> str:
        return str(Path(__file__).parent.parent / 'config' / 'categories.yaml')

    def _load_categories(self) -> Dict[str, Any]:
        """カテゴリ設定を読み込む"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return config.get('categories', {})
        except FileNotFoundError:
            return self._default_categories()

    def _default_categories(self) -> Dict[str, Any]:
        """デフォルトカテゴリ"""
        return {
            '食費': {'icon': '🍽️', 'ideal_ratio': 0.25},
            '交通費': {'icon': '🚃', 'ideal_ratio': 0.05},
            '医療費': {'icon': '🏥', 'ideal_ratio': 0.05},
            '通信費': {'icon': '📱', 'ideal_ratio': 0.05},
            '光熱費': {'icon': '💡', 'ideal_ratio': 0.07},
            '住居費': {'icon': '🏠', 'ideal_ratio': 0.25},
            '保険料': {'icon': '🛡️', 'ideal_ratio': 0.05},
            '娯楽費': {'icon': '🎮', 'ideal_ratio': 0.05},
            '教育費': {'icon': '📚', 'ideal_ratio': 0.05},
            '日用品': {'icon': '🧴', 'ideal_ratio': 0.03},
            '衣服': {'icon': '👕', 'ideal_ratio': 0.05},
            'その他': {'icon': '📦', 'ideal_ratio': 0.05},
        }

    def load_csv(self, file_or_path) -> pd.DataFrame:
        """CSVファイルを読み込む"""
        df = pd.read_csv(file_or_path, encoding='utf-8')
        return self._validate_and_process(df)

    def load_excel(self, file_or_path, sheet_name: str = 0) -> pd.DataFrame:
        """Excelファイルを読み込む"""
        df = pd.read_excel(file_or_path, sheet_name=sheet_name)
        return self._validate_and_process(df)

    def load_from_bytes(self, data: bytes, file_type: str) -> pd.DataFrame:
        """バイトデータから読み込む（Streamlitアップロード用）"""
        buffer = BytesIO(data)
        if file_type == 'csv':
            return self.load_csv(buffer)
        elif file_type in ['xlsx', 'xls']:
            return self.load_excel(buffer)
        else:
            raise ValueError(f"サポートされていないファイル形式: {file_type}")

    def _sanitize_cell(self, value):
        """CSVインジェクション対策"""
        if isinstance(value, str) and len(value) > 0 and value[0] in ('=', '+', '@'):
            return "'" + value
        return value

    def _validate_and_process(self, df: pd.DataFrame) -> pd.DataFrame:
        """データの検証と前処理"""
        # 列名の正規化（空白除去）
        df.columns = df.columns.str.strip()

        # 必須列の確認
        missing_cols = [col for col in self.REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols:
            raise ValueError(f"必須列が見つかりません: {missing_cols}")

        # 日付の変換
        df['日付'] = pd.to_datetime(df['日付'])

        # 日付範囲の検証
        min_date = pd.Timestamp('2000-01-01')
        max_date = pd.Timestamp('2100-12-31')
        out_of_range = (df['日付'] < min_date) | (df['日付'] > max_date)
        if out_of_range.any():
            raise ValueError("日付は2000-01-01から2100-12-31の範囲内である必要があります")

        # 金額を数値に変換
        df['金額'] = pd.to_numeric(df['金額'], errors='coerce')

        # 欠損値の処理
        df = df.dropna(subset=['日付', 'カテゴリ', '金額'])

        # 金額範囲の検証
        if (df['金額'] < 0).any() or (df['金額'] > 999_999_999).any():
            raise ValueError("金額は0以上999,999,999以下である必要があります")

        # メモ列がない場合は追加
        if 'メモ' not in df.columns:
            df['メモ'] = ''

        # メモ列のCSVインジェクション対策
        df['メモ'] = df['メモ'].apply(self._sanitize_cell)

        # 年月列を追加
        df['年月'] = df['日付'].dt.to_period('M')
        df['曜日'] = df['日付'].dt.day_name()

        return df.sort_values('日付').reset_index(drop=True)

    def get_category_list(self) -> List[str]:
        """利用可能なカテゴリ一覧を取得"""
        return list(self.categories.keys())

    def get_category_icon(self, category: str) -> str:
        """カテゴリのアイコンを取得"""
        return self.categories.get(category, {}).get('icon', '📦')

    def get_ideal_ratios(self) -> Dict[str, float]:
        """理想的な支出比率を取得"""
        return {cat: info.get('ideal_ratio', 0.05)
                for cat, info in self.categories.items()}

    def create_empty_dataframe(self) -> pd.DataFrame:
        """空のデータフレームを作成"""
        df = pd.DataFrame(columns=self.REQUIRED_COLUMNS + self.OPTIONAL_COLUMNS)
        df['日付'] = pd.to_datetime(df['日付'])
        df['金額'] = pd.to_numeric(df['金額'])
        return df

    def add_entry(self, df: pd.DataFrame, date, category: str,
                  amount: float, memo: str = '') -> pd.DataFrame:
        """エントリを追加"""
        new_entry = pd.DataFrame([{
            '日付': pd.to_datetime(date),
            'カテゴリ': category,
            '金額': amount,
            'メモ': memo
        }])
        new_entry['年月'] = new_entry['日付'].dt.to_period('M')
        new_entry['曜日'] = new_entry['日付'].dt.day_name()

        return pd.concat([df, new_entry], ignore_index=True).sort_values('日付').reset_index(drop=True)

    def export_csv(self, df: pd.DataFrame, path: str) -> None:
        """CSVにエクスポート"""
        export_df = df[['日付', 'カテゴリ', '金額', 'メモ']].copy()
        export_df['日付'] = export_df['日付'].dt.strftime('%Y-%m-%d')
        export_df.to_csv(path, index=False, encoding='utf-8')

    def get_save_path(self) -> Path:
        """保存ファイルのデフォルトパスを取得"""
        if self._data_dir:
            return Path(self._data_dir) / 'saved_expenses.csv'
        return Path(__file__).parent.parent / 'data' / 'saved_expenses.csv'

    def save_data(self, df: pd.DataFrame) -> bool:
        """支出データをファイルに保存

        Args:
            df: 保存するDataFrame

        Returns:
            保存成功の場合True
        """
        if df is None or len(df) == 0:
            return False

        save_path = self.get_save_path()
        save_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            self.export_csv(df, str(save_path))
            return True
        except Exception:
            return False

    def load_saved_data(self) -> Optional[pd.DataFrame]:
        """保存された支出データを読み込み

        Returns:
            読み込んだDataFrame、存在しない場合はNone
        """
        save_path = self.get_save_path()
        if not save_path.exists():
            return None

        try:
            return self.load_csv(str(save_path))
        except Exception:
            return None

    def has_saved_data(self) -> bool:
        """保存データが存在するか確認"""
        return self.get_save_path().exists()

    def to_csv_bytes(self, df: pd.DataFrame) -> bytes:
        """DataFrameをCSVバイトデータに変換（ダウンロード用）

        Args:
            df: 変換するDataFrame

        Returns:
            CSVのバイトデータ
        """
        if df is None or len(df) == 0:
            return b''

        export_df = df[['日付', 'カテゴリ', '金額', 'メモ']].copy()
        export_df['日付'] = export_df['日付'].dt.strftime('%Y-%m-%d')
        return export_df.to_csv(index=False, encoding='utf-8').encode('utf-8')
