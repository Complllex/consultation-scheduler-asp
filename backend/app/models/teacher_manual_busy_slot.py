from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


class TeacherManualBusySlot(Base):
    __tablename__ = "teacher_manual_busy_slots"

    id = Column(Integer, primary_key=True, index=True)

    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)

    day = Column(Integer, nullable=False)
    pair_number = Column(Integer, nullable=False)
    week_type = Column(String, nullable=False)

    title = Column(String, nullable=False, default="Лабораторная")
    comment = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())