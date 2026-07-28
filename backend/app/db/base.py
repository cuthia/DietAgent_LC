'''
ORM基类定义
'''

from sqlalchemy.orm import DeclarativeBase, mapped_column
from sqlalchemy import DateTime
from datetime import UTC, datetime
from sqlalchemy.orm import Mapped

# ORM 模型基类，所有数据表都继承它

class Base(DeclarativeBase):
    created_at: Mapped[datetime] = mapped_column(
        DateTime, # 指定数据库层面字段类型为 DATETIME 类型
        default=lambda:datetime.now(UTC),
        comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda:datetime.now(UTC),
        onupdate=lambda:datetime.now(UTC), # 当模型实例更新时，自动更新数据条的该字段为当前时间
        comment="更新时间"
    )
