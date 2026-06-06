from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String, unique=True, nullable=True, index=True)
    name = Column(String, nullable=False)
    abbr = Column(String, nullable=False, index=True)
    faculty_name = Column(String, nullable=True)
    faculty_abbr = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())