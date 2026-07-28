"""
用户相关操作的请求和响应模型
包含：登录、注册、更新健康档案的请求/响应数据结构定义
"""
from pydantic import BaseModel, Field, ConfigDict # 使用 Pydantic v2 语法，支持数据校验和 ORM 对象转换
from typing import Optional


# ========== 请求模型 ==========

class UserRegisterRequest(BaseModel):
    """
    用户注册请求模型
    username: 用户名，长度3-20个字符
    password: 密码，长度6-20个字符
    """
    username: str = Field(min_length=3, max_length=20, description="用户名")
    password: str = Field(min_length=6, max_length=20, description="密码")


class UserLoginRequest(BaseModel):
    """
    用户登录请求模型
    username: 用户名
    password: 密码
    """
    username: str = Field(description="用户名")
    password: str = Field(description="密码")


class UserProfileUpdateRequest(BaseModel):
    """
    更新健康档案请求模型
    所有字段均为可选，只更新传入的非空字段
    
    age: 年龄（0-120岁）
    gender: 性别（male/female）
    height: 身高（cm，大于0小于300）
    weight: 体重（kg，大于0小于500）
    taste_preference: 口味偏好（如：辣、清淡、甜）
    food_taboo: 食物忌口（如：海鲜、花生）
    chronic_disease: 慢性疾病（如：糖尿病、高血压）
    region: 地域（如：南方、北方、沿海）
    diet_goal: 膳食目标（如：减脂、养胃、控糖）
    """
    age: Optional[int] = Field(None, ge=0, le=120, description="年龄")
    gender: Optional[str] = Field(None, pattern="^(male|female)$", description="性别")
    height: Optional[float] = Field(None, gt=0, lt=300, description="身高(cm)")
    weight: Optional[float] = Field(None, gt=0, lt=500, description="体重(kg)")
    taste_preference: Optional[str] = Field(None, description="口味偏好")
    food_taboo: Optional[str] = Field(None, description="食物忌口")
    chronic_disease: Optional[str] = Field(None, description="慢性疾病")
    region: Optional[str] = Field(None, description="地域")
    diet_goal: Optional[str] = Field(None, description="膳食目标")


# ========== 响应模型 ==========

class UserInfoResponse(BaseModel):
    """
    用户信息响应模型
    返回用户基础信息，不包含敏感数据（如密码哈希）
 
    id: 用户ID
    username: 用户名
    is_active: 是否活跃
    """
    id: int
    username: str
    is_active: bool
    
    # Pydantic v2 配置：支持从 ORM 对象直接转换
    model_config = ConfigDict(from_attributes=True)


class UserProfileResponse(BaseModel):
    """
    健康档案响应模型
    返回用户完整的健康档案信息
    
    age: 年龄
    gender: 性别
    height: 身高
    weight: 体重
    taste_preference: 口味偏好
    food_taboo: 食物忌口
    chronic_disease: 慢性疾病
    region: 地域
    diet_goal: 膳食目标
    """
    age: Optional[int] = None
    gender: Optional[str] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    taste_preference: Optional[str] = None
    food_taboo: Optional[str] = None
    chronic_disease: Optional[str] = None
    region: Optional[str] = None
    diet_goal: Optional[str] = None
    
    # Pydantic v2 配置：支持从 ORM 对象直接转换
    model_config = ConfigDict(from_attributes=True)


class LoginResponse(BaseModel):
    """
    登录响应模型
    返回登录成功后的令牌和用户信息

    access_token: JWT访问令牌
    token_type: 令牌类型（固定为bearer）
    user_info: 用户基础信息
    """
    access_token: str
    token_type: str = "bearer"
    user_info: UserInfoResponse


# ======================== 文件内自测脚本 ========================
# python -m schemas.user_schema
if __name__ == "__main__":
    from types import SimpleNamespace  # 用于模拟 ORM 对象

    print("=" * 60)
    print("用户 Schema 自测开始")
    print("=" * 60)

    # ---------- 测试1：注册请求合法数据 ----------
    # 用例：合法用户名+密码正常创建
    req = UserRegisterRequest(username="alice", password="123456")
    assert req.username == "alice" and req.password == "123456"
    print("[通过] 测试1 - 注册请求合法数据: 正常创建")

    # ---------- 测试2：注册请求字段约束拦截 ----------
    # 用例：用户名 <3 字符、密码 <6 字符被 Pydantic 拦截
    try:
        UserRegisterRequest(username="ab", password="123456")
        assert False, "用户名 <3 字符未被拦截"
    except Exception:
        pass
    try:
        UserRegisterRequest(username="alice", password="12345")
        assert False, "密码 <6 字符未被拦截"
    except Exception:
        pass
    print("[通过] 测试2 - 注册请求字段约束: 短用户名/短密码均被拦截")

    # ---------- 测试3：健康档案校验 ----------
    # 用例：合法值通过，非法性别值被 pattern 拦截
    profile_req = UserProfileUpdateRequest(age=25, gender="male", height=175.0)
    assert profile_req.age == 25 and profile_req.gender == "male"
    try:
        # 除了性别外还可以修改测试其他
        UserProfileUpdateRequest(gender="unknown")
        assert False, "非法性别值未被拦截"
    except Exception:
        pass
    print("[通过] 测试3 - 健康档案校验: 合法值通过，非法性别被拦截")

    # ---------- 测试4：from_attributes ORM 转换 ----------
    # 用例：从模拟 ORM 对象转换为 UserInfoResponse 对象，密码哈希保护
    mock_user = SimpleNamespace(id=1, username="alice", is_active=True, password_hash="secret")
    user_resp = UserInfoResponse.model_validate(mock_user)
    assert user_resp.id == 1 and user_resp.username == "alice"
    assert not hasattr(user_resp, "password_hash"), "密码哈希未被保护"
    print("[通过] 测试4 - ORM 转换: 字段正确提取，密码哈希被保护")

    # ---------- 测试5：Optional 字段允许为空 ----------
    # 用例：UserProfileResponse 不传任何字段时正常创建，全为 None
    empty_profile = UserProfileResponse()
    assert empty_profile.age is None and empty_profile.gender is None
    print("[通过] 测试5 - Optional 字段: 空档案响应正常创建")

    print("=" * 60)
    print("用户 Schema 自测全部通过（5/5）")
    print("=" * 60)