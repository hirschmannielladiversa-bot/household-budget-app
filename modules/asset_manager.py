"""資産管理モジュール"""
import yaml
import pandas as pd
import json
from pathlib import Path
from typing import Optional, Union
from datetime import datetime, date
from io import BytesIO


class AssetManager:
    """資産データの管理と減価償却計算を行うクラス"""

    REQUIRED_COLUMNS = ['asset_id', 'asset_type', 'name', 'purchase_date',
                        'purchase_price', 'current_value', 'details']

    def __init__(self, config_path: str = "config/assets.yaml"):
        self.config = self._load_config(config_path)
        self.df: Optional[pd.DataFrame] = None

    def _load_config(self, config_path: str) -> dict:
        """設定ファイル読み込み"""
        path = Path(config_path)
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        return self._get_default_config()

    def _get_default_config(self) -> dict:
        """デフォルト設定"""
        return {
            'asset_types': {
                'vehicle': {'name': '車両・バイク', 'icon': '🚗', 'depreciation_years': 6},
                'financial': {'name': '金融資産', 'icon': '💰', 'subtypes': ['預金', '株式', '投資信託']},
                'real_estate': {'name': '不動産', 'icon': '🏠', 'depreciation_years': {'木造': 22, 'RC': 47}}
            }
        }

    # データ読み込み
    def load_assets(self, file_path: Union[str, BytesIO]) -> pd.DataFrame:
        """資産データ読み込み"""
        if isinstance(file_path, BytesIO):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_csv(file_path)

        df = self._validate_and_process(df)
        self.df = df
        return df

    def load_from_bytes(self, file_bytes: bytes, file_type: str = 'csv') -> pd.DataFrame:
        """バイトデータから読み込み"""
        buffer = BytesIO(file_bytes)
        if file_type == 'csv':
            df = pd.read_csv(buffer)
        else:
            df = pd.read_excel(buffer)

        df = self._validate_and_process(df)
        self.df = df
        return df

    def _validate_and_process(self, df: pd.DataFrame) -> pd.DataFrame:
        """データ検証と前処理"""
        # 必須カラム確認
        for col in self.REQUIRED_COLUMNS:
            if col not in df.columns:
                df[col] = None

        # 日付変換
        df['purchase_date'] = pd.to_datetime(df['purchase_date'], errors='coerce')

        # 数値変換
        df['purchase_price'] = pd.to_numeric(df['purchase_price'], errors='coerce').fillna(0)
        df['current_value'] = pd.to_numeric(df['current_value'], errors='coerce').fillna(0)

        # details列のJSON解析
        df['details_parsed'] = df['details'].apply(self._parse_details)

        return df

    def _parse_details(self, details: str) -> dict:
        """details列をJSONとして解析"""
        if pd.isna(details) or details == '':
            return {}
        try:
            return json.loads(details)
        except (json.JSONDecodeError, TypeError):
            return {}

    def create_empty_dataframe(self) -> pd.DataFrame:
        """空のデータフレーム作成"""
        df = pd.DataFrame(columns=self.REQUIRED_COLUMNS + ['details_parsed'])
        df = df.astype({
            'asset_id': 'object',
            'asset_type': 'object',
            'name': 'object',
            'purchase_date': 'datetime64[ns]',
            'purchase_price': 'float64',
            'current_value': 'float64',
            'details': 'object',
            'details_parsed': 'object'
        })
        self.df = df
        return df

    # CRUD操作
    def add_asset(self, asset_data: dict) -> None:
        """資産追加"""
        if self.df is None:
            self.create_empty_dataframe()

        # 新しいIDを生成
        if len(self.df) == 0:
            new_id = 'A001'
        else:
            existing_ids = self.df['asset_id'].dropna()
            if len(existing_ids) == 0:
                new_id = 'A001'
            else:
                extracted = existing_ids.str.extract(r'A(\d+)')[0].dropna().astype(int)
                max_id = extracted.max() if len(extracted) > 0 else 0
                new_id = f'A{max_id + 1:03d}'

        asset_data['asset_id'] = new_id

        # details を JSON文字列に変換
        if 'details' in asset_data and isinstance(asset_data['details'], dict):
            asset_data['details'] = json.dumps(asset_data['details'], ensure_ascii=False)

        new_row = pd.DataFrame([asset_data])
        new_row = self._validate_and_process(new_row)

        if len(self.df) == 0:
            self.df = new_row
        else:
            self.df = pd.concat([self.df, new_row], ignore_index=True)

    def update_asset(self, asset_id: str, updates: dict) -> None:
        """資産更新"""
        if self.df is None:
            return

        idx = self.df[self.df['asset_id'] == asset_id].index
        if len(idx) == 0:
            return

        for key, value in updates.items():
            if key in self.df.columns:
                self.df.loc[idx[0], key] = value

    def delete_asset(self, asset_id: str) -> None:
        """資産削除"""
        if self.df is None:
            return
        self.df = self.df[self.df['asset_id'] != asset_id].reset_index(drop=True)

    # 減価償却計算（定額法）
    def calculate_depreciation(self, asset: pd.Series) -> float:
        """年間減価償却費を計算"""
        asset_type = asset.get('asset_type', '')
        purchase_price = asset.get('purchase_price', 0)

        # 金融資産は減価償却なし
        if asset_type == 'financial':
            return 0

        # 耐用年数を取得
        type_config = self.config.get('asset_types', {}).get(asset_type, {})

        if asset_type == 'real_estate':
            details = asset.get('details_parsed', {})
            structure = details.get('type', 'RC')
            years_config = type_config.get('depreciation_years', {})
            useful_life = years_config.get(structure, 47)
        else:
            useful_life = type_config.get('depreciation_years', 6)

        # 定額法: (取得価格 - 残存価格) / 耐用年数
        # 残存価格は取得価格の10%とする
        residual_value = purchase_price * 0.1
        annual_depreciation = (purchase_price - residual_value) / useful_life

        return annual_depreciation

    def calculate_current_book_value(self, asset: pd.Series) -> float:
        """現在の簿価を計算"""
        purchase_date = asset.get('purchase_date')
        purchase_price = asset.get('purchase_price', 0)

        if pd.isna(purchase_date):
            return purchase_price

        # 経過年数
        today = datetime.now()
        years_elapsed = (today - purchase_date).days / 365.25

        # 減価償却累計
        annual_dep = self.calculate_depreciation(asset)
        total_depreciation = annual_dep * years_elapsed

        # 残存価格を下回らない
        residual_value = purchase_price * 0.1
        book_value = max(purchase_price - total_depreciation, residual_value)

        return book_value

    # 集計
    def get_total_assets_value(self) -> float:
        """総資産額"""
        if self.df is None or len(self.df) == 0:
            return 0
        return self.df['current_value'].sum()

    def get_assets_by_type(self, asset_type: str) -> pd.DataFrame:
        """資産種別でフィルタ"""
        if self.df is None:
            return pd.DataFrame()
        return self.df[self.df['asset_type'] == asset_type]

    def asset_composition(self) -> pd.Series:
        """資産種別ごとの合計"""
        if self.df is None or len(self.df) == 0:
            return pd.Series()
        return self.df.groupby('asset_type')['current_value'].sum()

    def get_asset_type_name(self, asset_type: str) -> str:
        """資産種別の日本語名を取得"""
        types = self.config.get('asset_types', {})
        return types.get(asset_type, {}).get('name', asset_type)

    def get_asset_type_icon(self, asset_type: str) -> str:
        """資産種別のアイコンを取得"""
        types = self.config.get('asset_types', {})
        return types.get(asset_type, {}).get('icon', '📦')

    # エクスポート
    def export_csv(self) -> str:
        """CSV文字列として出力"""
        if self.df is None:
            return ''
        export_df = self.df.drop(columns=['details_parsed'], errors='ignore')
        return export_df.to_csv(index=False)

    def save_to_file(self, file_path: str) -> None:
        """ファイルに保存"""
        if self.df is None:
            return
        export_df = self.df.drop(columns=['details_parsed'], errors='ignore')
        export_df.to_csv(file_path, index=False)

    def to_dict(self) -> dict:
        """DataFrameを辞書形式に変換（暗号化保存用）

        Returns:
            資産データの辞書表現
        """
        if self.df is None or len(self.df) == 0:
            return {"assets": [], "metadata": {"version": 1}}

        # details_parsed列を除外してエクスポート
        export_df = self.df.drop(columns=['details_parsed'], errors='ignore')

        # 日付をISO形式文字列に変換
        if 'purchase_date' in export_df.columns:
            export_df['purchase_date'] = export_df['purchase_date'].apply(
                lambda x: x.isoformat() if pd.notna(x) and hasattr(x, 'isoformat') else str(x) if pd.notna(x) else None
            )

        return {
            "assets": export_df.to_dict(orient='records'),
            "metadata": {
                "version": 1,
                "exported_at": datetime.now().isoformat(),
                "count": len(export_df)
            }
        }

    def from_dict(self, data: dict) -> pd.DataFrame:
        """辞書形式からDataFrameを復元

        Args:
            data: to_dict()で生成された辞書

        Returns:
            復元されたDataFrame
        """
        if not data or "assets" not in data:
            return self.create_empty_dataframe()

        assets = data.get("assets", [])
        if not assets:
            return self.create_empty_dataframe()

        df = pd.DataFrame(assets)
        df = self._validate_and_process(df)
        self.df = df
        return df

    def save_encrypted(self, crypto_manager, password: str) -> bool:
        """資産データを暗号化して保存

        Args:
            crypto_manager: CryptoManagerインスタンス
            password: 暗号化パスワード

        Returns:
            保存成功の場合True
        """
        data = self.to_dict()
        return crypto_manager.save_encrypted(data, password)

    def load_encrypted(self, crypto_manager, password: str) -> bool:
        """暗号化された資産データを読み込み

        Args:
            crypto_manager: CryptoManagerインスタンス
            password: 復号パスワード

        Returns:
            読み込み成功の場合True
        """
        data = crypto_manager.load_encrypted(password)
        if data is None:
            return False

        self.from_dict(data)
        return True
