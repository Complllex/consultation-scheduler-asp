from sqlalchemy import Column, ForeignKey, Integer, String

from app.core.database import Base


class TeacherGenerationRunVariant(Base):
    __tablename__ = "teacher_generation_run_variants"

    id = Column(Integer, primary_key=True, index=True)

    run_id = Column(Integer, ForeignKey("teacher_generation_runs.id"), nullable=False)
    variant_number = Column(Integer, nullable=False)
    score = Column(Integer, nullable=True)
    comment = Column(String, nullable=True)
    status = Column(String, nullable=False, default="generated")  # generated/selected/discarded