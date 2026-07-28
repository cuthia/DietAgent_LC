"""
依赖注入模块 - 提供认证相关的依赖函数
实现get_current_user 依赖，自动验证用户身份
获取OAuth2令牌，解码JWT令牌，通过中段payload中的id到数据库查询用户信息，返回用户对象
"""

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from core.security import decode_access_token
from core.exception import AuthFailedException
from db.crud.user_crud import get_user_by_id
from db.models.user import User


# OAuth2 密码Bearer令牌方案
# tokenUrl: 前端获取令牌的接口地址
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/user/login")

# 作为依赖项，提供验证用户身份的功能
async def get_current_user(
    token: str = Depends(oauth2_scheme), # OAuth2令牌（自动从请求头获取）
    db: AsyncSession = Depends(get_db) # 获取数据库会话
) -> User:
    """
    获取当前登录用户（依赖注入函数）
    """
    # 解码JWT令牌，提取用户ID
    user_id = decode_access_token(token)
    if not user_id:
        # 令牌无效或已过期
        raise AuthFailedException()

    # 根据用户ID查询数据库，获取用户对象
    user = await get_user_by_id(db, user_id)
    if not user:
        # 用户不存在
        raise AuthFailedException("用户不存在")
    
    # 验证用户是否活跃
    if not user.is_active:
        # 用户已被禁用
        raise AuthFailedException("用户已被禁用")
    
    # 返回用户对象，供接口函数使用
    return user

