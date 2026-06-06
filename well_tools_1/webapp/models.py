"""ORM models: templates registry and report run history."""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, JSON, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .db import Base


class Template(Base):
    """A registered Word template, keyed uniquely by (damage_count, config_key)."""
    __tablename__ = "templates"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    damage_count = Column(Integer, nullable=False)
    config_key = Column(String, nullable=False)        # e.g. "4.5-7-9-13-18"
    file_path = Column(String, nullable=False)          # absolute path on disk
    placeholders = Column(JSON, nullable=True)          # list of tag strings
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow, nullable=False)

    runs = relationship("ReportRun", back_populates="template")

    __table_args__ = (
        UniqueConstraint("damage_count", "config_key", name="uq_damage_config"),
    )


class ReportRun(Base):
    """One report-generation attempt and its result."""
    __tablename__ = "report_runs"

    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey("templates.id"), nullable=True)
    well_name = Column(String, nullable=True)
    excel_path = Column(String, nullable=False)
    working_dir = Column(String, nullable=False)
    output_docx_path = Column(String, nullable=True)
    status = Column(String, nullable=False)             # "success" | "failed"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    template = relationship("Template", back_populates="runs")
