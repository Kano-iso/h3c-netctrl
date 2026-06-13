from cryptography.fernet import Fernet

from app.config import settings


def _get_fernet() -> Fernet:
    """获取 Fernet 实例，ENCRYPTION_KEY 必须已配置"""
    if not settings.ENCRYPTION_KEY:
        raise ValueError("ENCRYPTION_KEY 未配置，无法进行加密操作")
    return Fernet(settings.ENCRYPTION_KEY.encode())


def encrypt_password(plaintext: str) -> str:
    """加密密码，返回加密后的字符串"""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    """解密密码，返回明文字符串"""
    f = _get_fernet()
    return f.decrypt(encrypted.encode()).decode()


def generate_key() -> str:
    """生成新的 Fernet 密钥（用于初始化 .env 中的 ENCRYPTION_KEY）"""
    return Fernet.generate_key().decode()
