"""
FastAPI 应用入口模块

负责创建和配置FastAPI应用实例，包含：
1. 应用配置（标题、描述、版本）
2. 中间件注册（CORS）
3. 异常处理器注册
4. API路由注册
5. 启动事件（数据库初始化）
6. 健康检查接口
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

# 导入全局配置实例（从config_api模块）
from core.config_api import settings
from core.logger import logger
from core.exception import (
    BusinessException, business_exception_handler,
    validation_exception_handler, global_exception_handler
)
from api.routers import api_router
from db.session import init_db
from contextlib import asynccontextmanager

# 把启动逻辑封装成异步上下文管理器
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行（对应原来的 startup）
    await init_db()
    logger.info("数据库初始化完成")
    logger.info(f"服务启动成功，环境：{settings.env}，端口：{settings.server.port}")
    
    yield  # ← 这里分开：上面是启动，下面是关闭
    
    '''# 关闭时执行（对应原来的 shutdown，如果需要的话）
    logger.info("服务正在关闭...")
    # 可以在这里关闭数据库连接池、释放资源等
    # 例如await db.close()'''
    



def create_app() -> FastAPI:
    """
    创建并配置FastAPI应用（工厂函数模式）
    """
    # 创建FastAPI应用实例
    app = FastAPI(
        title="每日膳食搭配助手Agent",
        description="基于RAG+LangGraph的个性化膳食推荐AI Agent服务",
        version="1.0.0",
        # 开发环境启用文档，生产环境关闭
        docs_url="/docs" if settings.env == "dev" else None,
        redoc_url=None,
        lifespan=lifespan  # 启动事件：初始化数据库，项目启动时自动执行建表操作
    )

    # 配置跨域中间件（前端联调必备）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 开发环境全开，生产环境需配置具体域名
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册全局异常处理器
    # 业务异常：自定义业务逻辑异常
    app.add_exception_handler(BusinessException, business_exception_handler)
    # 参数校验异常
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    # 未知异常：兜底，防止泄露敏感信息
    app.add_exception_handler(Exception, global_exception_handler)

    # 注册API路由
    app.include_router(api_router)


    # TODO: 健康检查接口（用于容器化部署时的健康探测）
    @app.get("/health", summary="健康检查")
    async def health_check():
        """健康检查接口，返回服务状态"""
        return {"status": "ok", "env": settings.env}

    return app


    '''
    # 启动事件：初始化数据库，项目启动时自动执行建表操作
    @app.on_event("startup")
    async def startup_event():
        # 初始化数据库表结构
        await init_db()
        app_logger.info("数据库初始化完成")
        app_logger.info(f"服务启动成功，环境：{settings.env}，端口：{settings.server.port}")'''


# 创建全局应用实例（供Uvicorn启动使用）
app = create_app()


# 开发环境直接运行（生产环境使用uvicorn命令启动）
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.env == "dev"  # 开发环境启用热重载
    )