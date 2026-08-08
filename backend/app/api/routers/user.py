"""
用户模块路由 - 提供用户注册、登录、健康档案管理接口
路由前缀：/api/user
"""

from schemas.user_schema import LoginResponse, UserInfoResponse, UserProfileResponse

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from schemas.user_schema import (
    UserRegisterRequest, UserLoginRequest, UserProfileUpdateRequest,
    LoginResponse, UserInfoResponse, UserProfileResponse
)
from schemas.common_schema import ApiResponse
from db.crud.user_crud import create_user, get_user_by_username, update_user_profile
from core.security import verify_password, create_access_token
from core.exception import ParamsException, UserNotExistException
from api.dependencies import get_current_user
from db.models.user import User


# 创建路由实例，设置前缀和标签
router = APIRouter(prefix="/user", tags=["用户模块"])


@router.post("/register", response_model=ApiResponse[UserInfoResponse])
async def register(user_data: UserRegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    用户注册接口
    """
    # 检查用户名是否已被注册
    exist_user = await get_user_by_username(db, user_data.username)
    if exist_user:
        raise ParamsException("用户名已被注册")

    # 创建用户（密码会自动哈希）
    user = await create_user(db, user_data.username, user_data.password)
    
    # 返回用户信息（使用 Pydantic 模型转换，过滤敏感字段）
    return ApiResponse[UserInfoResponse](data=UserInfoResponse.model_validate(user))


@router.post("/login", response_model=ApiResponse[LoginResponse])
async def login(user_data: UserLoginRequest, db: AsyncSession = Depends(get_db)):
    """
    用户登录接口
    """
    # 根据用户名查询用户
    user = await get_user_by_username(db, user_data.username)
    if not user:
        raise UserNotExistException()
    
    # 验证密码（使用bcrypt哈希比对）
    if not verify_password(user_data.password, user.password_hash):
        raise ParamsException("密码错误")
    
    # 生成JWT访问令牌
    token = create_access_token(user.id)
    
    # 生成JWT访问令牌
    token = create_access_token(user.id)
    
    # 返回登录结果
    return ApiResponse[LoginResponse](data=LoginResponse(
        access_token=token,
        user_info=UserInfoResponse.model_validate(user)
    ))


@router.get("/profile", response_model=ApiResponse[UserProfileResponse])
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取当前用户健康档案
    依赖：get_current_user: 自动验证登录状态
    """
    from sqlalchemy import select
    from db.models.user import UserProfile

    # 显式查询健康档案（避免 relationship lazy-load 在同步函数中出错）
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    # 如果档案不存在，创建一条空档案并持久化，保证后续查询总能拿到实体
    if not profile:
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)

    # 返回健康档案信息
    return ApiResponse[UserProfileResponse](data=UserProfileResponse.model_validate(profile))


@router.put("/profile", response_model=ApiResponse[UserProfileResponse])
async def update_profile(
    profile_data: UserProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    更新用户健康档案
    
    字段：      
    age: 年龄（可选）
    gender: 性别（可选）
    height: 身高（可选）
    weight: 体重（可选）
    taste_preference: 口味偏好（可选）
    food_taboo: 食物忌口（可选）
    chronic_disease: 慢性疾病（可选）
    region: 地域（可选）
    diet_goal: 膳食目标（可选）
    
    依赖：get_current_user: 自动验证登录状态
    """
    # 将请求数据转换为字典，排除None值（只更新传入的字段）
    update_dict = profile_data.model_dump(exclude_none=True)
    
    # 更新健康档案
    updated = await update_user_profile(db, current_user.id, update_dict)
    
    # 返回更新后的健康档案
    return ApiResponse[UserProfileResponse](data=UserProfileResponse.model_validate(updated))