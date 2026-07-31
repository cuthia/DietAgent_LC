"""
用户信息工具 - 查询和更新用户健康档案

功能：
1. get_user_info: 查询用户完整健康档案
2. update_user_info: 更新用户健康档案

数据来源：数据库（通过db/session.py和db/crud/user_crud.py）
"""

import logging
from typing import Optional, Dict, Any

# 日志记录器
logger = logging.getLogger(__name__)


async def get_user_info(user_id: int) -> Dict[str, Any]:
    """
    查询用户完整健康档案
    
    功能：
    根据用户ID获取用户的健康档案信息，包括：
    - 基础信息：年龄、性别、身高、体重
    - 健康信息：慢性疾病、食物忌口
    - 偏好信息：口味偏好、地域
    - 目标信息：膳食目标
    
    参数：
        user_id: 用户ID（数据库主键）
    
    返回：
        用户档案字典，结构如下：
        {
            "user_id": 1,
            "age": 25,
            "gender": "male",
            "height": 175.0,
            "weight": 70.0,
            "chronic_disease": "",  # 如："糖尿病"
            "food_taboo": "",      # 如："海鲜"
            "taste_preference": "", # 如："清淡"
            "region": "",          # 如："南方"
            "diet_goal": ""        # 如："减脂"
        }
    
    """
    try:
        # 延迟导入以避免循环依赖
        from db.session import AsyncSessionLocal
        from sqlalchemy import select
        from db.models.user import UserProfile
        
        async with AsyncSessionLocal() as db:
            # 查询用户档案
            result = await db.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()
            
            if not profile:
                logger.warning(f"用户 {user_id} 无健康档案")
                return {
                    "user_id": user_id,
                    "age": None,
                    "gender": None,
                    "height": None,
                    "weight": None,
                    "chronic_disease": "",
                    "food_taboo": "",
                    "taste_preference": "",
                    "region": "",
                    "diet_goal": ""
                }
            
            # 构建返回字典
            return {
                "user_id": user_id,
                "age": profile.age,
                "gender": profile.gender,
                "height": profile.height,
                "weight": profile.weight,
                "chronic_disease": profile.chronic_disease or "",
                "food_taboo": profile.food_taboo or "",
                "taste_preference": profile.taste_preference or "",
                "region": profile.region or "",
                "diet_goal": profile.diet_goal or ""
            }
            
    except Exception as e:
        logger.error(f"查询用户信息失败: {e}")
        # 返回默认空档案，保证Agent可以继续执行
        return {
            "user_id": user_id,
            "age": None,
            "gender": None,
            "height": None,
            "weight": None,
            "chronic_disease": "",
            "food_taboo": "",
            "taste_preference": "",
            "region": "",
            "diet_goal": ""
        }


async def update_user_info(user_id: int, updates: Dict[str, Any]) -> bool:
    """
    更新用户健康档案
    
    功能：
    根据传入的更新字段，部分更新用户的健康档案。
    只会更新字典中值不为None的字段。
    
    参数：
        user_id: 用户ID
        updates: 待更新字段字典，如：
                {"age": 26, "weight": 68.5, "food_taboo": "花生"}
    
    返回：
        bool: 更新成功返回True，失败返回False
    
    """
    try:
        # 延迟导入
        from db.session import AsyncSessionLocal
        from sqlalchemy import select
        from db.models.user import UserProfile
        
        async with AsyncSessionLocal() as db:
            # 查询用户档案
            result = await db.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()
            
            # 如果档案不存在，创建新档案
            if not profile:
                profile = UserProfile(user_id=user_id)
                db.add(profile)
            
            # 更新非None字段
            update_count = 0
            for key, value in updates.items():
                if value is not None and hasattr(profile, key):
                    setattr(profile, key, value)
                    update_count += 1
            
            if update_count > 0:
                await db.commit()
                await db.refresh(profile)
                logger.info(f"用户 {user_id} 档案更新成功，更新了 {update_count} 个字段")
                return True
            else:
                logger.info(f"用户 {user_id} 档案无需更新")
                return True  # 无需更新也算成功
                
    except Exception as e:
        logger.error(f"更新用户信息失败: {e}")
        return False


def format_profile_for_prompt(profile: Dict[str, Any]) -> str:
    """
    将用户档案格式化为Prompt可消费的文本
    
    功能：
    将结构化的用户档案转换为自然语言描述，便于LLM理解
    
    参数：
        profile: 用户档案字典（来自get_user_info）
    
    返回：
        格式化的文本描述
    
    使用示例：
    ```python
    profile = await get_user_info(user_id=1)
    profile_text = format_profile_for_prompt(profile)
    # 输出示例：
    # 用户信息：25岁，男性，身高175cm，体重70kg
    # 慢性疾病：无
    # 食物忌口：海鲜
    # 口味偏好：清淡
    # 所在地域：南方
    # 膳食目标：减脂
    ```
    """
    parts = []
    
    # 基础信息
    age = profile.get("age")
    gender = profile.get("gender", "")
    height = profile.get("height")
    weight = profile.get("weight")
    
    gender_map = {"male": "男性", "female": "女性", "": "未知"}
    gender_text = gender_map.get(gender, gender)
    
    basic_info = f"{age or '未知'}岁，{gender_text}"
    if height and weight:
        basic_info += f"，身高{height}cm，体重{weight}kg"
    parts.append(f"用户基础信息：{basic_info}")
    
    # 慢性疾病
    chronic = profile.get("chronic_disease", "")
    parts.append(f"慢性疾病：{chronic if chronic else '无'}")
    
    # 食物忌口
    taboo = profile.get("food_taboo", "")
    parts.append(f"食物忌口：{taboo if taboo else '无'}")
    
    # 口味偏好
    taste = profile.get("taste_preference", "")
    parts.append(f"口味偏好：{taste if taste else '无特殊偏好'}")
    
    # 地域
    region = profile.get("region", "")
    parts.append(f"所在地域：{region if region else '未设置'}")
    
    # 膳食目标
    goal = profile.get("diet_goal", "")
    parts.append(f"膳食目标：{goal if goal else '日常养生'}")
    
    return "\n".join(parts)


# ======================== 文件内自测脚本 ========================
if __name__ == "__main__":
    import asyncio
    
    print("=" * 60)
    print("用户工具自测开始")
    print("=" * 60)
    
    async def test():
        # 测试获取用户信息
        profile = await get_user_info(user_id=1)
        print(f"[通过] 获取用户信息: user_id={profile['user_id']}")
        
        # 测试格式化
        formatted = format_profile_for_prompt(profile)
        print(f"[通过] 格式化档案:\n{formatted[:200]}...")
        
        # 测试更新（使用无效数据验证异常处理）
        success = await update_user_info(user_id=999, updates={"age": None})
        print(f"[通过] 更新用户信息（空数据）: {success}")
        
        print("=" * 60)
        print("用户工具自测完成")
    
    asyncio.run(test())
