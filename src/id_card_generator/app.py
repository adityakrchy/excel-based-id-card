"""Application initialization and main execution loop."""

import logging
import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from id_card_generator.core.constants import APP_NAME, APP_ORG
from id_card_generator.core.logging_config import setup_logging
from id_card_generator.ui.font_scaling import install_font_scaling
from id_card_generator.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


def main() -> int:
    """Initialize application, logging, and launch MainWindow."""
    setup_logging()
    logger.info("Starting %s desktop application...", APP_NAME)

    # Enable high-DPI scaling
    QApplication.setOrganizationName(APP_ORG)
    QApplication.setApplicationName(APP_NAME)

    app = QApplication(sys.argv)

    # Scale the UI type to the screen: dense (retina) panels and tall
    # resolutions get larger glyphs than the compact 10-12px base scale.
    install_font_scaling()

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
