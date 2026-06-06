from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint

from app.core.database import Base


class ConsultationRequestGroup(Base):
    __tablename__ = "consultation_request_groups"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("consultation_requests.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("request_id", "group_id", name="uq_consultation_request_group"),
    )