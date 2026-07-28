# 待完成1：配置模块yaml
配置三个yaml文件，分别对应不同的环境：
- config_dev.yaml：开发环境配置
- config_prod.yaml：生产环境配置
- config_test.yaml：测试环境配置
- config.yaml：默认配置文件

## 1. rag相关配置



# 改进1： pytest 自动化测试框架
## 一、引入 pytest 自动化测试框架

### 1.1 什么是 pytest？

**pytest** 是 Python 最流行的测试框架，相比文件内的 `if __name__ == "__main__"` 自测脚本，它有这些优势：

| 特性 | 文件内自测 | pytest |
|------|-----------|--------|
| 测试发现 | 手动运行每个文件 | 自动发现 `test_*.py` 文件 |
| 测试报告 | 自己 print | 详细的通过/失败统计 |
| Fixture（夹具） | 没有 | 强大的依赖注入机制 |
| 异步支持 | 手动写事件循环 | `pytest-asyncio` 插件原生支持 |
| 覆盖率统计 | 没有 | `pytest-cov` 插件 |
| 参数化测试 | 手动循环 | `@pytest.mark.parametrize` |

### 1.2 安装依赖

首先安装测试相关的包：

```bash
pip install pytest pytest-asyncio pytest-cov httpx
```

- `pytest`：核心测试框架
- `pytest-asyncio`：支持异步测试（你的项目大量使用 async/await）
- `pytest-cov`：代码覆盖率统计
- `httpx`：异步 HTTP 客户端（用于 API 测试）

### 1.3 目录结构规划

在 `backend/app` 下创建 `tests/` 目录，结构如下：

```
backend/app/
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # pytest 全局配置和 fixture
│   ├── pytest.ini           # pytest 配置文件
│   ├── test_security.py     # 安全模块测试
│   ├── test_config_handler.py  # 配置处理器测试
│   ├── test_exception.py    # 异常模块测试
│   ├── test_schemas.py      # 数据模型测试
│   └── api/                 # API 测试
│       ├── __init__.py
│       └── test_user.py     # 用户模块 API 测试
```

### 1.4 配置 pytest

**创建 `backend/app/tests/pytest.ini`：**

```ini
[pytest]
# 测试文件命名规则：以 test_ 开头
python_files = test_*.py
# 测试类命名规则：以 Test 开头
python_classes = Test*
# 测试函数命名规则：以 test_ 开头
python_functions = test_*
# 异步测试模式：auto 自动识别 async 测试函数
asyncio_mode = auto
# 测试路径
testpaths = tests
```

### 1.5 迁移示例：security.py → test_security.py

我们以 `core/security.py` 为例，看看如何把文件内自测迁移为 pytest 用例。

**原来的写法（在 security.py 末尾）：**
```python
if __name__ == "__main__":
    pwd = "123456"
    hashed1 = hash_password(pwd)
    assert hashed1.startswith("$2b$"), "哈希格式错误"
    print("[通过] 测试1 - 密码哈希生成")
```

**pytest 写法（新建 test_security.py）：**

```python
"""
安全模块测试 - 测试密码哈希和JWT令牌功能
运行方式：在 backend/app 目录下执行 pytest tests/test_security.py -v
"""
import pytest
from datetime import timedelta

# 导入要测试的函数
from core.security import hash_password, verify_password, create_access_token, decode_access_token


# ---------- 密码哈希测试 ----------
class TestPasswordHashing:
    """密码哈希相关测试"""

    def test_hash_password_format(self):
        """测试1：密码哈希格式正确（$2b$ 开头）"""
        pwd = "123456"
        hashed = hash_password(pwd)
        assert hashed.startswith("$2b$"), f"哈希格式错误: {hashed}"

    def test_hash_password_random_salt(self):
        """测试2：相同密码两次哈希结果不同（随机盐生效）"""
        pwd = "123456"
        hashed1 = hash_password(pwd)
        hashed2 = hash_password(pwd)
        assert hashed1 != hashed2, "两次哈希结果相同，随机盐可能失效"

    def test_verify_password_correct(self):
        """测试3：正确密码验证返回 True"""
        pwd = "123456"
        hashed = hash_password(pwd)
        assert verify_password(pwd, hashed) is True

    def test_verify_password_wrong(self):
        """测试4：错误密码验证返回 False"""
        pwd = "123456"
        hashed = hash_password(pwd)
        assert verify_password("wrong_password", hashed) is False

    def test_long_password_truncation(self):
        """测试5：超长密码（>72字节）自动截断，不抛异常"""
        long_pwd = "a" * 100
        hashed = hash_password(long_pwd)
        assert hashed.startswith("$2b$")
        assert verify_password(long_pwd, hashed) is True


# ---------- JWT 令牌测试 ----------
class TestJWTTokens:
    """JWT令牌相关测试"""

    def test_create_access_token_format(self):
        """测试6：JWT令牌格式正确（三段式，含两个点）"""
        token = create_access_token(user_id=42)
        assert token and token.count(".") == 2, "JWT 格式错误"

    def test_decode_access_token_success(self):
        """测试7：合法令牌能正确解析出用户ID（回环验证）"""
        user_id = 42
        token = create_access_token(user_id)
        decoded_id = decode_access_token(token)
        assert decoded_id == user_id

    def test_decode_expired_token(self):
        """测试8：过期令牌解析返回 None"""
        expired_token = create_access_token(42, expires_delta=timedelta(seconds=-1))
        assert decode_access_token(expired_token) is None

    def test_decode_tampered_token(self):
        """测试9：篡改令牌解析返回 None"""
        token = create_access_token(42)
        tampered_token = token[:-5] + "XXXXX"
        assert decode_access_token(tampered_token) is None
```

### 1.6 运行测试

在 `backend/app` 目录下执行：

```bash
# 运行所有测试
pytest tests/ -v

# 只运行安全模块测试
pytest tests/test_security.py -v

# 运行并显示覆盖率
pytest tests/ --cov=core --cov=schemas -v
```

### 1.7 关键概念：Fixture（夹具）

Fixture 是 pytest 最强大的功能之一，相当于"测试前准备 + 测试后清理"的封装。

**简单例子：**
```python
import pytest

@pytest.fixture
def test_user():
    """创建一个测试用户，测试结束后自动清理"""
    # setup：测试前执行
    user = {"id": 1, "username": "test_user", "password": "123456"}
    print("\n[fixture] 创建测试用户")
    
    yield user  # 这里的 user 会传给测试函数
    
    # teardown：测试后执行
    print("\n[fixture] 清理测试用户")
    # 可以在这里删除测试数据、关闭连接等

def test_something(test_user):  # 直接把 fixture 名作为参数
    """测试函数直接使用 fixture 提供的数据"""
    assert test_user["username"] == "test_user"
```

---

## 二、API 自动化测试

### 2.1 两种测试方式对比

| 方式 | 适用场景 | 特点 |
|------|---------|------|
| `TestClient` | 同步接口 | 简单易用，基于 httpx |
| `httpx.AsyncClient` | 异步接口 / 流式响应 | 完全异步，更灵活 |

对于你的 FastAPI 项目，**推荐使用 `httpx.AsyncClient`**，因为你的接口大多是 `async` 的。

### 2.2 API 测试示例

创建 `backend/app/tests/api/test_user.py`：

```python
"""
用户模块 API 测试
运行方式：pytest tests/api/test_user.py -v
"""
import pytest
import httpx
from main import app  # 导入 FastAPI 应用实例


# ---------- 用户注册测试 ----------
class TestUserRegister:
    """用户注册接口测试"""

    @pytest.mark.asyncio
    async def test_register_success(self):
        """正向用例：注册成功"""
        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/user/register",
                json={"username": "test_new_user", "password": "123456"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0  # 假设成功 code 为 0
            assert data["data"]["username"] == "test_new_user"

    @pytest.mark.asyncio
    async def test_register_duplicate_username(self):
        """反向用例：用户名已存在"""
        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            # 先注册一次
            await client.post(
                "/api/user/register",
                json={"username": "test_dup", "password": "123456"}
            )
            # 再注册同样的用户名
            response = await client.post(
                "/api/user/register",
                json={"username": "test_dup", "password": "123456"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["code"] != 0  # 业务错误码非0

    @pytest.mark.asyncio
    async def test_register_empty_username(self):
        """反向用例：用户名为空"""
        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/user/register",
                json={"username": "", "password": "123456"}
            )
            # 参数校验失败，FastAPI 会返回 422
            assert response.status_code == 422


# ---------- 用户登录测试 ----------
class TestUserLogin:
    """用户登录接口测试"""

    @pytest.mark.asyncio
    async def test_login_success(self):
        """正向用例：登录成功"""
        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            # 先注册
            await client.post(
                "/api/user/register",
                json={"username": "test_login", "password": "123456"}
            )
            # 再登录
            response = await client.post(
                "/api/user/login",
                json={"username": "test_login", "password": "123456"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert "access_token" in data["data"]
            assert data["data"]["user_info"]["username"] == "test_login"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self):
        """反向用例：密码错误"""
        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            # 先注册
            await client.post(
                "/api/user/register",
                json={"username": "test_wrong_pwd", "password": "123456"}
            )
            # 用错误密码登录
            response = await client.post(
                "/api/user/login",
                json={"username": "test_wrong_pwd", "password": "wrong_pwd"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["code"] != 0
```

### 2.3 注意：导入路径问题

直接运行 pytest 时可能会遇到导入错误（找不到 `core`、`db` 等模块）。

**解决方案**：在 `tests/conftest.py` 中添加路径配置：

```python
"""
pytest 全局配置文件
- 配置测试环境
- 提供全局 fixture
"""
import sys
import os
from pathlib import Path

# 将 backend/app 目录添加到 Python 路径，解决导入问题
APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

# 也可以设置环境变量，标记当前为测试环境
os.environ["ENV"] = "test"
```

---

## 三、数据库测试隔离

### 3.1 为什么需要数据库测试隔离？

如果直接用开发数据库跑测试，会有这些问题：
- ❌ 测试数据污染开发数据（比如测试注册会留下一堆 test_xxx 用户）
- ❌ 测试之间互相影响（前一个测试改了数据，后一个测试结果不确定）
- ❌ 不能随便删表、改结构

### 3.2 三种隔离方案对比

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **专用测试数据库** | 完全隔离，最接近真实环境 | 需要额外的数据库实例 | ⭐⭐⭐⭐ |
| **事务回滚** | 速度快，不需要额外数据库 | 某些场景不适用（如DDL语句） | ⭐⭐⭐⭐⭐ |
| **SQLite 内存数据库** | 速度最快，零配置 | 和 MySQL 行为可能有差异 | ⭐⭐⭐ |

**推荐：事务回滚 + 测试数据库** 组合使用

### 3.3 方案一：事务回滚（推荐，实现简单）

核心思路：**每个测试用例开启一个事务，测试结束后回滚**，这样测试数据不会真正写入数据库。

在 `tests/conftest.py` 中添加：

```python
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# 导入你的模型基类和依赖
from db.base import Base
from db.session import get_db

# 测试数据库连接（可以用开发库的一个测试库，或者同库但用事务回滚）
TEST_DATABASE_URL = "mysql+aiomysql://root:yzt998666@localhost:3306/dietapp_test?charset=utf8"

# 创建测试用的数据库引擎
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,  # 测试时不打印 SQL，保持输出干净
    pool_size=5,
    max_overflow=10
)

# 测试用的会话工厂
TestAsyncSessionLocal = async_sessionmaker[AsyncSession](
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False
)


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """
    数据库会话 fixture - 事务回滚模式
    
    每个测试用例：
    1. 创建新的会话
    2. 开启事务
    3. yield 会话给测试用例使用
    4. 测试结束后回滚事务，数据不会保留
    """
    async with TestAsyncSessionLocal() as session:
        # 开启事务
        await session.begin()
        try:
            yield session  # 测试函数在这里执行
        finally:
            # 测试结束，回滚事务，所有改动都撤销
            await session.rollback()
            await session.close()


@pytest_asyncio.fixture(scope="function")
async def client_with_db(db_session):
    """
    带数据库会话的 API 测试客户端
    
    覆盖 FastAPI 的 get_db 依赖，让 API 使用测试会话（事务回滚的）
    """
    # 导入 FastAPI 应用
    from main import app
    
    # 覆盖依赖：把 get_db 替换成返回我们的测试会话
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    # 测试结束后清除覆盖
    app.dependency_overrides.clear()
```

**使用示例（修改 API 测试）：**

```python
class TestUserRegister:
    """用户注册接口测试 - 使用事务回滚"""

    @pytest.mark.asyncio
    async def test_register_success(self, client_with_db):
        """正向用例：注册成功（测试后自动回滚，不污染数据库）"""
        response = await client_with_db.post(
            "/api/user/register",
            json={"username": "test_user", "password": "123456"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        # 测试结束后，这个 test_user 会被自动回滚掉！
```

### 3.4 方案二：专用测试数据库

如果想要完全隔离，可以创建一个专门的测试数据库 `dietapp_test`。

**步骤：**

1. **在 MySQL 中创建测试数据库：**
```sql
CREATE DATABASE dietapp_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

2. **创建测试配置文件** `backend/app/core/config/config.test.yaml`：
```yaml
server:
  host: "0.0.0.0"
  port: 8000

jwt:
  secret_key: "test_secret_key_for_testing_only"
  algorithm: "HS256"
  expire_minutes: 1440

logging:
  level: "DEBUG"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

3. **在 conftest.py 中初始化测试数据库表：**
```python
@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_database():
    """
    会话级 fixture：在所有测试开始前创建表，测试结束后删除表
    
    scope="session" 表示整个测试会话只执行一次
    autouse=True 表示自动使用，不需要测试函数显式引用
    """
    # 创建所有表
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    print("\n[fixture] 测试数据库表创建完成")
    
    yield  # 所有测试在这里运行
    
    # 测试结束后删除所有表（可选，看你需不需要保留测试数据）
    # async with test_engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.drop_all)
    # print("\n[fixture] 测试数据库表已清理")
```

### 3.5 方案三：SQLite 内存数据库（最快）

如果只是测试逻辑，不需要 MySQL 特定功能，可以用 SQLite 内存数据库，速度飞快。

```python
# 使用 SQLite 内存数据库（注意：必须用 aiosqlite 驱动）
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
```

**⚠️ 注意事项：**
- SQLite 和 MySQL 语法有差异（比如自增、字段类型等）
- 你的模型如果用了 MySQL 特定功能，可能在 SQLite 下跑不通
- 适合单元测试，集成测试还是建议用 MySQL

---

## 四、完整实施步骤（建议顺序）

### 第一步：搭建基础测试框架
1. 安装依赖：`pip install pytest pytest-asyncio pytest-cov httpx`
2. 创建 `tests/` 目录和 `pytest.ini`
3. 创建 `conftest.py`，配置路径和基础 fixture
4. 先迁移 1-2 个简单的模块测试（比如 `test_exception.py`）

### 第二步：迁移核心模块测试
把 5 个文件内自测脚本都迁移到 pytest：
- `test_security.py`
- `test_config_handler.py`
- `test_exception.py`
- `test_schemas.py`

### 第三步：实现数据库测试隔离
1. 创建测试数据库 `dietapp_test`
2. 在 `conftest.py` 中添加 `db_session` fixture（事务回滚模式）
3. 添加 `setup_test_database` fixture（建表）

### 第四步：编写 API 测试
1. 创建 `tests/api/` 目录
2. 编写用户模块 API 测试（注册、登录、档案）
3. 覆盖正向用例和反向用例

### 第五步：完善和优化
1. 添加更多测试用例（边界条件、异常场景）
2. 配置覆盖率统计
3. 添加 CI/CD 集成（如果需要）

---

## 五、常见问题和注意事项

### Q1: 测试时导入错误怎么办？
**A:** 确保 `conftest.py` 中正确添加了 Python 路径，或者在运行测试前 `cd backend/app`。

### Q2: async fixture 报错怎么办？
**A:** 记住：**异步 fixture 必须用 `@pytest_asyncio.fixture`，不能用 `@pytest.fixture`**（这是经验总结里的坑！）。

### Q3: 测试数据怎么准备？
**A:** 用 fixture！比如创建一个 `test_user` fixture，自动注册一个测试用户，测试函数直接用。

### Q4: 测试速度慢怎么办？
**A:** 
- 用事务回滚代替删表重建
- 把公共数据的 fixture scope 设为 `module` 或 `session`
- SQLite 内存数据库最快

---

## 总结

| 任务 | 核心工具/概念 | 难度 |
|------|-------------|------|
| pytest 迁移 | `pytest` + 测试函数 + `assert` | ⭐⭐ |
| API 自动化测试 | `httpx.AsyncClient` + FastAPI 依赖覆盖 | ⭐⭐⭐ |
| 数据库测试隔离 | `pytest_asyncio.fixture` + 事务回滚 | ⭐⭐⭐⭐ |

你想先从哪一步开始？我可以帮你：
1. 直接创建测试目录和基础配置文件
2. 帮你把某个模块的自测脚本迁移为 pytest 用例
3. 先把数据库测试隔离的基础搭起来

告诉我你想先做哪个，我们一步步来！