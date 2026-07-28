"""
配置模块 - 统一对外暴露配置接口 
只关心最终的配置对象settings，不关心配置加载的细节
"""


# 导入需要的对象
from .config_handler import get_settings, Settings, config_handler 

# 全局配置实例 
settings = get_settings() 

# 定义模块的公共api，控制from app.core.config_api import * 时导入的内容
__all__ = ["settings", "get_settings", "Settings", "config_handler"] 