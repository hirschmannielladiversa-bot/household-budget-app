"""レシート画像読み取りモジュール（Gemini API連携）

画像からレシート・明細書の情報を抽出し、
日付・カテゴリ・金額を自動認識するモジュール。
"""
import io
import json
import re
from datetime import datetime
from typing import Optional, Dict, Any

try:
    from google import genai
    from PIL import Image
    GEMINI_AVAILABLE = True
except ImportError:
    try:
        import google.generativeai as genai
        from PIL import Image
        GEMINI_AVAILABLE = True
    except ImportError:
        genai = None
        GEMINI_AVAILABLE = False

from .gemini_utils import call_gemini_with_retry


class ReceiptReader:
    """画像からレシート情報を抽出するクラス

    Gemini APIを使用して画像を解析し、
    日付、店舗名、カテゴリ、金額などを抽出する。
    """

    SYSTEM_PROMPT = """あなたはレシート・明細書の読み取りエキスパートです。
画像から以下の情報を抽出してJSON形式で返してください。

出力形式（必ずこの形式で）:
{
  "date": "YYYY-MM-DD",
  "store_name": "店舗名",
  "category": "カテゴリ",
  "amount": 金額（数値のみ、カンマなし）,
  "memo": "主な商品名や内容（簡潔に）",
  "confidence": 信頼度（0.0〜1.0の数値）
}

カテゴリは以下から最も適切なものを1つ選択:
- 食費（スーパー、コンビニ、飲食店）
- 交通費（電車、バス、タクシー、ガソリン）
- 医療費（病院、薬局、歯科）
- 通信費（携帯、インターネット）
- 光熱費（電気、ガス、水道）
- 住居費（家賃、管理費）
- 保険料（生命保険、医療保険）
- 娯楽費（趣味、旅行、映画）
- 教育費（学費、書籍、習い事）
- 日用品（消耗品、掃除用品）
- 衣服（衣類、靴）
- AI費（ChatGPT、Claude、AI関連サービス）
- 税（所得税、住民税、各種税金）
- 資産（iDeCo、NISA、積立投資）
- 車両費（車検、自動車関連費用）
- その他

注意事項:
- 日付が読み取れない場合は null
- 金額は税込み合計を使用（数値のみ）
- 店舗名が不明な場合は「不明」
- JSONのみを出力（説明文不要）
"""

    VALID_CATEGORIES = [
        "給与", "食費", "交通費", "医療費", "通信費", "光熱費",
        "住居費", "保険料", "娯楽費", "教育費", "日用品",
        "衣服", "AI費", "税", "資産", "車両費", "その他"
    ]

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        """初期化

        Args:
            api_key: Gemini APIキー
            model_name: 使用するモデル名
        """
        if not GEMINI_AVAILABLE:
            raise ImportError(
                "google-genai と Pillow がインストールされていません。\n"
                "pip install google-genai Pillow でインストールしてください。"
            )

        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        self.api_key = api_key

    def read_receipt(self, image_bytes: bytes) -> Dict[str, Any]:
        """画像からレシート情報を抽出

        Args:
            image_bytes: 画像のバイトデータ

        Returns:
            抽出された情報の辞書
        """
        # 画像を開く
        image = Image.open(io.BytesIO(image_bytes))

        # Gemini APIで解析（リトライ付き）
        response = call_gemini_with_retry(self.client, [
            self.SYSTEM_PROMPT,
            image
        ], model_name=self.model_name)

        # レスポンステキストからJSONを抽出
        result = self._parse_response(response.text)

        # 結果を検証・補完
        return self.validate_result(result)

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """APIレスポンスからJSONを抽出

        Args:
            text: APIからのレスポンステキスト

        Returns:
            パースされた辞書
        """
        # ```json ... ``` を除去
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        # 前後の空白を除去
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # JSONパースに失敗した場合、正規表現で抽出を試みる
            return self._extract_with_regex(text)

    def _extract_with_regex(self, text: str) -> Dict[str, Any]:
        """正規表現でデータを抽出（フォールバック）

        Args:
            text: テキスト

        Returns:
            抽出された辞書
        """
        result = {
            "date": None,
            "store_name": "不明",
            "category": "その他",
            "amount": 0,
            "memo": "",
            "confidence": 0.5
        }

        # 金額を探す（¥やカンマを含む数字）
        amount_match = re.search(r'[¥￥]?\s*([\d,]+)\s*円?', text)
        if amount_match:
            amount_str = amount_match.group(1).replace(',', '')
            result["amount"] = int(amount_str)

        # 日付を探す
        date_match = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', text)
        if date_match:
            result["date"] = f"{date_match.group(1)}-{date_match.group(2):0>2}-{date_match.group(3):0>2}"

        return result

    def validate_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """結果の検証と補完

        Args:
            result: 抽出された結果

        Returns:
            検証・補完された結果
        """
        validated = {}

        # 日付
        date_str = result.get("date")
        if date_str:
            try:
                # 日付形式を検証
                datetime.strptime(str(date_str), "%Y-%m-%d")
                validated["date"] = str(date_str)
            except (ValueError, TypeError):
                validated["date"] = None
        else:
            validated["date"] = None

        # 店舗名
        validated["store_name"] = str(result.get("store_name", "不明"))[:50]

        # カテゴリ
        category = result.get("category", "その他")
        if category not in self.VALID_CATEGORIES:
            # 部分一致を試みる
            for valid_cat in self.VALID_CATEGORIES:
                if valid_cat in str(category):
                    category = valid_cat
                    break
            else:
                category = "その他"
        validated["category"] = category

        # 金額
        amount = result.get("amount", 0)
        if isinstance(amount, str):
            amount = int(re.sub(r'[^\d]', '', amount) or 0)
        validated["amount"] = max(0, int(amount))

        # メモ
        validated["memo"] = str(result.get("memo", ""))[:100]

        # 信頼度
        confidence = result.get("confidence", 0.5)
        try:
            confidence = float(confidence)
            confidence = max(0.0, min(1.0, confidence))
        except (ValueError, TypeError):
            confidence = 0.5
        validated["confidence"] = confidence

        return validated

    def format_for_entry(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """支出エントリ用にフォーマット

        Args:
            result: 読み取り結果

        Returns:
            支出エントリ用の辞書
        """
        return {
            "date": result.get("date") or datetime.now().strftime("%Y-%m-%d"),
            "category": result.get("category", "その他"),
            "amount": result.get("amount", 0),
            "memo": f"{result.get('store_name', '')} - {result.get('memo', '')}".strip(" -")
        }


def is_gemini_available() -> bool:
    """Gemini APIが利用可能か確認

    Returns:
        利用可能な場合True
    """
    return GEMINI_AVAILABLE
