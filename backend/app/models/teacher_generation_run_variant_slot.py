from sqlalchemy import Column, ForeignKey, Integer, String

from app.core.database import Base


class TeacherGenerationRunVariantSlot(Base):
    __tablename__ = "teacher_generation_run_variant_slots"

    id = Column(Integer, primary_key=True, index=True)

    run_variant_id = Column(Integer, ForeignKey("teacher_generation_run_variants.id"), nullable=False)
    request_id = Column(Integer, ForeignKey("consultation_requests.id"), nullable=False)

    day = Column(Integer, nullable=False)
    pair_number = Column(Integer, nullable=False)
    week_type = Column(String, nullable=False)