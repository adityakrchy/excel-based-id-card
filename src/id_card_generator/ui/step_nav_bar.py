"""Backwards compatible alias for the shared page footer.

The step navigation bar was replaced by :class:`PageFooter`, which is built
from the design tokens and driven by :mod:`id_card_generator.ui.workflow`.
This module keeps the historic import path working.
"""

from id_card_generator.ui.components.page_scaffold import PageFooter

StepNavBar = PageFooter

__all__ = ["PageFooter", "StepNavBar"]
