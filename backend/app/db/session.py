'''
异步数据库会话工厂
'''

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.ext.asyncio.session import AsyncSession
from db.base import Base
import os


# .1 数据库连接
ASYNC_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+aiomysql://root:yzt998666@localhost:3306/dietapp?charset=utf8",
)

# 2. 创建异步数据库引擎
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "0") == "1",  # 生产环境默认关闭 SQL 日志
    pool_size=10,     # 连接池常驻连接数量
    max_overflow=20   # 流量高峰额外扩容连接上限
)

# 3. 创建异步会话工厂
AsyncSessionLocal = async_sessionmaker[AsyncSession](
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False  # 提交后不自动过期，确保数据一致性
)

# 4. 异步创建所有数据表函数
async def init_db():
    # begin() 开启事务上下文，自动提交/回滚
    async with async_engine.begin() as conn:
        # run_sync：在异步连接中执行同步DDL建表语句
        await conn.run_sync(Base.metadata.create_all)

# 8. 创建获取数据库会话的依赖方法
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session # 返回数据库会话，给路由处理函数
            await session.commit() # 无异常，提交事务
        except Exception:
            await session.rollback() # 有异常则回滚
            raise
        finally:
            await session.close() # 关闭会话
