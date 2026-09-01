import os

from dotenv import load_dotenv
from sqlmodel import Session, create_engine

load_dotenv()


def get_database_url():
    db_type = os.getenv("DB_TYPE", "sqlite")
    if db_type == "sqlite":
        return "sqlite:///:memory:"
    return f"mariadb+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"


engine = create_engine(get_database_url())


def get_session():
    with Session(engine) as session:
        yield session
