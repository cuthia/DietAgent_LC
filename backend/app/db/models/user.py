'''
User: 用户账号表
UserProfile: 用户健康档案表
关联关系：用户一对一关联健康档案
'''
from sqlalchemy import Column, Integer, String, Boolean, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import Optional
from db.base import Base
from sqlalchemy.orm import Mapped, mapped_column



class User(Base):
    """用户账号表，用户名，密码，邮箱，密码哈希，是否在线"""
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True, comment="用户ID")
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment="用户名")
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=True, comment="邮箱")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment="加密密码")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否激活")
    
    # 一对一关联健康档案
    profile = relationship("UserProfile", 
                            back_populates="user", 
                            uselist=False, 
                            cascade="all, delete-orphan") # 级联增删改


class UserProfile(Base):
    """用户健康档案表"""
    __tablename__ = "user_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), unique=True, nullable=False, comment="关联用户ID")

    # 基础身体信息（年龄，性别，身高，体重）——注册时为空，用户后续填写，故允许为 null
    age: Mapped[Optional[int]] = mapped_column(nullable=True, comment="年龄")
    gender: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, comment="性别：male/female")
    height: Mapped[Optional[float]] = mapped_column(nullable=True, comment="身高(cm)")
    weight: Mapped[Optional[float]] = mapped_column(nullable=True, comment="体重(kg)")

    # 饮食相关（口味，食物忌口，慢性疾病，所在城市）
    taste_preference: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="口味偏好：清淡/微辣/重辣/偏甜等")
    food_taboo: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="食物忌口/过敏，逗号分隔")
    chronic_disease: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="慢性疾病，逗号分隔：糖尿病/高血压/痛风等")
    region: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="所在城市/地域")

    # 其他（饮食目标）
    diet_goal: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="饮食目标：减脂/增肌/控糖/养生等")

    user = relationship("User", back_populates="profile")