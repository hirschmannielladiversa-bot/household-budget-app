"""Gemini API ユーティリティモジュール

レート制限対策のリトライ機能を提供。
"""
import time
import re
from functools import wraps
from typing import Callable, Any, Optional

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

try:
    from google.api_core import exceptions as google_exceptions
except ImportError:
    google_exceptions = None


DEFAULT_MAX_RETRIES = 3
DEFAULT_INITIAL_DELAY = 5.0
DEFAULT_MAX_DELAY = 120.0
DEFAULT_BACKOFF_FACTOR = 2.0


def extract_retry_delay(error_message: str) -> Optional[float]:
    """エラーメッセージからリトライ待機時間を抽出"""
    match = re.search(r'retry in ([\d.]+)s', str(error_message), re.IGNORECASE)
    if match:
        return float(match.group(1))
    match = re.search(r'retry_delay.*?seconds:\s*(\d+)', str(error_message))
    if match:
        return float(match.group(1))
    return None


def is_retryable_error(error: Exception) -> bool:
    """リトライ可能なエラーかどうかを判定（レート制限・503等）"""
    error_str = str(error).lower()
    return (
        '429' in error_str or
        '503' in error_str or
        'unavailable' in error_str or
        'overloaded' in error_str or
        'high demand' in error_str or
        'quota' in error_str or
        ('rate' in error_str and 'limit' in error_str) or
        'exceeded' in error_str
    )


# 後方互換性
is_rate_limit_error = is_retryable_error


def gemini_retry(
    max_retries: int = DEFAULT_MAX_RETRIES,
    initial_delay: float = DEFAULT_INITIAL_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    on_retry: Optional[Callable[[int, float, Exception], None]] = None
):
    """Gemini API呼び出しのリトライデコレータ

    Args:
        max_retries: 最大リトライ回数
        initial_delay: 初期待機時間（秒）
        max_delay: 最大待機時間（秒）
        backoff_factor: 待機時間の増加倍率
        on_retry: リトライ時のコールバック (retry_count, delay, error)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_error = None
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e

                    if not is_rate_limit_error(e):
                        raise

                    if attempt >= max_retries:
                        raise

                    # エラーから推奨待機時間を抽出
                    suggested_delay = extract_retry_delay(str(e))
                    if suggested_delay:
                        wait_time = min(suggested_delay + 1, max_delay)
                    else:
                        wait_time = min(delay, max_delay)

                    if on_retry:
                        on_retry(attempt + 1, wait_time, e)

                    time.sleep(wait_time)
                    delay *= backoff_factor

            raise last_error

        return wrapper
    return decorator


def call_gemini_with_retry(
    client_or_model,
    content,
    max_retries: int = DEFAULT_MAX_RETRIES,
    on_retry: Optional[Callable[[int, float, Exception], None]] = None,
    model_name: str = "gemini-2.5-flash",
) -> Any:
    """Gemini API呼び出しをリトライ付きで実行

    Args:
        client_or_model: google.genai.Client または旧GenerativeModelインスタンス
        content: generate_contentに渡すコンテンツ
        max_retries: 最大リトライ回数
        on_retry: リトライ時のコールバック
        model_name: モデル名（新APIで使用）

    Returns:
        APIレスポンス
    """
    last_error = None
    delay = DEFAULT_INITIAL_DELAY

    # 新API（google.genai.Client）か旧API（GenerativeModel）かを判定
    is_new_api = hasattr(client_or_model, 'models') and hasattr(client_or_model.models, 'generate_content')

    for attempt in range(max_retries + 1):
        try:
            if is_new_api:
                return client_or_model.models.generate_content(
                    model=model_name, contents=content
                )
            else:
                return client_or_model.generate_content(content)
        except Exception as e:
            last_error = e

            if not is_rate_limit_error(e):
                raise

            if attempt >= max_retries:
                raise

            suggested_delay = extract_retry_delay(str(e))
            if suggested_delay:
                wait_time = min(suggested_delay + 1, DEFAULT_MAX_DELAY)
            else:
                wait_time = min(delay, DEFAULT_MAX_DELAY)

            if on_retry:
                on_retry(attempt + 1, wait_time, e)

            time.sleep(wait_time)
            delay *= DEFAULT_BACKOFF_FACTOR

    raise last_error
