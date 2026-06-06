from sqlalchemy import Column, ForeignKey, Integer

from app.core.database import Base


class ScheduleSlotTeacher(Base):
    __tablename__ = "schedule_slot_teachers"

    id = Column(Integer, primary_key=True, index=True)
    slot_id = Column(Integer, ForeignKey("schedule_slots.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)