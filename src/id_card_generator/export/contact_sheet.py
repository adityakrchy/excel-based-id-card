"""Generates multi-page PDF contact sheets using ReportLab."""

import logging
from pathlib import Path
from typing import List, Tuple
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

logger = logging.getLogger(__name__)


class ContactSheetGenerator:
    """Arranges exported card images in a printable multi-page grid PDF."""

    @staticmethod
    def generate_pdf(
        card_items: List[Tuple[Path, str, str]],  # (image_path, pin, name)
        output_pdf_path: Path,
        title: str = "ID Cards - Contact Sheet",
        columns: int = 2,
        rows: int = 3,
        margin_mm: float = 12.7,
    ) -> Path:
        """Create an optional contact sheet PDF.

        This is a convenience artifact - the export itself always writes one
        file per card.
        """
        output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
        c = canvas.Canvas(str(output_pdf_path), pagesize=A4)
        page_w, page_h = A4

        margin = max(4.0, float(margin_mm)) * 72.0 / 25.4  # mm -> points
        margin_x = margin
        margin_y = margin
        header_h = 40.0

        cols = max(1, int(columns))
        rows = max(1, int(rows))
        per_page = cols * rows

        grid_w = page_w - (2 * margin_x)
        grid_h = page_h - (2 * margin_y) - header_h

        cell_w = grid_w / cols
        cell_h = grid_h / rows

        for idx, (img_path, pin, name) in enumerate(card_items):
            page_idx = idx % per_page
            if page_idx == 0:
                if idx > 0:
                    c.showPage()
                # Draw header
                c.setFont("Helvetica-Bold", 14)
                c.drawString(margin_x, page_h - margin_y - 20, title)
                c.setFont("Helvetica", 9)
                page_num = (idx // per_page) + 1
                c.drawRightString(page_w - margin_x, page_h - margin_y - 20, f"Page {page_num}")
                c.setStrokeColorRGB(0.8, 0.8, 0.8)
                c.setLineWidth(0.5)
                c.line(margin_x, page_h - margin_y - 28, page_w - margin_x, page_h - margin_y - 28)

            col = page_idx % cols
            row = page_idx // cols

            # Calculate box inside cell
            box_x = margin_x + (col * cell_w) + 10
            # PDF coordinates start from bottom-left
            box_y = page_h - margin_y - header_h - ((row + 1) * cell_h) + 10
            usable_w = cell_w - 20
            usable_h = cell_h - 35  # leave room for text label

            if img_path.exists():
                try:
                    c.drawImage(
                        str(img_path),
                        box_x,
                        box_y + 20,
                        width=usable_w,
                        height=usable_h,
                        preserveAspectRatio=True,
                        anchor='c',
                    )
                except Exception as e:
                    logger.warning("Failed to render image on contact sheet %s: %s", img_path, e)

            # Draw label under card
            c.setFont("Helvetica-Bold", 10)
            c.setFillColorRGB(0.1, 0.1, 0.1)
            c.drawCentredString(box_x + (usable_w / 2), box_y + 8, f"PIN: {pin} • {name[:24]}")

        c.save()
        logger.info("Generated contact sheet PDF at %s (%d cards)", output_pdf_path, len(card_items))
        return output_pdf_path
