from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


class ScheduleSlot(Base):
    __tablename__ = "schedule_slots"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    day = Column(Integer, nullable=False)
    pair_number = Column(Integer, nullable=False)
    week_type = Column(String, nullable=False)  # both / num / den
    discipline_id = Column(Integer, ForeignKey("disciplines.id"), nullable=True)
    act_type = Column(String, nullable=True)
    start_time = Column(String, nullable=True)
    end_time = Column(String, nullable=True)
    source_type = Column(String, nullable=False, default="base")
    is_vuc = Column(Boolean, nullable=False, default=False)
    raw_teacher_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())