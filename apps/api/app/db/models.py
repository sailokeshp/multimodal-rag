import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


import os

# Dimensions must match the configured embedding models.
# TEXT: default BAAI/bge-small-en-v1.5 = 384d
# IMAGE: SigLIP2 so400m = 1152d
# If you change models, drop and recreate the DB.
TEXT_EMBED_DIM = int(os.getenv("TEXT_EMBED_DIM", "384"))
IMAGE_EMBED_DIM = int(os.getenv("IMAGE_EMBED_DIM", "1152"))


class Base(DeclarativeBase):
    pass


class File(Base):
    __tablename__ = "files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_name = Column(Text, nullable=False)
    file_type = Column(Text, nullable=False)
    mime_type = Column(Text)
    s3_key = Column(Text, nullable=False)
    checksum = Column(Text)
    size_bytes = Column(BigInteger)
    page_count = Column(Integer)
    status = Column(Text, nullable=False, default="UPLOADED")
    language = Column(Text)
    uploaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    processed_at = Column(DateTime)
    error_message = Column(Text)

    chunks = relationship("DocumentChunk", back_populates="file", cascade="all, delete-orphan")
    images = relationship("Image", back_populates="file", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id = Column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    chunk_type = Column(Text, nullable=False)   # text_chunk | page_summary | table_summary | image_caption | ocr_text
    page_start = Column(Integer)
    page_end = Column(Integer)
    section_title = Column(Text)
    chunk_index = Column(Integer)
    content = Column(Text, nullable=False)
    token_count = Column(Integer)
    embedding = Column(Vector(TEXT_EMBED_DIM))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    file = relationship("File", back_populates="chunks")


class Image(Base):
    __tablename__ = "images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id = Column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    page_number = Column(Integer)
    image_role = Column(Text)   # uploaded | page_render | inline_extracted
    s3_key = Column(Text, nullable=False)
    thumbnail_s3_key = Column(Text)
    width = Column(Integer)
    height = Column(Integer)
    ocr_text = Column(Text)
    caption_text = Column(Text)
    embedding = Column(Vector(IMAGE_EMBED_DIM))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    file = relationship("File", back_populates="images")


class SearchLog(Base):
    __tablename__ = "search_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_text = Column(Text, nullable=False)
    query_type = Column(Text)
    result_count = Column(Integer)
    latency_ms = Column(Integer)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
