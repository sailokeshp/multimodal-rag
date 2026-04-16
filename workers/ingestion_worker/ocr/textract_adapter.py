"""
AWS Textract adapter — used selectively for complex scanned PDFs or forms.
Only called when USE_TEXTRACT=true AND local OCR quality is insufficient.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def run_textract_ocr(image_bytes: bytes, aws_region: str = "us-east-1") -> str:
    """
    Send image bytes to AWS Textract DetectDocumentText.
    Returns extracted text or empty string on failure.
    """
    if os.getenv("USE_TEXTRACT", "false").lower() != "true":
        logger.debug("Textract disabled (USE_TEXTRACT=false)")
        return ""

    try:
        import boto3

        client = boto3.client("textract", region_name=aws_region)
        response = client.detect_document_text(Document={"Bytes": image_bytes})

        lines = [
            block["Text"]
            for block in response.get("Blocks", [])
            if block.get("BlockType") == "LINE"
        ]
        text = "\n".join(lines)
        logger.info("Textract extracted %d lines", len(lines))
        return text
    except Exception as exc:
        logger.error("Textract OCR failed: %s", exc, exc_info=True)
        return ""
