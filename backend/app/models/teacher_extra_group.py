from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint

from app.core.database import Base


class TeacherExtraGroup(Base):
    __tablename__ = "teacher_extra_groups"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    source = Column(String, nullable=False, default="manual_department_access")

    __table_args__ = (
        UniqueConstraint("teacher_id", "group_id", name="uq_teacher_extra_group"),
    )