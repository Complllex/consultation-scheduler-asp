from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


class ConsultationRequest(Base):
    __tablename__ = "consultation_requests"

    id = Column(Integer, primary_key=True, index=True)

    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)

    discipline_id = Column(Integer, ForeignKey("disciplines.id"), nullable=True)

    consultations_count = Column(Integer, nullable=False)
    preferred_audience = Column(String, nullable=True)

    avoid_day_without_classes = Column(Boolean, nullable=False, default=False)
    avoid_first_pair = Column(Boolean, nullable=False, default=False)
    avoid_last_pair = Column(Boolean, nullable=False, default=False)

    preferred_day = Column(Integer, nullable=True)
    excluded_day = Column(Integer, nullable=True)

    week_preference = Column(String, nullable=False, default="both")

    status = Column(String, nullable=False, default="ready_for_generation")
    selected_variant_id = Column(
        Integer, ForeignKey("consultation_request_variants.id"), nullable=True
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )