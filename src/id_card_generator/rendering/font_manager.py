"""Font manager providing safe font loading, caching, and cross-platform fallbacks."""

import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PIL import ImageFont

logger = logging.getLogger(__name__)

# Common fallback font filenames by platform and family
FONT_MAPPINGS: Dict[str, Dict[str, List[str]]] = {
    "arial": {
        "regular": ["Arial.ttf", "arial.ttf", "LiberationSans-Regular.ttf", "DejaVuSans.ttf"],
        "bold": ["Arial-Bold.ttf", "arialbd.ttf", "LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf"],
        "italic": ["Arial-Italic.ttf", "ariali.ttf", "LiberationSans-Italic.ttf", "DejaVuSans-Oblique.ttf"],
        "bold_italic": ["Arial-BoldItalic.ttf", "arialbi.ttf", "LiberationSans-BoldItalic.ttf", "DejaVuSans-BoldOblique.ttf"],
    },
    "segoe ui": {
        "regular": ["segoeui.ttf", "SegoeUI.ttf", "arial.ttf"],
        "bold": ["segoeuib.ttf", "SegoeUI-Bold.ttf", "arialbd.ttf"],
        "italic": ["segoeuii.ttf", "SegoeUI-Italic.ttf", "ariali.ttf"],
        "bold_italic": ["segoeuiz.ttf", "SegoeUI-BoldItalic.ttf", "arialbi.ttf"],
    },
    "times new roman": {
        "regular": ["times.ttf", "TimesNewRoman.ttf", "LiberationSerif-Regular.ttf", "DejaVuSerif.ttf"],
        "bold": ["timesbd.ttf", "TimesNewRoman-Bold.ttf", "LiberationSerif-Bold.ttf", "DejaVuSerif-Bold.ttf"],
        "italic": ["timesi.ttf", "TimesNewRoman-Italic.ttf", "LiberationSerif-Italic.ttf", "DejaVuSerif-Italic.ttf"],
        "bold_italic": ["timesbi.ttf", "TimesNewRoman-BoldItalic.ttf", "LiberationSerif-BoldItalic.ttf", "DejaVuSerif-BoldItalic.ttf"],
    },
    "tahoma": {
        "regular": ["tahoma.ttf", "Tahoma.ttf", "arial.ttf"],
        "bold": ["tahomabd.ttf", "Tahoma-Bold.ttf", "arialbd.ttf"],
        "italic": ["tahoma.ttf", "ariali.ttf"],
        "bold_italic": ["tahomabd.ttf", "arialbi.ttf"],
    },
}


class FontManager:
    """Discovers, caches, and returns Pillow ImageFont instances."""

    _font_cache: Dict[Tuple[str, int, bool, bool], ImageFont.FreeTypeFont] = {}
    _system_font_dirs: Optional[List[Path]] = None

    @classmethod
    def get_system_font_dirs(cls) -> List[Path]:
        """Return list of standard system font directories."""
        if cls._system_font_dirs is not None:
            return cls._system_font_dirs

        dirs = []
        if sys.platform == "win32":
            windir = os.environ.get("WINDIR", "C:\\Windows")
            dirs.append(Path(windir) / "Fonts")
            local_appdata = os.environ.get("LOCALAPPDATA")
            if local_appdata:
                dirs.append(Path(local_appdata) / "Microsoft" / "Windows" / "Fonts")
        elif sys.platform == "darwin":
            dirs.extend([
                Path("/System/Library/Fonts"),
                Path("/Library/Fonts"),
                Path("~/Library/Fonts").expanduser(),
            ])
        else:
            dirs.extend([
                Path("/usr/share/fonts"),
                Path("/usr/local/share/fonts"),
                Path("~/.fonts").expanduser(),
                Path("~/.local/share/fonts").expanduser(),
            ])

        cls._system_font_dirs = [d for d in dirs if d.exists()]
        return cls._system_font_dirs

    @classmethod
    def find_font_file(cls, family: str, bold: bool = False, italic: bool = False) -> Optional[Path]:
        """Search font directories for a matching TrueType / OpenType font file."""
        fam_key = family.lower().strip()
        style_key = "regular"
        if bold and italic:
            style_key = "bold_italic"
        elif bold:
            style_key = "bold"
        elif italic:
            style_key = "italic"

        candidate_names = []
        if fam_key in FONT_MAPPINGS:
            candidate_names.extend(FONT_MAPPINGS[fam_key].get(style_key, []))

        # Add direct name guesses
        suffix = ""
        if bold and italic:
            suffix = "-BoldItalic"
        elif bold:
            suffix = "-Bold"
        elif italic:
            suffix = "-Italic"

        candidate_names.extend([
            f"{family}{suffix}.ttf",
            f"{family}{suffix}.otf",
            f"{fam_key}{suffix.lower()}.ttf",
            f"{fam_key}.ttf",
        ])

        # Also fallback candidates
        candidate_names.extend([
            "Arial.ttf",
            "arial.ttf",
            "DejaVuSans.ttf",
            "Helvetica.ttc",
        ])

        font_dirs = cls.get_system_font_dirs()
        for candidate in candidate_names:
            for fdir in font_dirs:
                direct = fdir / candidate
                if direct.exists():
                    return direct
                # Recursive search in subdirectories (e.g. /usr/share/fonts/truetype/...)
                try:
                    for sub in fdir.glob(f"**/{candidate}"):
                        if sub.is_file():
                            return sub
                except Exception:
                    pass

        return None

    @classmethod
    def get_font(
        cls,
        family: str = "Arial",
        size: int = 24,
        bold: bool = False,
        italic: bool = False,
    ) -> ImageFont.ImageFont:
        """Load and cache an ImageFont instance. Falls back gracefully if unavailable."""
        cache_key = (family.lower(), size, bold, italic)
        if cache_key in cls._font_cache:
            return cls._font_cache[cache_key]

        font_path = cls.find_font_file(family, bold, italic)
        if font_path:
            try:
                font = ImageFont.truetype(str(font_path), size=size)
                cls._font_cache[cache_key] = font
                return font
            except Exception as e:
                logger.warning("Failed to load font from %s: %s", font_path, e)

        # Fallback to Pillow's built-in default font
        logger.debug("Falling back to default font for %s (size %d)", family, size)
        try:
            # Pillow >= 10.1 has ImageFont.load_default(size=size)
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()
