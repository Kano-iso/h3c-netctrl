import os
import pytest
from fastapi.testclient import TestClient

# 设置测试环境变量
os.environ["ENCRYPTION_KEY"] = "BRPOu1O4FIvcdwijI1yf0quviQjeSr0V1Zfw2CRwgRQ="
os.environ["DB_PATH"] = "/tmp/test_h3c.db"

from app.main import app
from app.database import Base, engine, SessionLocal


@pytest.fixture(autouse=True)
def setup_db():
    """每个测试前重建数据库表"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    """FastAPI 测试客户端"""
    return TestClient(app)


@pytest.fixture
def db():
    """数据库 session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
