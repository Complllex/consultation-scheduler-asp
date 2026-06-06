from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


class Discipline(Base):
    __tablename__ = "disciplines"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False, index=True)
    short_name = Column(String, nullable=True)
    abbr = Column(String, nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())