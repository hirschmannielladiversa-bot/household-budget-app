"""口座出納管理モジュール"""
import logging
import pandas as pd
import yaml
import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from io import BytesIO

logger = logging.getLogger(__name__)

try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

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


class BankManager:
    """口座出納データの管理を行うクラス"""

    # 口座種別
    ACCOUNT_TYPES = {
        'bank': '銀行口座',
        'securities': '証券口座',
        'credit_card': 'クレジットカード'
    }

    # デフォルトのカテゴリ分類パターン（設定ファイルがない場合のフォールバック）
    DEFAULT_CATEGORY_PATTERNS = {
        '給与': ['給与', '給料', 'SALARY', '賞与', 'ボーナス'],
        '住居費': ['家賃', '管理費', 'UR都市', '住宅', 'マンション'],
        '光熱費': ['東京電力', '東京ガス', '水道', 'TEPCO', '関西電力', '電気', 'ガス代'],
        '通信費': ['NTT', 'KDDI', 'ソフトバンク', 'ドコモ', 'AU', '携帯', 'インターネット'],
        '食費': ['イオン', 'セブン', 'ローソン', 'ファミマ', 'スーパー', 'マルエツ', '西友'],
        '交通費': ['JR', 'SUICA', 'PASMO', 'モバイルSuica', '定期', '電車', 'バス', 'ETC', '高速', 'ガソリン'],
        '保険料': ['生命保険', '損害保険', '保険', 'アフラック', '日本生命'],
        '医療費': ['病院', 'クリニック', '薬局', '医療'],
        '娯楽費': ['映画', 'カラオケ', 'Netflix', 'Amazon Prime', 'Spotify'],
        '教育費': ['学費', '塾', '習い事', '教材'],
        '日用品': ['ダイソー', 'セリア', 'ニトリ', 'IKEA', '無印', 'ホームセンター'],
        '衣服': ['ユニクロ', 'GU', 'ZARA', 'しまむら', 'クリーニング'],
    }

    def __init__(self, config_path: str = None, data_dir: str = None):
        """初期化"""
        self._data_dir = data_dir
        self.config_path = config_path or str(Path(__file__).parent.parent / 'config' / 'bank_formats.yaml')
        self.formats = self._load_formats()
        # 設定ファイルからカテゴリパターンを読み込み
        self.CATEGORY_PATTERNS = self.formats.get('category_patterns', self.DEFAULT_CATEGORY_PATTERNS)

        # 口座マスタ
        self.accounts_df: Optional[pd.DataFrame] = None
        # 取引データ
        self.transactions_df: Optional[pd.DataFrame] = None

        self._init_dataframes()

    def _load_formats(self) -> Dict:
        """CSVフォーマット設定を読み込み"""
        path = Path(self.config_path)
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        return self._get_default_formats()

    def _get_default_formats(self) -> Dict:
        """デフォルトのCSVフォーマット"""
        return {
            'bank': {
                'mufj': {
                    'name': '三菱UFJ銀行',
                    'encoding': 'shift_jis',
                    'columns': {
                        'date': '日付',
                        'description': '摘要',
                        'withdrawal': 'お支払金額',
                        'deposit': 'お預り金額',
                        'balance': '残高'
                    },
                    'date_format': '%Y/%m/%d'
                },
                'smbc': {
                    'name': '三井住友銀行',
                    'encoding': 'shift_jis',
                    'columns': {
                        'date': '年月日',
                        'withdrawal': 'お引出し',
                        'deposit': 'お預入れ',
                        'balance': '残高',
                        'description': '摘要'
                    },
                    'date_format': '%Y/%m/%d'
                },
                'rakuten': {
                    'name': '楽天銀行',
                    'encoding': 'utf-8',
                    'columns': {
                        'date': '取引日',
                        'amount': '入出金(税込)',
                        'balance': '取引後残高',
                        'description': '摘要'
                    },
                    'date_format': '%Y/%m/%d'
                },
                'generic': {
                    'name': '汎用フォーマット',
                    'encoding': 'utf-8',
                    'columns': {
                        'date': '日付',
                        'description': '摘要',
                        'amount': '金額',
                        'balance': '残高'
                    },
                    'date_format': '%Y-%m-%d'
                }
            },
            'credit_card': {
                'rakuten_card': {
                    'name': '楽天カード',
                    'encoding': 'shift_jis',
                    'columns': {
                        'date': 'ご利用日',
                        'description': 'ご利用店名',
                        'amount': 'ご利用金額'
                    },
                    'date_format': '%Y/%m/%d'
                },
                'smbc_card': {
                    'name': '三井住友カード',
                    'encoding': 'shift_jis',
                    'columns': {
                        'date': 'ご利用日',
                        'description': 'ご利用先',
                        'amount': 'ご利用金額'
                    },
                    'date_format': '%Y/%m/%d'
                },
                'generic_card': {
                    'name': '汎用クレカ',
                    'encoding': 'utf-8',
                    'columns': {
                        'date': '日付',
                        'description': '店舗名',
                        'amount': '金額'
                    },
                    'date_format': '%Y-%m-%d'
                }
            }
        }

    def _init_dataframes(self) -> None:
        """DataFrameを初期化"""
        self.accounts_df = pd.DataFrame(columns=[
            'account_id', 'account_type', 'name', 'bank_name',
            'initial_balance', 'current_balance', 'created_at'
        ])
        self.transactions_df = pd.DataFrame(columns=[
            'transaction_id', 'account_id', 'date', 'description',
            'amount', 'balance', 'category', 'memo', 'created_at'
        ])

    # === 口座管理 ===

    def add_account(self, name: str, account_type: str, bank_name: str = '',
                    initial_balance: float = 0) -> str:
        """口座を追加

        Args:
            name: 口座名
            account_type: 種別（bank/securities/credit_card）
            bank_name: 金融機関名
            initial_balance: 初期残高

        Returns:
            生成された口座ID
        """
        # ID生成
        prefix = {'bank': 'B', 'securities': 'S', 'credit_card': 'C'}.get(account_type, 'X')
        existing_ids = self.accounts_df['account_id'].tolist()
        num = 1
        while f"{prefix}{num:03d}" in existing_ids:
            num += 1
        account_id = f"{prefix}{num:03d}"

        new_row = pd.DataFrame([{
            'account_id': account_id,
            'account_type': account_type,
            'name': name,
            'bank_name': bank_name,
            'initial_balance': initial_balance,
            'current_balance': initial_balance,
            'created_at': datetime.now().isoformat()
        }])

        self.accounts_df = pd.concat([self.accounts_df, new_row], ignore_index=True)
        return account_id

    def update_account(self, account_id: str, updates: Dict) -> bool:
        """口座情報を更新"""
        idx = self.accounts_df[self.accounts_df['account_id'] == account_id].index
        if len(idx) == 0:
            return False

        for key, value in updates.items():
            if key in self.accounts_df.columns:
                self.accounts_df.loc[idx[0], key] = value
        return True

    def delete_account(self, account_id: str) -> bool:
        """口座を削除"""
        if account_id not in self.accounts_df['account_id'].values:
            return False

        self.accounts_df = self.accounts_df[
            self.accounts_df['account_id'] != account_id
        ].reset_index(drop=True)

        # 関連取引も削除
        self.transactions_df = self.transactions_df[
            self.transactions_df['account_id'] != account_id
        ].reset_index(drop=True)

        return True

    def get_account(self, account_id: str) -> Optional[Dict]:
        """口座情報を取得"""
        row = self.accounts_df[self.accounts_df['account_id'] == account_id]
        if len(row) == 0:
            return None
        return row.iloc[0].to_dict()

    def get_accounts_by_type(self, account_type: str) -> pd.DataFrame:
        """種別で口座をフィルタ"""
        return self.accounts_df[self.accounts_df['account_type'] == account_type]

    # === 取引管理 ===

    def is_duplicate_transaction(self, account_id: str, date: Any,
                                   description: str, amount: float) -> bool:
        """重複取引かどうかをチェック

        Args:
            account_id: 口座ID
            date: 日付
            description: 摘要
            amount: 金額

        Returns:
            重複している場合True
        """
        if self.transactions_df is None or len(self.transactions_df) == 0:
            return False

        # 日付変換
        if isinstance(date, str):
            date = pd.to_datetime(date)

        # 正規化して比較
        normalized_desc = unicodedata.normalize('NFKC', str(description)).upper().strip()

        for _, row in self.transactions_df.iterrows():
            if row['account_id'] != account_id:
                continue

            row_date = pd.to_datetime(row['date'])
            if row_date.date() != date.date():
                continue

            row_desc = unicodedata.normalize('NFKC', str(row['description'])).upper().strip()
            if row_desc != normalized_desc:
                continue

            if abs(row['amount'] - amount) < 0.01:  # 金額が一致
                return True

        return False

    def add_transaction(self, account_id: str, date: Any, description: str,
                        amount: float, balance: float = None,
                        category: str = None, memo: str = '',
                        skip_duplicate_check: bool = False) -> str:
        """取引を追加

        Args:
            account_id: 口座ID
            date: 日付
            description: 摘要
            amount: 金額（入金:+, 出金:-）
            balance: 取引後残高
            category: カテゴリ
            memo: メモ
            skip_duplicate_check: 重複チェックをスキップするか

        Returns:
            取引ID（重複の場合はNone）
        """
        # 日付変換
        if isinstance(date, str):
            date = pd.to_datetime(date)

        # 重複チェック
        if not skip_duplicate_check:
            if self.is_duplicate_transaction(account_id, date, description, amount):
                return None  # 重複のため追加しない

        # ID生成
        num = len(self.transactions_df) + 1
        transaction_id = f"T{num:06d}"

        # カテゴリ自動判定
        if category is None:
            category = self.classify_category(description)

        new_row = pd.DataFrame([{
            'transaction_id': transaction_id,
            'account_id': account_id,
            'date': date,
            'description': description,
            'amount': amount,
            'balance': balance,
            'category': category,
            'memo': memo,
            'created_at': datetime.now().isoformat()
        }])

        self.transactions_df = pd.concat([self.transactions_df, new_row], ignore_index=True)

        # 口座残高を更新
        if balance is not None:
            self.update_account(account_id, {'current_balance': balance})

        return transaction_id

    def remove_duplicates(self) -> int:
        """重複取引を削除

        Returns:
            削除された件数
        """
        if self.transactions_df is None or len(self.transactions_df) == 0:
            return 0

        original_count = len(self.transactions_df)

        # 正規化した摘要カラムを作成
        self.transactions_df['normalized_desc'] = self.transactions_df['description'].apply(
            lambda x: unicodedata.normalize('NFKC', str(x)).upper().strip()
        )

        # 日付を正規化
        self.transactions_df['date_only'] = pd.to_datetime(self.transactions_df['date']).dt.date

        # 重複を削除（最初のレコードを残す）
        self.transactions_df = self.transactions_df.drop_duplicates(
            subset=['account_id', 'date_only', 'normalized_desc', 'amount'],
            keep='first'
        )

        # 一時カラムを削除
        self.transactions_df = self.transactions_df.drop(columns=['normalized_desc', 'date_only'])

        removed_count = original_count - len(self.transactions_df)

        return removed_count

    def classify_category(self, description: str) -> str:
        """摘要からカテゴリを推定

        Args:
            description: 摘要

        Returns:
            カテゴリ名
        """
        # NFKC正規化で半角全角を統一し、大文字に変換
        normalized_desc = unicodedata.normalize('NFKC', description).upper()

        for category, patterns in self.CATEGORY_PATTERNS.items():
            for pattern in patterns:
                # パターンも同様に正規化
                normalized_pattern = unicodedata.normalize('NFKC', pattern).upper()
                if normalized_pattern in normalized_desc:
                    return category

        return 'その他'

    def reclassify_transactions(self, only_other: bool = True) -> int:
        """取引のカテゴリを再分類

        Args:
            only_other: Trueの場合「その他」のみ再分類、Falseで全件再分類

        Returns:
            再分類された件数
        """
        if self.transactions_df is None or len(self.transactions_df) == 0:
            return 0

        count = 0
        for idx, row in self.transactions_df.iterrows():
            if only_other and row['category'] != 'その他':
                continue

            # メモに使途が記入済みの場合、手動分類とみなしスキップ
            memo = str(row.get('memo', '') or '').strip()
            if not only_other and memo and row['category'] != '交通費':
                continue

            new_category = self.classify_category(row['description'])
            if new_category != row['category']:
                self.transactions_df.loc[idx, 'category'] = new_category
                count += 1

        return count

    def get_transactions(self, account_id: str = None,
                         start_date: Any = None, end_date: Any = None,
                         category: str = None) -> pd.DataFrame:
        """取引を検索

        Args:
            account_id: 口座ID（Noneで全口座）
            start_date: 開始日
            end_date: 終了日
            category: カテゴリ

        Returns:
            取引DataFrame
        """
        df = self.transactions_df.copy()

        if account_id:
            df = df[df['account_id'] == account_id]

        if start_date:
            df = df[df['date'] >= pd.to_datetime(start_date)]

        if end_date:
            df = df[df['date'] <= pd.to_datetime(end_date)]

        if category:
            df = df[df['category'] == category]

        return df.sort_values('date', ascending=False)

    # === CSVインポート ===

    def import_csv(self, file: Any, account_id: str, format_type: str,
                   account_type: str = 'bank') -> Tuple[int, List[str]]:
        """CSVファイルをインポート

        Args:
            file: ファイルパスまたはバイトデータ
            account_id: 口座ID
            format_type: フォーマットタイプ
            account_type: 口座種別

        Returns:
            (インポート件数, エラーリスト)
        """
        errors = []

        # フォーマット取得
        formats = self.formats.get(account_type, {})
        fmt = formats.get(format_type)

        if not fmt:
            return 0, [f"フォーマット '{format_type}' が見つかりません"]

        # CSV読み込み
        try:
            encoding = fmt.get('encoding', 'utf-8')

            if isinstance(file, bytes):
                df = pd.read_csv(BytesIO(file), encoding=encoding)
            elif isinstance(file, str):
                df = pd.read_csv(file, encoding=encoding)
            else:
                df = pd.read_csv(file, encoding=encoding)

        except Exception as e:
            logger.error(f"CSV読み込みエラー: {e}")
            return 0, ["CSV読み込みに失敗しました。ファイル形式を確認してください。"]

        # カラムマッピング
        columns = fmt.get('columns', {})
        date_format = fmt.get('date_format', '%Y-%m-%d')
        date_no_year = fmt.get('date_no_year', False)

        count = 0
        for idx, row in df.iterrows():
            try:
                # 日付
                date_col = columns.get('date', '日付')
                date_str = str(row.get(date_col, ''))
                if not date_str or date_str == 'nan':
                    continue

                try:
                    if date_no_year:
                        # 年なしの場合、現在の年を付与
                        current_year = datetime.now().year
                        date = datetime.strptime(f"{current_year}年{date_str}", f"%Y年{date_format}")
                    else:
                        date = datetime.strptime(date_str, date_format)
                except:
                    date = pd.to_datetime(date_str)

                # 摘要
                desc_col = columns.get('description', '摘要')
                description = str(row.get(desc_col, ''))

                # 金額
                amount = 0
                if 'amount' in columns:
                    amount_col = columns['amount']
                    amount = self._parse_amount(row.get(amount_col, 0))
                else:
                    # 入出金分離形式
                    withdrawal_col = columns.get('withdrawal', 'お支払金額')
                    deposit_col = columns.get('deposit', 'お預り金額')

                    withdrawal = self._parse_amount(row.get(withdrawal_col, 0))
                    deposit = self._parse_amount(row.get(deposit_col, 0))

                    amount = deposit - withdrawal

                # クレジットカードは出金扱い
                if account_type == 'credit_card' and amount > 0:
                    amount = -amount

                # 残高
                balance = None
                if 'balance' in columns:
                    balance_col = columns['balance']
                    balance = self._parse_amount(row.get(balance_col))

                # 取引追加（重複チェック付き）
                result = self.add_transaction(
                    account_id=account_id,
                    date=date,
                    description=description,
                    amount=amount,
                    balance=balance
                )
                if result is not None:
                    count += 1
                # 重複の場合はresult=Noneなのでカウントしない

            except Exception as e:
                errors.append(f"行 {idx + 1}: {e}")

        return count, errors

    def _parse_amount(self, value: Any) -> float:
        """金額をパース"""
        if value is None or pd.isna(value):
            return 0

        if isinstance(value, (int, float)):
            return float(value)

        # 文字列の場合
        s = str(value)
        # 各種円記号・通貨記号を除去（Shift-JISの円記号はバックスラッシュとして読み込まれる）
        s = s.replace(',', '').replace('\\', '').replace('¥', '').replace('￥', '').replace('\u00a5', '').replace('円', '').strip()

        if not s or s == '-':
            return 0

        try:
            return float(s)
        except:
            return 0

    def import_from_bytes(self, data: bytes, account_id: str, format_type: str,
                          account_type: str = 'bank') -> Tuple[int, List[str]]:
        """バイトデータからインポート"""
        return self.import_csv(data, account_id, format_type, account_type)

    def import_pdf(
        self,
        file: Any,
        account_id: str,
        gemini_api_key: str = None,
        split: bool = False,
        chunk_pages: int = 3,
        max_text_len: int = 8000,
    ) -> Tuple[int, List[str]]:
        """PDFカード明細をインポート

        Args:
            file: PDFファイル（パスまたはバイトデータ）
            account_id: 口座ID
            gemini_api_key: Gemini APIキー
            split: Gemini解析用にPDFをページ単位で分割するか
            chunk_pages: 1チャンクあたりのページ数（split=True のとき）
            max_text_len: 1回のGemini呼び出しに渡すテキスト上限（文字数）

        Returns:
            (インポート件数, エラーリスト)
        """
        errors = []

        if not PDF_AVAILABLE:
            return 0, ["pdfplumberがインストールされていません: pip install pdfplumber"]

        if not GEMINI_AVAILABLE or genai is None:
            return 0, ["google-generativeaiがインストールされていません"]

        if not gemini_api_key:
            return 0, ["Gemini APIキーが設定されていません"]

        # PDFからテキスト抽出（各ページごと）
        try:
            if isinstance(file, bytes):
                pdf = pdfplumber.open(BytesIO(file))
            else:
                pdf = pdfplumber.open(file)

            page_texts: List[str] = []
            for page in pdf.pages:
                page_texts.append(page.extract_text() or "")
            pdf.close()

        except Exception as e:
            logger.error(f"PDF読み込みエラー: {e}")
            return 0, ["PDFの読み込みに失敗しました。ファイルを確認してください。"]

        if not any(t.strip() for t in page_texts):
            return 0, ["PDFからテキストを抽出できませんでした"]

        # Gemini APIで解析（分割する場合はチャンクごとに複数回呼び出し）
        prompt_template = """以下はクレジットカード明細のPDFから抽出したテキストです。
取引データを抽出してJSON形式で返してください。

【抽出テキスト】
{text}

【出力形式】（説明なし、JSONのみ）:
{{
    "card_name": "カード名（分かれば）",
    "statement_period": "明細期間（分かれば）",
    "transactions": [
        {{
            "date": "YYYY-MM-DD",
            "description": "利用店舗・内容",
            "amount": 金額（数値のみ、正の数）
        }}
    ]
}}

注意:
- 日付が不完全な場合は推測してください
- 金額は正の数値で（クレジットは出金として扱います）
- 年会費、分割手数料なども取引として含めてください
"""

        # チャンク作成（ページ分割）
        if split and chunk_pages and chunk_pages > 0:
            chunks: List[str] = []
            for start in range(0, len(page_texts), chunk_pages):
                end = min(start + chunk_pages, len(page_texts))
                chunk_text = "\n--- ページ区切り ---\n".join(page_texts[start:end])
                chunks.append(chunk_text)
        else:
            chunks = ["\n--- ページ区切り ---\n".join(page_texts)]

        try:
            client = genai.Client(api_key=gemini_api_key)
        except Exception as e:
            logger.error(f"Gemini API設定エラー: {e}")
            return 0, ["Gemini APIの設定に失敗しました。APIキーを確認してください。"]

        total_count = 0

        for chunk_idx, chunk_text in enumerate(chunks, start=1):
            chunk_prompt = prompt_template.format(text=chunk_text[:max_text_len])

            try:
                response = call_gemini_with_retry(client, chunk_prompt)
                result_text = response.text
            except Exception as e:
                logger.error(f"チャンク {chunk_idx}: Gemini APIエラー: {e}")
                errors.append(f"チャンク {chunk_idx}: API通信に失敗しました。再試行してください。")
                continue

            # JSONを抽出
            json_match = re.search(r"\{[\s\S]*\}", result_text)
            if not json_match:
                errors.append(f"チャンク {chunk_idx}: AIの応答からJSONを抽出できませんでした")
                continue

            try:
                data = json.loads(json_match.group())
            except json.JSONDecodeError as e:
                logger.error(f"チャンク {chunk_idx}: JSON解析エラー: {e}")
                errors.append(f"チャンク {chunk_idx}: 応答の解析に失敗しました")
                continue

            transactions = data.get("transactions", [])
            if not transactions:
                errors.append(f"チャンク {chunk_idx}: 取引データが見つかりませんでした")
                continue

            # 取引を追加
            for trans in transactions:
                try:
                    date_str = trans.get("date", "")
                    description = trans.get("description", "")
                    amount = float(trans.get("amount", 0))

                    if not date_str or not description or amount <= 0:
                        continue

                    # 日付パース
                    try:
                        date = datetime.strptime(date_str, "%Y-%m-%d")
                    except Exception:
                        try:
                            date = pd.to_datetime(date_str)
                        except Exception:
                            errors.append(f"日付パースエラー: {date_str}")
                            continue

                    # クレジットカードなので出金として登録
                    tid = self.add_transaction(
                        account_id=account_id,
                        date=date,
                        description=description,
                        amount=-amount,  # 出金はマイナス
                        balance=None,
                    )
                    if tid is not None:
                        total_count += 1

                except Exception as e:
                    logger.error(f"取引追加エラー: {e}")
                    errors.append("取引データの追加に失敗しました")

        return total_count, errors

    def import_pdf_from_bytes(
        self,
        data: bytes,
        account_id: str,
        gemini_api_key: str = None,
        split: bool = False,
        chunk_pages: int = 3,
        max_text_len: int = 8000,
    ) -> Tuple[int, List[str]]:
        """バイトデータからPDFインポート"""
        return self.import_pdf(
            data,
            account_id,
            gemini_api_key,
            split=split,
            chunk_pages=chunk_pages,
            max_text_len=max_text_len,
        )

    def import_statement_image(
        self,
        image_bytes: bytes,
        account_id: str,
        gemini_api_key: str,
        is_credit_card: bool = False,
    ) -> Tuple[int, List[str]]:
        """口座取引履歴の画像をGemini Visionで解析してインポート

        Args:
            image_bytes: 画像バイトデータ (JPG/PNG)
            account_id: 口座ID
            gemini_api_key: Gemini APIキー
            is_credit_card: クレジットカード明細かどうか

        Returns:
            (インポート件数, エラーリスト)
        """
        errors = []

        if not GEMINI_AVAILABLE or genai is None:
            return 0, ["google-generativeaiがインストールされていません"]
        if not gemini_api_key:
            return 0, ["Gemini APIキーが設定されていません"]

        sign_instruction = "金額はクレジット支出なのでマイナス値にしてください" if is_credit_card else "入金はプラス、出金はマイナスで表してください"

        prompt = f"""この画像は銀行口座またはカードの取引明細です。
取引データを正確に読み取り、JSON形式で返してください。

【出力形式】（説明なし、JSONのみ）:
{{
    "transactions": [
        {{
            "date": "YYYY-MM-DD",
            "description": "摘要・内容",
            "amount": 金額（数値のみ）,
            "balance": 残高（数値、不明ならnull）
        }}
    ]
}}

注意:
- {sign_instruction}
- 日付が不完全な場合は年を推測してください
- 金額の千円区切りカンマは除去してください
- 読み取れない文字は最善の推測をしてください
"""

        try:
            import base64
            client = genai.Client(api_key=gemini_api_key)
            image_part = {
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": base64.b64encode(image_bytes).decode("utf-8"),
                }
            }
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[prompt, image_part],
            )
            result_text = response.text
        except Exception as e:
            logger.error(f"Gemini Vision APIエラー: {e}")
            return 0, ["画像解析に失敗しました。APIキーの有効期限や利用制限を確認してください。"]

        json_match = re.search(r"\{[\s\S]*\}", result_text)
        if not json_match:
            return 0, ["AIの応答からJSONを抽出できませんでした"]

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析エラー: {e}")
            return 0, ["AIの応答を解析できませんでした。再試行してください。"]

        transactions = data.get("transactions", [])
        if not transactions:
            return 0, ["取引データが見つかりませんでした"]

        total_count = 0
        for trans in transactions:
            try:
                date_str = trans.get("date", "")
                description = trans.get("description", "")
                amount = float(trans.get("amount", 0))
                balance = trans.get("balance")
                if balance is not None:
                    try:
                        balance = float(balance)
                    except (ValueError, TypeError):
                        balance = None

                if not date_str or not description:
                    continue

                try:
                    date = datetime.strptime(date_str, "%Y-%m-%d")
                except Exception:
                    try:
                        date = pd.to_datetime(date_str)
                    except Exception:
                        errors.append(f"日付パースエラー: {date_str}")
                        continue

                tid = self.add_transaction(
                    account_id=account_id,
                    date=date,
                    description=description,
                    amount=amount,
                    balance=balance,
                )
                if tid is not None:
                    total_count += 1
            except Exception as e:
                logger.error(f"取引追加エラー: {e}")
                errors.append("取引データの追加に失敗しました")

        return total_count, errors

    def import_bank_pdf(
        self,
        file_bytes: bytes,
        account_id: str,
        gemini_api_key: str,
        is_credit_card: bool = False,
        split: bool = True,
        chunk_pages: int = 3,
    ) -> Tuple[int, List[str]]:
        """銀行口座のPDF取引履歴をインポート（汎用版）"""
        errors = []

        if not PDF_AVAILABLE:
            return 0, ["pdfplumberがインストールされていません"]
        if not GEMINI_AVAILABLE or genai is None:
            return 0, ["google-generativeaiがインストールされていません"]
        if not gemini_api_key:
            return 0, ["Gemini APIキーが設定されていません"]

        try:
            pdf = pdfplumber.open(BytesIO(file_bytes))
            page_texts = [page.extract_text() or "" for page in pdf.pages]
            pdf.close()
        except Exception as e:
            logger.error(f"PDF読み込みエラー: {e}")
            return 0, ["PDFの読み込みに失敗しました。ファイルを確認してください。"]

        if not any(t.strip() for t in page_texts):
            return 0, ["PDFからテキストを抽出できませんでした"]

        sign_instruction = "金額はクレジット支出なのでマイナス値にしてください" if is_credit_card else "入金はプラス、出金はマイナスで表してください"

        prompt_template = f"""以下は口座取引明細のPDFから抽出したテキストです。
取引データを正確に抽出してJSON形式で返してください。

【抽出テキスト】
{{text}}

【出力形式】（説明なし、JSONのみ）:
{{{{
    "transactions": [
        {{{{
            "date": "YYYY-MM-DD",
            "description": "摘要・内容",
            "amount": 金額（数値のみ）,
            "balance": 残高（数値、不明ならnull）
        }}}}
    ]
}}}}

注意:
- {sign_instruction}
- 日付が不完全な場合は年を推測してください
- 年会費、手数料なども含めてください
"""

        if split and chunk_pages > 0:
            chunks = []
            for start in range(0, len(page_texts), chunk_pages):
                end = min(start + chunk_pages, len(page_texts))
                chunks.append("\n--- ページ区切り ---\n".join(page_texts[start:end]))
        else:
            chunks = ["\n--- ページ区切り ---\n".join(page_texts)]

        try:
            client = genai.Client(api_key=gemini_api_key)
        except Exception as e:
            logger.error(f"Gemini API設定エラー: {e}")
            return 0, ["Gemini APIの設定に失敗しました。APIキーを確認してください。"]

        total_count = 0
        for chunk_idx, chunk_text in enumerate(chunks, start=1):
            chunk_prompt = prompt_template.format(text=chunk_text[:8000])
            try:
                response = call_gemini_with_retry(client, chunk_prompt)
                result_text = response.text
            except Exception as e:
                logger.error(f"チャンク {chunk_idx}: APIエラー: {e}")
                errors.append(f"チャンク {chunk_idx}: API通信に失敗しました")
                continue

            json_match = re.search(r"\{[\s\S]*\}", result_text)
            if not json_match:
                errors.append(f"チャンク {chunk_idx}: JSON抽出失敗")
                continue

            try:
                data = json.loads(json_match.group())
            except json.JSONDecodeError:
                errors.append(f"チャンク {chunk_idx}: JSON解析エラー")
                continue

            for trans in data.get("transactions", []):
                try:
                    date_str = trans.get("date", "")
                    description = trans.get("description", "")
                    amount = float(trans.get("amount", 0))
                    balance = trans.get("balance")
                    if balance is not None:
                        try:
                            balance = float(balance)
                        except (ValueError, TypeError):
                            balance = None

                    if not date_str or not description:
                        continue

                    try:
                        date = datetime.strptime(date_str, "%Y-%m-%d")
                    except Exception:
                        try:
                            date = pd.to_datetime(date_str)
                        except Exception:
                            continue

                    tid = self.add_transaction(
                        account_id=account_id,
                        date=date,
                        description=description,
                        amount=amount,
                        balance=balance,
                    )
                    if tid is not None:
                        total_count += 1
                except Exception:
                    continue

        return total_count, errors

    # === 集計 ===

    def get_balance(self, account_id: str, date: Any = None) -> float:
        """口座残高を取得"""
        account = self.get_account(account_id)
        if not account:
            return 0

        if date is None:
            return account.get('current_balance', 0)

        # 指定日時点の残高
        trans = self.get_transactions(account_id, end_date=date)
        if len(trans) > 0:
            return trans.iloc[0]['balance'] or 0

        return account.get('initial_balance', 0)

    def get_balance_history(self, account_id: str = None,
                            start_date: Any = None, end_date: Any = None) -> pd.DataFrame:
        """残高推移を取得"""
        trans = self.get_transactions(account_id, start_date, end_date)

        if len(trans) == 0:
            return pd.DataFrame(columns=['date', 'balance'])

        df = trans[['date', 'balance', 'account_id']].copy()
        df = df.sort_values('date')
        df = df.dropna(subset=['balance'])

        return df

    def get_monthly_summary(self, account_id: str = None,
                            year: int = None, month: int = None) -> pd.DataFrame:
        """月別サマリーを取得"""
        trans = self.transactions_df.copy()

        if account_id:
            trans = trans[trans['account_id'] == account_id]

        if len(trans) == 0:
            return pd.DataFrame()

        trans['year_month'] = trans['date'].dt.to_period('M')

        if year and month:
            period = pd.Period(f"{year}-{month:02d}")
            trans = trans[trans['year_month'] == period]

        summary = trans.groupby('year_month').agg({
            'amount': [
                ('入金', lambda x: x[x > 0].sum()),
                ('出金', lambda x: x[x < 0].sum()),
                ('収支', 'sum')
            ]
        }).reset_index()

        summary.columns = ['年月', '入金', '出金', '収支']
        return summary

    def get_category_breakdown(self, account_id: str = None,
                               start_date: Any = None, end_date: Any = None) -> pd.DataFrame:
        """カテゴリ別集計"""
        trans = self.get_transactions(account_id, start_date, end_date)

        if len(trans) == 0:
            return pd.DataFrame(columns=['カテゴリ', '入金', '出金', '件数'])

        # 出金のみ集計（除外カテゴリを除く）
        expenses = trans[(trans['amount'] < 0) & (trans['category'] != '除外')].copy()
        expenses['amount'] = expenses['amount'].abs()

        summary = expenses.groupby('category').agg({
            'amount': 'sum',
            'transaction_id': 'count'
        }).reset_index()

        summary.columns = ['カテゴリ', '金額', '件数']
        return summary.sort_values('金額', ascending=False)

    def get_total_balance(self) -> Dict[str, float]:
        """全口座の残高サマリー"""
        if self.accounts_df is None or len(self.accounts_df) == 0:
            return {'総資産': 0, '総負債': 0, '純資産': 0}

        assets = self.accounts_df[
            self.accounts_df['account_type'].isin(['bank', 'securities'])
        ]['current_balance'].sum()

        liabilities = abs(self.accounts_df[
            self.accounts_df['account_type'] == 'credit_card'
        ]['current_balance'].sum())

        return {
            '総資産': assets,
            '総負債': liabilities,
            '純資産': assets - liabilities
        }

    def export_expenses_to_budget(self, start_date: Any = None, end_date: Any = None,
                                   account_ids: List[str] = None) -> pd.DataFrame:
        """マイナス取引（支出）を家計データ形式でエクスポート

        Args:
            start_date: 開始日
            end_date: 終了日
            account_ids: 対象口座ID（Noneの場合は全口座）

        Returns:
            家計データ形式のDataFrame (日付, カテゴリ, 金額, メモ)
        """
        if self.transactions_df is None or len(self.transactions_df) == 0:
            return pd.DataFrame(columns=['日付', 'カテゴリ', '金額', 'メモ'])

        # フィルタリング
        df = self.transactions_df.copy()

        # マイナス（支出）のみ
        df = df[df['amount'] < 0]

        if len(df) == 0:
            return pd.DataFrame(columns=['日付', 'カテゴリ', '金額', 'メモ'])

        # 日付フィルタ
        if start_date:
            start_date = pd.to_datetime(start_date)
            df = df[df['date'] >= start_date]

        if end_date:
            end_date = pd.to_datetime(end_date)
            df = df[df['date'] <= end_date]

        # 口座フィルタ
        if account_ids:
            df = df[df['account_id'].isin(account_ids)]

        # 除外カテゴリをフィルタ（給与=入金関連も除外）
        df = df[~df['category'].isin(['除外', '給与'])]

        if len(df) == 0:
            return pd.DataFrame(columns=['日付', 'カテゴリ', '金額', 'メモ'])

        # 家計データ形式に変換（最新パターンでカテゴリ再分類）
        budget_df = pd.DataFrame({
            '日付': df['date'],
            'カテゴリ': df['description'].apply(self.classify_category),
            '金額': df['amount'].abs(),  # 正の数に変換
            'メモ': df['description']
        })

        return budget_df.sort_values('日付').reset_index(drop=True)

    def get_unexported_expenses(self, exported_ids: List[str] = None) -> pd.DataFrame:
        """まだエクスポートされていない支出取引を取得

        Args:
            exported_ids: 既にエクスポート済みの取引ID

        Returns:
            未エクスポートの支出取引
        """
        if self.transactions_df is None or len(self.transactions_df) == 0:
            return pd.DataFrame()

        df = self.transactions_df[self.transactions_df['amount'] < 0].copy()

        if exported_ids:
            df = df[~df['transaction_id'].isin(exported_ids)]

        return df

    # === データI/O ===

    def to_dict(self) -> Dict:
        """辞書形式で出力"""
        return {
            'accounts': self.accounts_df.to_dict(orient='records'),
            'transactions': self.transactions_df.to_dict(orient='records'),
            'metadata': {
                'version': 1,
                'exported_at': datetime.now().isoformat()
            }
        }

    def from_dict(self, data: Dict) -> None:
        """辞書形式から復元"""
        if 'accounts' in data:
            self.accounts_df = pd.DataFrame(data['accounts'])

        if 'transactions' in data:
            self.transactions_df = pd.DataFrame(data['transactions'])
            if 'date' in self.transactions_df.columns:
                self.transactions_df['date'] = pd.to_datetime(self.transactions_df['date'])

    def save_to_csv(self, path: str = None) -> None:
        """CSVに保存"""
        base_path = path or self._data_dir or str(Path(__file__).parent.parent / 'data')
        Path(base_path).mkdir(parents=True, exist_ok=True)

        self.accounts_df.to_csv(f"{base_path}/accounts.csv", index=False, encoding='utf-8')
        self.transactions_df.to_csv(f"{base_path}/transactions.csv", index=False, encoding='utf-8')

    def load_from_csv(self, path: str = None) -> bool:
        """CSVから読み込み"""
        base_path = path or self._data_dir or str(Path(__file__).parent.parent / 'data')

        accounts_path = Path(f"{base_path}/accounts.csv")
        trans_path = Path(f"{base_path}/transactions.csv")

        if not accounts_path.exists():
            return False

        self.accounts_df = pd.read_csv(accounts_path, encoding='utf-8')

        if trans_path.exists():
            self.transactions_df = pd.read_csv(trans_path, encoding='utf-8')
            if 'date' in self.transactions_df.columns:
                self.transactions_df['date'] = pd.to_datetime(self.transactions_df['date'])

        return True

    def get_format_list(self, account_type: str = 'bank') -> List[Dict]:
        """利用可能なフォーマット一覧"""
        formats = self.formats.get(account_type, {})
        return [
            {'id': k, 'name': v.get('name', k)}
            for k, v in formats.items()
        ]
