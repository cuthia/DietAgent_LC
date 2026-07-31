"""
Agent相关的数据Schema定义

使用Pydantic定义请求和响应的数据结构，用于API层的数据验证和序列化。

Schema列表：
- ChatRequest: 聊天请求
- ChatResponse: 聊天响应
- UserProfileUpdate: 用户档案更新请求
- DietPlan: 膳食方案结构
- ValidationResult: 校验结果
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ========== 请求Schema ==========

class ChatRequest(BaseModel):
    """
    聊天请求
    用户向Agent发送消息时的请求结构
    
    """
    user_id: int = Field(
        ..., 
        description="用户ID",
        examples=[1]
    )
    message: str = Field(
        ..., 
        description="用户消息",
        min_length=1,
        max_length=2000,
        examples=["我想制定一份减脂食谱"]
    )
    session_id: str = Field(
        default="default", 
        description="会话ID，用于区分不同的对话会话",
        examples=["default", "session_001"]
    )


class StreamChatRequest(ChatRequest):
    """
    流式聊天请求（继承自ChatRequest）
    
    用于请求SSE流式响应
    """
    pass


class UserProfileUpdate(BaseModel):
    """
    用户档案更新请求
    
    更新用户健康档案时的请求结构
    
    使用示例：
    ```json
    {
        "user_id": 1,
        "age": 28,
        "weight": 65,
        "chronic_disease": "糖尿病"
    }
    ```
    """
    user_id: int = Field(..., description="用户ID")
    age: Optional[int] = Field(None, description="年龄", ge=0, le=150)
    gender: Optional[str] = Field(None, description="性别", pattern="^(男|女|其他)$")
    height: Optional[float] = Field(None, description="身高(cm)", ge=0, le=300)
    weight: Optional[float] = Field(None, description="体重(kg)", ge=0, le=500)
    chronic_disease: Optional[str] = Field(None, description="慢性疾病，如：糖尿病、高血压")
    food_taboo: Optional[str] = Field(None, description="食物忌口，多个用逗号分隔")
    taste_preference: Optional[str] = Field(None, description="口味偏好")
    region: Optional[str] = Field(None, description="所在地域")
    diet_goal: Optional[str] = Field(None, description="膳食目标，如：减脂、增肌、控糖")


class ValidatePlanRequest(BaseModel):
    """
    校验膳食方案请求
    
    使用示例：
    ```json
    {
        "user_id": 1,
        "diet_plan": {...}
    }
    ```
    """
    user_id: int = Field(..., description="用户ID")
    diet_plan: Dict[str, Any] = Field(..., description="待校验的膳食方案")


# ========== 响应Schema ==========

class DietItem(BaseModel):
    """
    膳食单品
    
    膳食方案中单个食材/菜品的信息
    """
    name: str = Field(..., description="食材/菜品名称")
    amount: Optional[str] = Field(None, description="用量，如：100g、1个")
    calories: Optional[float] = Field(None, description="热量(千卡)")
    protein: Optional[float] = Field(None, description="蛋白质(克)")
    fat: Optional[float] = Field(None, description="脂肪(克)")
    carbs: Optional[float] = Field(None, description="碳水化合物(克)")
    tips: Optional[str] = Field(None, description="小贴士")


class DietMeal(BaseModel):
    """
    单餐膳食
    
    早餐/午餐/晚餐/加餐的详细信息
    """
    items: List[DietItem] = Field(default_factory=list, description="食材列表")
    total_calories: Optional[float] = Field(None, description="本餐总热量(千卡)")
    cooking_method: Optional[str] = Field(None, description="烹饪方式")
    tips: Optional[str] = Field(None, description="本餐建议")


class NutritionBalance(BaseModel):
    """
    营养均衡评估
    """
    protein: Optional[str] = Field(None, description="蛋白质评估")
    carbs: Optional[str] = Field(None, description="碳水化合物评估")
    fat: Optional[str] = Field(None, description="脂肪评估")
    fiber: Optional[str] = Field(None, description="膳食纤维评估")
    assessment: Optional[str] = Field(None, description="整体评估")


class DietPlan(BaseModel):
    """
    完整膳食方案
    
    Agent生成的膳食方案结构
    """
    breakfast: Optional[DietMeal] = Field(None, description="早餐")
    lunch: Optional[DietMeal] = Field(None, description="午餐")
    dinner: Optional[DietMeal] = Field(None, description="晚餐")
    snack: Optional[DietMeal] = Field(None, description="加餐")
    total_calories: Optional[float] = Field(None, description="全天总热量(千卡)")
    daily_target_calories: Optional[str] = Field(None, description="建议每日热量摄入")
    nutrition_balance: Optional[NutritionBalance] = Field(None, description="营养均衡评估")
    health_tips: List[str] = Field(default_factory=list, description="健康建议")
    disclaimer: Optional[str] = Field(None, description="免责声明")


class ChatResponse(BaseModel):
    """
    聊天响应
    
    Agent处理用户请求后的响应结构
    """
    success: bool = Field(..., description="是否成功")
    need_info: bool = Field(default=False, description="是否需要用户补充信息")
    diet_plan: Optional[DietPlan] = Field(None, description="膳食方案（如果有）")
    follow_up: Optional[str] = Field(None, description="追问消息（如果需要补充信息）")
    message: str = Field(..., description="回复消息")
    processing_time_ms: int = Field(default=0, description="处理耗时(毫秒)")


class StreamChatEvent(BaseModel):
    """
    流式聊天事件
    
    SSE流式响应中每个事件的结构
    """
    stage: str = Field(..., description="处理阶段")
    status: str = Field(..., description="状态：start/complete/error")
    message: str = Field(..., description="状态描述")
    data: Optional[ChatResponse] = Field(None, description="最终数据（仅在最后一个事件）")


class ValidationResult(BaseModel):
    """
    校验结果
    
    膳食方案校验的返回结果
    """
    passed: bool = Field(..., description="是否通过校验")
    forbidden_items: List[str] = Field(default_factory=list, description="禁忌食材列表")
    suggestions: List[str] = Field(default_factory=list, description="修正建议")
    details: Optional[Dict[str, Any]] = Field(None, description="详细信息")
    warning: Optional[str] = Field(None, description="警告信息")


class HistoryMessage(BaseModel):
    """
    历史消息
    
    对话历史中单条消息的结构
    """
    role: str = Field(..., description="角色：user/assistant/system")
    content: str = Field(..., description="消息内容")
    timestamp: Optional[float] = Field(None, description="时间戳")


class ChatHistoryResponse(BaseModel):
    """
    对话历史响应
    """
    messages: List[HistoryMessage] = Field(default_factory=list, description="消息列表")
    total: int = Field(default=0, description="消息总数")


class DietHistoryItem(BaseModel):
    """
    膳食历史项
    """
    plan: DietPlan = Field(..., description="膳食方案")
    saved_at: float = Field(..., description="保存时间戳")


class DietHistoryResponse(BaseModel):
    """
    膳食历史响应
    """
    plans: List[DietHistoryItem] = Field(default_factory=list, description="膳食方案历史")
    total: int = Field(default=0, description="方案总数")


# ========== 通用响应Schema ==========

class BaseResponse(BaseModel):
    """
    通用响应基础结构
    """
    success: bool = Field(default=True, description="是否成功")
    message: str = Field(default="操作成功", description="消息")
    data: Optional[Dict[str, Any]] = Field(None, description="数据")


class ErrorResponse(BaseModel):
    """
    错误响应
    """
    success: bool = Field(default=False)
    message: str = Field(..., description="错误消息")
    error_code: Optional[str] = Field(None, description="错误代码")
    details: Optional[Dict[str, Any]] = Field(None, description="详细信息")


# ========== 用户档案Schema ==========

class UserProfileResponse(BaseModel):
    """
    用户档案响应
    """
    user_id: int = Field(..., description="用户ID")
    age: Optional[int] = Field(None, description="年龄")
    gender: Optional[str] = Field(None, description="性别")
    height: Optional[float] = Field(None, description="身高(cm)")
    weight: Optional[float] = Field(None, description="体重(kg)")
    chronic_disease: Optional[str] = Field(None, description="慢性疾病")
    food_taboo: Optional[str] = Field(None, description="食物忌口")
    taste_preference: Optional[str] = Field(None, description="口味偏好")
    region: Optional[str] = Field(None, description="所在地域")
    diet_goal: Optional[str] = Field(None, description="膳食目标")


# ======================== 辅助函数 ========================

def chat_response_from_result(result: Dict[str, Any]) -> ChatResponse:
    """
    将Agent处理结果转换为ChatResponse
    
    参数：
        result: Agent处理结果字典
    
    返回：
        ChatResponse对象
    """
    diet_plan = None
    if result.get("diet_plan"):
        try:
            diet_plan = DietPlan(**result["diet_plan"])
        except Exception:
            pass
    
    return ChatResponse(
        success=result.get("success", False),
        need_info=result.get("need_info", False),
        diet_plan=diet_plan,
        follow_up=result.get("follow_up"),
        message=result.get("message", ""),
        processing_time_ms=result.get("processing_time_ms", 0)
    )


# ======================== 文件内自测脚本 ========================
if __name__ == "__main__":
    print("=" * 60)
    print("Agent Schema 自测开始")
    print("=" * 60)
    
    # 测试请求Schema
    print("\n[测试] ChatRequest验证...")
    try:
        req = ChatRequest(user_id=1, message="减脂食谱")
        print(f"[通过] user_id={req.user_id}, message={req.message}")
    except Exception as e:
        print(f"[失败] {e}")
    
    # 测试响应Schema
    print("\n[测试] ChatResponse验证...")
    try:
        resp = ChatResponse(
            success=True,
            need_info=False,
            message="您好，这是您的膳食方案",
            processing_time_ms=1500
        )
        print(f"[通过] success={resp.success}, time={resp.processing_time_ms}ms")
    except Exception as e:
        print(f"[失败] {e}")
    
    # 测试膳食方案
    print("\n[测试] DietPlan验证...")
    try:
        plan = DietPlan(
            total_calories=1800,
            health_tips=["多吃蔬菜", "适量运动"],
            breakfast=DietMeal(
                total_calories=400,
                items=[
                    DietItem(name="燕麦粥", calories=150),
                    DietItem(name="水煮蛋", calories=80)
                ]
            )
        )
        print(f"[通过] total_calories={plan.total_calories}, items={len(plan.breakfast.items)}")
    except Exception as e:
        print(f"[失败] {e}")
    
    # 测试校验结果
    print("\n[测试] ValidationResult验证...")
    try:
        vr = ValidationResult(
            passed=True,
            forbidden_items=[],
            suggestions=[]
        )
        print(f"[通过] passed={vr.passed}")
    except Exception as e:
        print(f"[失败] {e}")
    
    print("\n" + "=" * 60)
    print("Agent Schema 自测完成")
