"""
用户数据访问，对用户表和健康档案表的数据库操作：
1. 用户查询（按用户名、按ID）
2. 用户创建（含密码哈希）
3. 健康档案更新
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.models.user import User, UserProfile
from core.security import hash_password


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    """
    根据用户名查询用户
    """
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    """
    根据用户ID查询用户
    """
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, username: str, password: str) -> User:
    """
    创建新用户，同时初始化空的健康档案
    """
    hashed_pwd = hash_password(password) # 对密码进行bcrypt哈希加密

    # 创建User对象
    db_user = User(username=username, password_hash=hashed_pwd)
    db.add(db_user)

    # flush() 获取自动生成的用户ID
    await db.flush()
    # 创建关联的空健康档案
    db_profile = UserProfile(user_id=db_user.id) # 实例化的User对象自动为主键id生成了一个值
    db.add(db_profile)

    # 提交事务
    await db.commit()

    # 刷新用户对象，确保包含最新的数据库数据
    await db.refresh(db_user)

    return db_user


async def update_user_profile(db: AsyncSession, user_id: int, profile_data: dict) -> UserProfile:
    """
    更新用户健康档案
    profile_data: 需更新数据的字典
    """
    # 查询用户的健康档案
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = result.scalar_one_or_none()

    # 如果档案不存在，创建新档案
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.add(profile)

    # 遍历更新数据，只设置非None的值
    for key, value in profile_data.items():
        if value is not None:
            setattr(profile, key, value)

    # 提交事务
    await db.commit()

    # 刷新档案对象
    await db.refresh(profile)

    return profile
