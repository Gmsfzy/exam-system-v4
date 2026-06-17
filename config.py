import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY')
    # SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    # SQLALCHEMY_TRACK_MODIFICATIONS = False
    # DOUBAN_API_KEY = os.getenv('DOUBAN_API_KEY')
    # DOUBAN_API_URL = os.getenv('DOUBAN_API_URL')
    # 改用 SQLite 数据库
    SQLALCHEMY_DATABASE_URI = 'sqlite:///exam_system.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # SQLite 锁超时时间（秒），避免 AI 调用期间数据库锁报错
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"timeout": 30}}
    # 火山引擎豆包配置
    DOUBAN_API_KEY = os.getenv('DOUBAN_API_KEY', '')
    DOUBAN_API_URL = os.getenv('DOUBAN_API_URL')  # 读取正确接口地址
    DOUBAN_ENDPOINT_ID = os.getenv('DOUBAN_ENDPOINT_ID')  # 新增：接入点ID
