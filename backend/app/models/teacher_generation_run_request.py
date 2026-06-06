from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint

from app.core.database import Base


class TeacherGenerationRunRequest(Base):
    __tablename__ = "teacher_generation_run_requests"

    id = Column(Integer, primary_key=True, index=True)

    run_id = Column(Integer, ForeignKey("teacher_generation_runs.id"), nullable=False)
    request_id = Column(Integer, ForeignKey("consultation_requests.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("run_id", "request_id", name="uq_teacher_generation_run_request"),
    )