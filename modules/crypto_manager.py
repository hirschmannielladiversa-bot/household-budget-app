"""データ暗号化モジュール

資産データをパスワードベースで暗号化・復号するためのモジュール。
PBKDF2で鍵導出、Fernetで暗号化を行う。
"""
import os
import json
import base64
from pathlib import Path
from typing import Optional, Union
from datetime import datetime

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


class CryptoManager:
    """パスワードベースの暗号化管理クラス

    セキュリティ仕様:
    - 鍵導出: PBKDF2-HMAC-SHA256, 480,000イテレーション (OWASP 2023推奨)
    - 暗号化: Fernet (AES-128-CBC + HMAC-SHA256)
    - ソルト: 16バイトのランダム値、ファイル保存
    """

    SALT_FILE = "data/.salt"
    ENCRYPTED_FILE = "data/assets.encrypted"
    ITERATIONS = 480000  # OWASP 2023 recommended

    def __init__(self, base_dir: Union[str, Path] = "."):
        """初期化

        Args:
            base_dir: プロジェクトのベースディレクトリ
        """
        self.base_dir = Path(base_dir)
        self._validate_crypto_available()

    def _validate_crypto_available(self) -> None:
        """cryptographyライブラリの存在確認"""
        if not CRYPTO_AVAILABLE:
            raise ImportError(
                "cryptography ライブラリがインストールされていません。\n"
                "pip install cryptography でインストールしてください。"
            )

    def _get_salt_path(self) -> Path:
        """ソルトファイルのパスを取得"""
        return self.base_dir / self.SALT_FILE

    def _get_encrypted_path(self) -> Path:
        """暗号化ファイルのパスを取得"""
        return self.base_dir / self.ENCRYPTED_FILE

    def _get_or_create_salt(self) -> bytes:
        """ソルトを取得または新規生成

        Returns:
            16バイトのソルト
        """
        salt_path = self._get_salt_path()
        if salt_path.exists():
            return salt_path.read_bytes()

        # 新規ソルト生成
        salt = os.urandom(16)
        salt_path.parent.mkdir(parents=True, exist_ok=True)
        salt_path.write_bytes(salt)
        return salt

    def _validate_password(self, password: str) -> None:
        """パスワード強度の検証"""
        if len(password) < 8:
            raise ValueError("パスワードは8文字以上必要です")
        if password.isdigit() or password.isalpha():
            raise ValueError("パスワードには英数字を混ぜてください")

    def _derive_key(self, password: str) -> bytes:
        """パスワードから暗号化キーを導出

        Args:
            password: ユーザーパスワード

        Returns:
            Fernet用の32バイトキー（base64エンコード済み）
        """
        salt = self._get_or_create_salt()
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self.ITERATIONS,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode('utf-8')))
        return key

    def encrypt_data(self, data: dict, password: str) -> bytes:
        """辞書データを暗号化

        Args:
            data: 暗号化する辞書データ
            password: 暗号化パスワード

        Returns:
            暗号化されたバイト列
        """
        self._validate_password(password)
        key = self._derive_key(password)
        f = Fernet(key)

        # メタデータ追加
        wrapped_data = {
            "version": 1,
            "encrypted_at": datetime.now().isoformat(),
            "data": data
        }

        json_bytes = json.dumps(wrapped_data, ensure_ascii=False, default=str).encode('utf-8')
        return f.encrypt(json_bytes)

    def decrypt_data(self, encrypted: bytes, password: str) -> Optional[dict]:
        """暗号化データを復号

        Args:
            encrypted: 暗号化されたバイト列
            password: 復号パスワード

        Returns:
            復号された辞書データ、パスワード不正の場合はNone
        """
        try:
            self._validate_password(password)
            key = self._derive_key(password)
            f = Fernet(key)
            decrypted = f.decrypt(encrypted)
            wrapped_data = json.loads(decrypted.decode('utf-8'))

            # バージョン1形式
            if isinstance(wrapped_data, dict) and "data" in wrapped_data:
                return wrapped_data["data"]
            # 旧形式（直接データ）
            return wrapped_data

        except InvalidToken:
            return None  # パスワード不正
        except Exception:
            return None  # その他のエラー

    def save_encrypted(self, data: dict, password: str) -> bool:
        """暗号化してファイル保存

        Args:
            data: 保存する辞書データ
            password: 暗号化パスワード

        Returns:
            保存成功の場合True
        """
        try:
            encrypted = self.encrypt_data(data, password)
            path = self._get_encrypted_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(encrypted)
            return True
        except Exception:
            return False

    def load_encrypted(self, password: str) -> Optional[dict]:
        """暗号化ファイルを読み込み・復号

        Args:
            password: 復号パスワード

        Returns:
            復号された辞書データ、失敗時はNone
        """
        path = self._get_encrypted_path()
        if not path.exists():
            return None

        try:
            encrypted = path.read_bytes()
            return self.decrypt_data(encrypted, password)
        except Exception:
            return None

    def has_encrypted_data(self) -> bool:
        """暗号化データファイルが存在するか確認

        Returns:
            ファイルが存在する場合True
        """
        return self._get_encrypted_path().exists()

    def delete_encrypted_data(self) -> bool:
        """暗号化データファイルを削除

        Returns:
            削除成功の場合True
        """
        path = self._get_encrypted_path()
        if path.exists():
            try:
                path.unlink()
                return True
            except Exception:
                return False
        return False

    def get_encrypted_info(self) -> Optional[dict]:
        """暗号化ファイルの情報を取得（パスワード不要）

        Returns:
            ファイル情報の辞書、存在しない場合はNone
        """
        path = self._get_encrypted_path()
        if not path.exists():
            return None

        stat = path.stat()
        return {
            "path": str(path),
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "exists": True
        }

    def verify_password(self, password: str) -> bool:
        """パスワードが正しいか検証

        Args:
            password: 検証するパスワード

        Returns:
            パスワードが正しい場合True
        """
        result = self.load_encrypted(password)
        return result is not None


def is_crypto_available() -> bool:
    """cryptographyライブラリが利用可能か確認

    Returns:
        利用可能な場合True
    """
    return CRYPTO_AVAILABLE
