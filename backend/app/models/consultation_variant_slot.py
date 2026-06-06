from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


class ConsultationVariantSlot(Base):
    __tablename__ = "consultation_variant_slots"

    id = Column(Integer, primary_key=True, index=True)
    variant_id = Column(Integer, ForeignKey("consultation_request_variants.id"), nullable=False)

    day = Column(Integer, nullable=False)
    pair_number = Column(Integer, nullable=False)
    week_type = Column(String, nullable=False)  # both / num / den

    created_at = Column(DateTime(timezone=True), server_default=func.now())