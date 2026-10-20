"""Manual verification of the text minimum-size behaviour."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QApplication

app = QApplication([])

from id_card_generator.core.models import CanvasElement, TemplateDefinition
from id_card_generator.ui.editor_page import EditorPage

page = EditorPage()
tmpl = TemplateDefinition(name="T", width_px=800, height_px=500)
page.load_template(tmpl)

page._add_static_text()
item = page.scene.get_selected_item()
print("auto-fit size:", item.element.width, "x", item.element.height)
print("natural size:", item._get_text_natural_size())
print("min size    :", item._get_text_min_size())

# Simulate a drag of the bottom-right handle far into the top-left.
tiny = QRectF(item._rect.x(), item._rect.y(), 5, 5)
constrained = item._apply_text_min_size(tiny, handle=4)
print("constrained to 5x5 ->", constrained.width(), "x", constrained.height())

# Simulate a horizontal-only squeeze (left handle).
squeeze = QRectF(item._rect.x(), item._rect.y(), 30, item._rect.height())
constrained = item._apply_text_min_size(squeeze, handle=7)
print("squeezed width ->", constrained.width(), "x", constrained.height())

# The text must still be fully inside the box.
from PySide6.QtGui import QFontMetrics
from id_card_generator.editor import text_metrics

text = item._get_display_text()
font = item._get_text_font()
fm = QFontMetrics(font)
br = fm.boundingRect(
    QRectF(0, 0, int(constrained.width()), 32767).toRect(),
    text_metrics.measurement_flags(item.element),
    text,
)
print("text bbox:", br.width(), "x", br.height(), "box:", constrained.width(), "x", constrained.height())
assert br.height() <= constrained.height(), "text is clipped vertically!"
assert br.width() <= constrained.width() or item.element.style.wrap, "text is clipped horizontally!"
print("OK (wrap)")


# ── No-wrap case ────────────────────────────────────────────────────────────
el = CanvasElement(name="NoWrap", type="static_text", static_content="Hello World", width=200, height=40)
el.style.wrap = False
page.scene.add_element(el)
item2 = page.scene.get_selected_item()
print("\nno-wrap natural:", item2._get_text_natural_size())
c = item2._apply_text_min_size(QRectF(0, 0, 10, 10), handle=4)
print("no-wrap constrained ->", c.width(), "x", c.height())
assert c.width() >= item2._get_text_natural_size()[0] - 0.5


# ── Long wrapped paragraph ──────────────────────────────────────────────────
long_text = "This is a fairly long paragraph of text that will certainly need to wrap over several lines when rendered inside a small box on the card."
el3 = CanvasElement(name="Long", type="static_text", static_content=long_text, width=400, height=200)
page.scene.add_element(el3)
item3 = page.scene.get_selected_item()
print("\nlong min size @400:", item3._get_text_min_size(400))
c3 = item3._apply_text_min_size(QRectF(0, 0, 60, 20), handle=4)
print("long constrained ->", c3.width(), "x", c3.height())
font3 = item3._get_text_font()
br3 = QFontMetrics(font3).boundingRect(
    QRectF(0, 0, int(c3.width()), 32767).toRect(),
    text_metrics.measurement_flags(el3),
    long_text,
)
print("long text bbox:", br3.width(), "x", br3.height())
assert br3.height() <= c3.height(), "paragraph clipped!"
print("OK")
