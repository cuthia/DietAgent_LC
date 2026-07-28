'''
自定义异常类
以及异常处理器
待扩展（更多功能的异常类和处理）
'''
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

# 使用 try/except 兼容直接运行本文件测试（python -m core.exception）
try:
    from .logger import logger
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from core.logger import logger


class BusinessException(Exception):
    """自定义业务异常基类"""
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message


# 常用业务异常快捷定义
class UserNotExistException(BusinessException):
    def __init__(self, message="用户不存在"):
        super().__init__(40001, message)


class AuthFailedException(BusinessException):
    def __init__(self, message="认证失败，请重新登录"):
        super().__init__(40101, message)

class PasswordException(BusinessException):
    def __init__(self, message="密码错误"):
        super().__init__(40002, message)



class ParamsException(BusinessException):
    def __init__(self, message="参数错误"):
        super().__init__(40000, message)


# 异常处理器

async def business_exception_handler(request: Request, exc: BusinessException) -> JSONResponse:
    """业务异常处理器"""
    logger.warning(f"业务异常: code={exc.code}, message={exc.message}")
    
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"code": exc.code, 
                 "message": exc.message,
                 "data": None}
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """参数校验异常处理器"""
    error_msg = "; ".join([f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in exc.errors()])
    logger.warning(f"参数校验失败: {error_msg}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"code": 40000, 
                 "message": f"参数错误: {error_msg}",
                 "data": None}
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """全局未知异常处理器"""
    logger.error(f"系统异常: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"code": 50000,
                 "message": "系统内部错误",
                 "data": None}
    )


# ======================== 文件内自测脚本 ========================
# python -m core.exception 
if __name__ == "__main__":
    print("=" * 60)
    print("异常模块自测开始")
    print("=" * 60)

    # ---------- 测试1：UserNotExistException ----------
    # 用例：默认 message 和 code 正确
    e1 = UserNotExistException()
    assert e1.code == 40001, f"错误码不符: {e1.code}"
    assert e1.message == "用户不存在", f"消息不符: {e1.message}"
    print(f"[通过] 测试1 - UserNotExistException: code={e1.code}, msg='{e1.message}'")

    # ---------- 测试2：AuthFailedException ----------
    # 用例：默认 message 和 code 正确，支持自定义消息
    e2 = AuthFailedException()
    assert e2.code == 40101, f"错误码不符: {e2.code}"
    assert e2.message == "认证失败，请重新登录", f"消息不符: {e2.message}"
    e2_custom = AuthFailedException("用户已被禁用")
    assert e2_custom.message == "用户已被禁用", f"自定义消息不符: {e2_custom.message}"
    print(f"[通过] 测试2 - AuthFailedException: 默认+自定义消息均正确")

    # ---------- 测试3：ParamsException ----------
    # 用例：默认 message 和 code 正确
    e3 = ParamsException()
    assert e3.code == 40000, f"错误码不符: {e3.code}"
    assert e3.message == "参数错误", f"消息不符: {e3.message}"
    print(f"[通过] 测试3 - ParamsException: code={e3.code}, msg='{e3.message}'")

    # ---------- 测试4：继承关系 ----------
    # 用例：所有业务异常继承 BusinessException，且是 Exception 子类
    assert issubclass(UserNotExistException, BusinessException), "继承关系错误"
    assert issubclass(AuthFailedException, BusinessException), "继承关系错误"
    assert issubclass(ParamsException, BusinessException), "继承关系错误"
    assert isinstance(e1, Exception), "不是 Exception 子类"
    print("[通过] 测试4 - 继承关系: 所有异常正确继承 BusinessException")

    # ---------- 测试5：异常统一捕获 ----------
    # 用例：PasswordException 能被 BusinessException 统一捕获
    try:
        raise PasswordException("测试异常")
    except BusinessException as e:
        assert e.code == 40002 and e.message == "测试异常"
    print("[通过] 测试5 - 异常捕获: BusinessException 统一捕获 PasswordException")

    # 用例：子类异常能被 BusinessException 统一捕获
    try:
        raise UserNotExistException("测试异常")
    except BusinessException as e:
        assert e.code == 40001 and e.message == "测试异常"
    print("[通过] 测试5 - 异常捕获: BusinessException 统一捕获子类异常")

    print("=" * 60)
    print("异常模块自测全部通过（5/5）")
    print("=" * 60)