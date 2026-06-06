from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id = Column(Integer, primary_key=True, index=True)

    job_type = Column(String, nullable=False)  # teacher_groups / department_groups
    target_uuid = Column(String, nullable=False)

    status = Column(String, nullable=False, default="pending")  # pending / running / done / failed

    total_groups = Column(Integer, nullable=False, default=0)
    processed_groups = Column(Integer, nullable=False, default=0)
    matched_groups = Column(Integer, nullable=False, default=0)
    imported_groups = Column(Integer, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)

    message = Column(String, nullable=True)
    result_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )