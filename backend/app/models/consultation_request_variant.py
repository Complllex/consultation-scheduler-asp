from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class ConsultationRequestVariant(Base):
    __tablename__ = "consultation_request_variants"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("consultation_requests.id"), nullable=False)

    variant_number = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="generated")  # generated / selected / discarded

    score = Column(Integer, nullable=True)
    comment = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())