'''
配置处理器 - 统一加载 YAML 配置和环境变量
支持多环境配置、类型校验、敏感信息保护
'''

import re
from pydantic import BaseModel, Field, ValidationError
from pathlib import Path
import os
import logging
from functools import lru_cache
from typing import Optional, Dict, Any
import yaml

# 日志记录器对象，用于记录配置加载过程中的日志
logger = logging.getLogger(__name__)

# 环境变量占位符正则：可匹配可匹配：${MY_VAR}   ${MY_VAR:hello_world123}
ENV_PATTERN = re.compile(r'\$\{(\w+)(?::([^}]*))?\}')

# 以下Config配置类，属性值为配置的默认值，但优先级低于yaml

# server配置
class ServerConfig(BaseModel):
    host: str = Field(description="服务监听主机地址", default="0.0.0.0")
    port: int = Field(description="服务监听端口", default=8000)

# auth配置
class JWTConfig(BaseModel):
    secret_key: str = ""
    algorithm: str = "HS256" 
    expire_minutes: int = 1440

# logging配置
class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class DatabaseConfig(BaseModel):
    type: str = "sqlite"
    sqlite: Dict[str, Any] = Field(default_factory=dict)
    postgresql: Dict[str, Any] = Field(default_factory=dict)


class EmbeddingConfig(BaseModel):
    model: str = Field(description="向量嵌入模型名称", default="BAAI/bge-small-zh-v1.5")
    device: str = Field(description="运行设备(cpu/cuda)", default="cpu")
    max_length: int = Field(description="最大输入长度(token)", default=512)
    local_path: str = Field(description="本地模型路径(优先于model名加载)", default="")
    hf_endpoint: str = Field(description="HuggingFace镜像地址(解决国内访问问题)", default="https://hf-mirror.com")
    offline: bool = Field(description="是否离线模式(仅从本地加载)", default=False)


class ChromaConfig(BaseModel):
    persist_dir: str = Field(description="Chroma持久化目录", default="./data/chroma")


class MilvusConfig(BaseModel):
    host: str = Field(description="Milvus服务地址", default="localhost")
    port: int = Field(description="Milvus服务端口", default=19530)
    collection_name: str = Field(description="集合名称", default="diet_knowledge")


class VectorStoreConfig(BaseModel):
    type: str = Field(description="向量库类型(chroma/milvus)", default="chroma")
    chroma: ChromaConfig = ChromaConfig()
    milvus: MilvusConfig = MilvusConfig()


# LLM配置
class LLMConfig(BaseModel):
    type: str = Field(description="LLM类型(deepseek/qwen/openai)", default="deepseek")
    api_key: str = Field(description="API密钥(使用环境变量占位)", default="")
    base_url: str = Field(description="API基础URL", default="https://api.deepseek.com")
    model: str = Field(description="模型名称", default="deepseek-chat")
    temperature: float = Field(description="生成温度(0-1)", default=0.7)
    max_tokens: int = Field(description="最大token数量", default=4096)


# Redis配置
class RedisConfig(BaseModel):
    host: str = Field(description="Redis主机地址", default="localhost")
    port: int = Field(description="Redis端口", default=6379)
    db: int = Field(description="Redis数据库编号", default=0)
    password: str = Field(description="Redis密码", default="")

# 全局配置类，将各种配置类对象实例化，从而属性就赋入默认值
class Settings(BaseModel):
    env: str = "dev"
    server: ServerConfig = ServerConfig()
    jwt: JWTConfig = JWTConfig()
    logging: LoggingConfig = LoggingConfig()
    embedding: EmbeddingConfig = EmbeddingConfig()
    vector_store: VectorStoreConfig = VectorStoreConfig()
    database: DatabaseConfig = DatabaseConfig()
    llm: LLMConfig = LLMConfig()
    redis: RedisConfig = RedisConfig()
    

class ConfigHandler:
    """配置处理器核心类"""
    
    def __init__(self, config_dir: Optional[str] = None):
        """
        初始化配置目录和环境变量
        :param config_dir: 配置文件所在目录，默认值是当前文件所在目录的config子目录
        """

        self.config_dir = Path(config_dir) if config_dir else Path(__file__).parent / "config"
        self.env = os.getenv("ENV", "dev")
        # 单下划线开头的命名，私有属性，不应该在外部直接访问
        self._settings: Optional[Settings] = None # 全局配置对象


    # 私有方法
    def _resolve_env_vars(self, value: Any) -> Any: # 递归
        """
        递归解析环境变量占位符
        """

        if isinstance(value, str): # 如果value是字符串类型
            
            def replacer(match):  # match是正则匹配结果对象，包含匹配到的字符串和分组信息
                var_name = match.group(1) # 获取第一个捕获组，即环境变量名（如 ${MY_VAR} 中的 MY_VAR
                default = match.group(2)  # 获取第二个捕获组，即默认值（如 ${MY_VAR:default} 中的 default ）
                return os.getenv(var_name, default if default is not None else "") # 从系统环境变量中获取名字为var_name的值，没有则返回default，空则返回字符串
            
            #
            return ENV_PATTERN.sub(replacer, value) # 替换环境变量占位符为实际值。

        elif isinstance(value, dict): # 如果value是字典类型
            # 返回一个字典，键值对的值是递归调用_resolve_env_vars方法处理后的结果
            return {k: self._resolve_env_vars(v) for k, v in value.items()} # k是字典的键，v是字典的值，递归调用_resolve_env_vars方法，处理v中的环境变量占位符

        elif isinstance(value, list): # 如果value是列表类型
            return [self._resolve_env_vars(item) for item in value]
        
        return value


    # 私有方法
    def _load_yaml_file(self, file_path: Path) -> Dict[str, Any]:
        """加载 YAML 文件并处理环境变量"""

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {} # 解析yaml文件内容，变成字典格式
            return self._resolve_env_vars(config_data) # 递归解析环境变量占位符为对应的环境变量值或默认值

        except FileNotFoundError:
            logger.warning(f"配置文件不存在: {file_path}")
            return {}
        except yaml.YAMLError as e:
            logger.error(f"YAML 解析失败: {e}")
            raise ConfigLoadError(f"YAML 解析失败: {e}")

    # 私有方法
    def _merge_configs(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        递归合并配置字典
        
        parameter:
            base:Dict  基础配置
            override:Dict  dev/prod配置，相同或缺少则从base赋入，不同则override覆盖基本配置
        """
        result = base.copy()
        for key, value in override.items():
            # 如果对某个base中的key，在override和base中都存在，且都是字典类型，递归合并
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)

            # 若为其他情况，都直接将key键对应的值赋入override中的对应value
            # 也就是override会覆盖不同的基本配置
            else: 
                result[key] = value
        # 返回当前环境合成后的配置字典        
        return result
    
    


    def load(self) -> Settings:
        """加载配置：基础配置 + 环境特定配置"""
        # 1. 加载基础配置
        base_config = self._load_yaml_file(self.config_dir / "config.yaml")
        
        # 2. 加载环境特定配置（覆盖基础配置）
        env_config = self._load_yaml_file(self.config_dir / f"config.{self.env}.yaml")
        
        # 3. 合并配置（环境配置优先级更高，但基础配置会合并补齐缺失）
        merged_config = self._merge_configs(base_config, env_config)
        merged_config["env"] = self.env # 赋入env属性，标识这是哪个环境
        
        # 4. 使用 Pydantic 校验
        try:
            self._settings = Settings(**merged_config) # 将解析好的配置字典赋给全局配置类实例
            logger.info(f"配置加载成功，当前环境: {self.env}")
            return self._settings
        except ValidationError as e:
            logger.error(f"配置校验失败: {e}")
            raise ConfigValidationError(f"配置校验失败: {e}")

    @property # @property是一个装饰器，用于将方法转换为属性调用，调用同名属性时，会同时调用同名的方法
    def settings(self) -> Settings: 
        '''
        获取配置实例（懒加载）
        只有在第一次调用时才会加载配置，后续调用直接返回缓存的配置实例
        '''
        if self._settings is None:
            self._settings = self.load() # 加载配置
        return self._settings

class ConfigLoadError(Exception):
    """配置加载异常"""
    pass


class ConfigValidationError(Exception):
    """配置校验异常"""
    pass

# 全局配置处理器实例
config_handler = ConfigHandler()

# 全局配置实例（便捷访问）
@lru_cache()
def get_settings() -> Settings: # 通过get_settings函数获取处理器的方法属性settings（已被@property修饰），缓存结果
    return config_handler.settings


# ======================== 文件内自测脚本 ========================
# 运行方式：在 backend/app 目录下执行  python -m core.config_handler
# 覆盖：环境变量占位符解析、嵌套字典解析、配置递归合并、懒加载单例
if __name__ == "__main__":
    print("=" * 60)
    print("配置处理器自测开始")
    print("=" * 60)

    handler = ConfigHandler()

    # ---------- 测试1：环境变量占位符解析 ----------
    # 用例：${VAR:default} 有变量取变量值，无变量取默认值
    os.environ["TEST_VAR"] = "test_value"
    assert handler._resolve_env_vars("${TEST_VAR:fallback}") == "test_value", "环境变量解析错误"
    del os.environ["TEST_VAR"]
    assert handler._resolve_env_vars("${TEST_VAR:fallback}") == "fallback", "默认值解析错误"
    print("[通过] 测试1 - 环境变量占位符解析: 变量值/默认值均正确")

    # ---------- 测试2：嵌套字典环境变量解析 ----------
    # 用例：字典内字符串值递归解析，非字符串值原样保留
    nested = {"db": {"host": "${DB_HOST:localhost}", "port": 3306}}
    resolved = handler._resolve_env_vars(nested)
    assert resolved["db"]["host"] == "localhost", f"嵌套解析错误: {resolved}"
    assert resolved["db"]["port"] == 3306, f"非字符串值被错误处理: {resolved}"
    print("[通过] 测试2 - 嵌套字典环境变量解析: 递归正确")

    # ---------- 测试3：配置递归合并 ----------
    # 用例：同名字典字段递归合并（子字段各自取值），非字典字段 override 覆盖
    base = {"server": {"host": "0.0.0.0", "port": 8000}, "debug": True}
    override = {"server": {"port": 9000}}
    merged = handler._merge_configs(base, override)
    assert merged["server"]["host"] == "0.0.0.0", "递归合并失败: host 丢失"
    assert merged["server"]["port"] == 9000, "递归合并失败: port 未覆盖"
    assert merged["debug"] is True, "基础配置字段丢失"
    print("[通过] 测试3 - 配置递归合并: 子字段各自取值正确")

    # ---------- 测试4：配置加载 ----------
    # 用例：load() 返回 Settings 实例，核心属性可访问
    settings = handler.load()
    assert isinstance(settings, Settings), "load() 未返回 Settings 实例"
    assert hasattr(settings, "env") and hasattr(settings, "server") and hasattr(settings, "jwt")
    print(f"[通过] 测试4 - 配置加载: env={settings.env}, port={settings.server.port}")

    # ---------- 测试5：懒加载单例 ----------
    # 用例：@property 懒加载，多次访问返回同一实例
    s1 = handler.settings
    s2 = handler.settings
    assert s1 is s2, "懒加载失败: 两次获取返回不同实例"
    print("[通过] 测试5 - 懒加载单例: 多次获取返回同一实例")

    # ---------- 测试6：全局配置缓存 ----------
    # 用例：get_settings() 返回有效的全局配置
    global_settings = get_settings()
    assert isinstance(global_settings, Settings), "get_settings 未返回 Settings"
    assert global_settings.env in ("dev", "prod"), f"环境标识异常: {global_settings.env}"
    print(f"[通过] 测试6 - 全局配置缓存: env={global_settings.env}")

    print("=" * 60)
    print("配置处理器自测全部通过（6/6）")
    print("=" * 60)