"""
通用响应模型
提供统一的API响应格式，使用泛型支持任意类型的数据返回
"""

from pydantic import BaseModel
from typing import Generic, TypeVar, Optional


# 泛型类型变量，用于定义响应数据的类型
T = TypeVar('T') 


class ApiResponse(BaseModel, Generic[T]):
    """
    通用API响应模型（泛型类）
    """
    code: int = 200
    message: str = "success"
    data: Optional[T] = None


# ======================== 测试脚本 ========================
# python -m schemas.common_schema
if __name__ == "__main__":
    print("=" * 60)
    print("通用响应模型自测开始")
    print("=" * 60)

    # ---------- 测试1：默认值 ----------
    # 用例：不传 data 时 code=200, message="success", data=None
    resp = ApiResponse()
    assert resp.code == 200, f"默认 code 错误: {resp.code}"
    assert resp.message == "success", f"默认 message 错误: {resp.message}"
    assert resp.data is None, f"默认 data 错误: {resp.data}"
    print(f"[通过] 测试1 - 默认值: code={resp.code}, message='{resp.message}'")

    # ---------- 测试2：携带数据data是否序列化 ----------
    # 用例：传入 dict 数据，正确封装，code 为默认 200
    resp2 = ApiResponse(data={"id": 1, "name": "test"})
    assert resp2.data["id"] == 1, "数据封装错误"
    assert resp2.code == 200, "携带数据时 code 应为默认 200"
    print(f"[通过] 测试2 - 携带数据: data={resp2.data}")

    # ---------- 测试3：泛型类型参数是否序列化 ----------
    # 用例：ApiResponse[dict] 指定类型参数，model_dump 正确序列化
    resp3 = ApiResponse[dict](data={"key": "value"})
    assert resp3.data == {"key": "value"}, "泛型实例化数据错误"
    dumped = resp3.model_dump()
    assert dumped["code"] == 200 and dumped["data"]["key"] == "value", "序列化结果错误"
    print(f"[通过] 测试3 - 泛型序列化: {dumped}")

    # ---------- 测试4：自定义错误响应 ----------
    # 用例：错误响应格式（自定义 code 和 message）
    resp4 = ApiResponse(code=40001, message="用户不存在", data=None)
    assert resp4.code == 40001, f"自定义 code 错误: {resp4.code}"
    assert resp4.message == "用户不存在", f"自定义 message 错误: {resp4.message}"
    print(f"[通过] 测试4 - 自定义错误响应: code={resp4.code}, message='{resp4.message}'")

    print("=" * 60)
    print("通用响应模型自测全部通过（4/4）")
    print("=" * 60)