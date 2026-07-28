"""
安全模块 - 提供密码加密和JWT令牌管理功能

功能说明：
密码哈希加密：使用bcrypt算法对用户密码进行加密存储
JWT令牌：生成、解析和验证JSON Web Token，用于用户身份认证

依赖：
- bcrypt：密码哈希库
- python-jose：JWT令牌处理库
- config_api：配置模块，提供JWT密钥和过期时间配置
"""

from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import JWTError, jwt

# 导入全局配置实例，获取JWT相关配置
# 使用 try/except 兼容直接运行本文件测试（python -m core.security）
try:
    from .config_api import settings
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from core.config_api import settings


def hash_password(password: str) -> str:
    """
    对用户密码进行哈希加密

    参数：password: 原始密码字符串
    返回：加密后的密码哈希字符串（标准 bcrypt 格式 $2b$...）
    """
    # bcrypt 要求密码为 bytes 类型，且不超过 72 字节
    # 手动截断到 72 字节，避免新版 bcrypt 抛出 ValueError
    pwd_bytes = password.encode("utf-8")[:72]
    # 生成随机盐值并计算哈希
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    # 返回字符串形式（数据库存储为字符串）
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证用户输入的密码与存储的哈希密码是否匹配

    参数：
        plain_password: 用户输入的原始密码
        hashed_password: 数据库中存储的哈希密码

    返回：bool: 匹配返回True，不匹配返回False
    """
    # 解码，与 hash_password 保持一致的截断逻辑
    pwd_bytes = plain_password.encode("utf-8")[:72]
    hashed_bytes = hashed_password.encode("utf-8")
    # checkpw 会自动从 hashed_bytes 中提取盐值进行比对
    return bcrypt.checkpw(pwd_bytes, hashed_bytes)


def create_access_token(user_id: int, expires_delta: Optional[timedelta] = None) -> str:
    """
    生成JWT访问令牌
    
    参数：
        user_id: 用户ID，将作为令牌的subject存储
        expires_delta: 令牌过期时间间隔，可选，默认使用配置中的过期时间
    
    返回：str: 编码后的JWT令牌字符串
    令牌结构：
        {
            "sub": "user_id",  # 用户ID
            "exp": timestamp   # 过期时间戳（UTC）
        }
    """
    # 创建令牌负载（payload），包含用户ID作为sub字段
    to_encode = {"sub": str(user_id)}
    
    # 设置令牌过期时间:payload的exp字段
    if expires_delta:
        # 使用传入的过期时间
        expire = datetime.utcnow() + expires_delta
    else:
        # 使用配置文件中的默认过期时间（从config_api获取）
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt.expire_minutes)
    
    # 将过期时间添加到负载中
    to_encode.update({"exp": expire})
    
    # 使用HS256算法和密钥对负载进行编码，生成JWT令牌
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.jwt.secret_key, 
        algorithm=settings.jwt.algorithm
    )
    
    return encoded_jwt


def decode_access_token(token: str) -> Optional[int]:
    """
    解析JWT令牌，提取用户ID
    
    参数：token: JWT令牌字符串
    
    返回：Optional[int]: 成功解析返回用户ID，失败返回None
    
    失败场景：
        - 令牌格式错误
        - 签名验证失败（密钥不匹配）
        - 令牌已过期
        - payload中缺少sub字段
    """
    try:
        # 使用密钥和算法解码令牌，获取payload
        payload = jwt.decode(
            token, 
            settings.jwt.secret_key, 
            algorithms=[settings.jwt.algorithm]
        )
        
        # 从payload中获取用户ID（subject）
        user_id: str = payload.get("sub")
        
        # 如果用户ID为空，返回None
        if user_id is None:
            return None
        
        # 将用户ID转换为整数并返回
        return int(user_id)
    
    except JWTError:
        # 捕获JWT解码异常（签名错误、过期等），返回None
        return None


# ======================== 文件内自测脚本 ========================
# python -m core.security
if __name__ == "__main__":
    print("=" * 60)
    print("安全模块自测开始")
    print("=" * 60)

    # ---------- 测试1：密码哈希生成 ----------
    # 用例：验证 hash_password 返回 $2b$ 开头，且相同密码两次哈希结果不同（随机盐）
    pwd = "123456"
    hashed1 = hash_password(pwd)
    hashed2 = hash_password(pwd)
    assert hashed1.startswith("$2b$"), f"哈希格式错误: {hashed1}"
    assert hashed1 != hashed2, "两次哈希结果相同，随机盐可能失效"
    print(f"[通过] 测试1 - 密码哈希生成（随机盐生效）: {hashed1[:25]}...")

    # ---------- 测试2：密码正确验证 ----------
    # 用例：verify_password 对正确明文返回 True
    assert verify_password(pwd, hashed1) is True, "正确密码验证失败"
    print("[通过] 测试2 - 密码正确验证: True")

    # ---------- 测试3：密码错误验证 ----------
    # 用例：verify_password 对错误明文返回 False
    assert verify_password("wrong_password", hashed1) is False, "错误密码验证未拦截"
    print("[通过] 测试3 - 密码错误验证: False")

    # ---------- 测试4：超长密码 72 字节截断 ----------
    # 用例：超过 72 字节的密码自动截断，不抛 ValueError
    long_pwd = "a" * 100
    long_hashed = hash_password(long_pwd)
    assert long_hashed.startswith("$2b$"), "超长密码哈希失败"
    assert verify_password(long_pwd, long_hashed) is True, "超长密码验证失败"
    print("[通过] 测试4 - 超长密码 72 字节截断: 正常哈希且验证通过")

    # ---------- 测试5：JWT 令牌生成 ----------
    # 用例：create_access_token 返回三段式 JWT（含两个"."）
    user_id = 42
    token = create_access_token(user_id)
    assert token and token.count(".") == 2, "JWT 格式错误（非三段式）"
    print(f"[通过] 测试5 - JWT 令牌生成: {token[:25]}...")

    # ---------- 测试6：JWT 令牌解析（回环验证） ----------
    # 用例：decode_access_token 从合法 token 提取原始 user_id
    decoded_id = decode_access_token(token)
    assert decoded_id == user_id, f"JWT 解析不符: 期望 {user_id}, 实际 {decoded_id}"
    print(f"[通过] 测试6 - JWT 解析回环: user_id={decoded_id}")

    # ---------- 测试7：JWT 过期令牌拦截 ----------
    # 用例：过期 token（expires_delta 为负）解析返回 None
    expired_token = create_access_token(user_id, expires_delta=timedelta(seconds=-1))
    assert decode_access_token(expired_token) is None, "过期令牌未被拦截"
    print("[通过] 测试7 - 过期令牌拦截: 返回 None")

    # ---------- 测试8：JWT 篡改令牌拦截 ----------
    # 用例：篡改 token 尾部签名后解析返回 None（签名校验失败）
    tampered_token = token[:-5] + "XXXXX"
    assert decode_access_token(tampered_token) is None, "篡改令牌未被拦截"
    print("[通过] 测试8 - 篡改令牌拦截: 返回 None")

    print("=" * 60)
    print("安全模块自测全部通过（8/8）")
    print("=" * 60)