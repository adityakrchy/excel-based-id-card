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
    "mangal": {
        "regular": ["mangal.ttf", "Mangal.ttf", "Devanagari Sangam MN.ttc", "DevanagariMT.ttc", "Kohinoor.ttc", "NotoSansDevanagari-Regular.ttf", "lohit_hi.ttf"],
        "bold": ["mangalb.ttf", "Mangal-Bold.ttf", "DevanagariMT-Bold.ttf", "NotoSansDevanagari-Bold.ttf", "lohit_hi.ttf"],
        "italic": ["mangal.ttf", "Mangal.ttf", "Devanagari Sangam MN.ttc", "NotoSansDevanagari-Regular.ttf"],
        "bold_italic": ["mangalb.ttf", "Mangal-Bold.ttf", "NotoSansDevanagari-Bold.ttf"],
    },
    "kruti dev 010": {
        "regular": ["Kruti Dev 010 Regular.ttf", "Kruti Dev 010.ttf", "kruti_dev_010.ttf", "KRDEV010.TTF", "KrutiDev010.ttf", "kdev010.ttf"],
        "bold": ["Kruti Dev 010 Bold.ttf", "Kruti Dev 010-Bold.ttf", "kruti_dev_010_b.ttf"],
        "italic": ["Kruti Dev 010 Italic.ttf", "Kruti Dev 010.ttf"],
        "bold_italic": ["Kruti Dev 010 Bold.ttf", "Kruti Dev 010.ttf"],
    },
    "kruti dev": {
        "regular": ["Kruti Dev 010 Regular.ttf", "Kruti Dev 010.ttf", "kruti_dev_010.ttf", "KRDEV010.TTF"],
        "bold": ["Kruti Dev 010 Bold.ttf", "Kruti Dev 010-Bold.ttf"],
        "italic": ["Kruti Dev 010 Italic.ttf", "Kruti Dev 010.ttf"],
        "bold_italic": ["Kruti Dev 010 Bold.ttf", "Kruti Dev 010.ttf"],
    },
    "devlys 010": {
        "regular": ["DevLys 010.ttf", "DevLys 010 Normal.ttf", "devlys010.ttf", "DevLys010.ttf"],
        "bold": ["DevLys 010 Bold.ttf", "devlys010b.ttf"],
        "italic": ["DevLys 010 Italic.ttf", "DevLys 010.ttf"],
        "bold_italic": ["DevLys 010 Bold.ttf", "DevLys 010.ttf"],
    },
    "devlys": {
        "regular": ["DevLys 010.ttf", "DevLys 010 Normal.ttf", "devlys010.ttf"],
        "bold": ["DevLys 010 Bold.ttf"],
        "italic": ["DevLys 010 Italic.ttf"],
        "bold_italic": ["DevLys 010 Bold.ttf"],
    },
    "nirmala ui": {
        "regular": ["Nirmala.ttf", "nirmala.ttf", "NirmalaUI.ttf"],
        "bold": ["NirmalaB.ttf", "nirmalab.ttf", "NirmalaUI-Bold.ttf"],
        "italic": ["NirmalaS.ttf", "Nirmala.ttf"],
        "bold_italic": ["NirmalaB.ttf", "Nirmala.ttf"],
    },
    "nirmala": {
        "regular": ["Nirmala.ttf", "nirmala.ttf"],
        "bold": ["NirmalaB.ttf", "nirmalab.ttf"],
        "italic": ["NirmalaS.ttf", "Nirmala.ttf"],
        "bold_italic": ["NirmalaB.ttf", "Nirmala.ttf"],
    },
    "noto sans devanagari": {
        "regular": ["NotoSansDevanagari-Regular.ttf", "NotoSansDevanagari.ttf"],
        "bold": ["NotoSansDevanagari-Bold.ttf", "NotoSansDevanagari-SemiBold.ttf"],
        "italic": ["NotoSansDevanagari-Regular.ttf"],
        "bold_italic": ["NotoSansDevanagari-Bold.ttf"],
    },
    "devanagari": {
        "regular": ["mangal.ttf", "Devanagari Sangam MN.ttc", "Kohinoor.ttc", "DevanagariMT.ttc", "NotoSansDevanagari-Regular.ttf", "Nirmala.ttf"],
        "bold": ["mangalb.ttf", "Devanagari Sangam MN.ttc", "Kohinoor.ttc", "DevanagariMT-Bold.ttf", "NotoSansDevanagari-Bold.ttf", "NirmalaB.ttf"],
        "italic": ["mangal.ttf", "Devanagari Sangam MN.ttc", "NotoSansDevanagari-Regular.ttf"],
        "bold_italic": ["mangalb.ttf", "Devanagari Sangam MN.ttc", "NotoSansDevanagari-Bold.ttf"],
    },
}


class FontManager:
    """Discovers, caches, and returns Pillow ImageFont instances."""

    _font_cache: Dict[Tuple[str, int, bool, bool], ImageFont.FreeTypeFont] = {}
    _system_font_dirs: Optional[List[Path]] = None
    _qt_fonts_registered: bool = False
    _family_to_font_files: Dict[str, List[Path]] = {}

    @classmethod
    def register_system_fonts_with_qt(cls) -> int:
        """Register all TrueType/OpenType fonts found in system font directories with QFontDatabase.

        This ensures all installed system and user fonts are available to Qt widgets such as QFontComboBox.
        Also maps family names to font file paths for Pillow renderer.
        """
        if cls._qt_fonts_registered:
            return len(cls._family_to_font_files)
        try:
            from PySide6.QtGui import QFontDatabase
        except ImportError:
            return 0

        registered = 0
        for fdir in cls.get_system_font_dirs():
            for ext in ("*.ttf", "*.otf", "*.ttc"):
                try:
                    for fpath in fdir.glob(f"**/{ext}"):
                        if fpath.is_file():
                            fid = QFontDatabase.addApplicationFont(str(fpath))
                            if fid != -1:
                                registered += 1
                                for fam in QFontDatabase.applicationFontFamilies(fid):
                                    fam_k = fam.lower().strip()
                                    if fam_k not in cls._family_to_font_files:
                                        cls._family_to_font_files[fam_k] = []
                                    if fpath not in cls._family_to_font_files[fam_k]:
                                        cls._family_to_font_files[fam_k].append(fpath)
                except Exception:
                    pass
        cls._qt_fonts_registered = True
        return registered

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

        # Check family mapped during Qt font registration if available
        if fam_key in cls._family_to_font_files:
            files = cls._family_to_font_files[fam_key]
            for f in files:
                fname_lower = f.name.lower()
                if bold and italic and ("bold" in fname_lower or "bd" in fname_lower) and ("italic" in fname_lower or "it" in fname_lower or "oblique" in fname_lower):
                    return f
                elif bold and not italic and ("bold" in fname_lower or "bd" in fname_lower):
                    return f
                elif italic and not bold and ("italic" in fname_lower or "it" in fname_lower or "oblique" in fname_lower):
                    return f
            if files:
                return files[0]

        candidate_names = []
        if fam_key in FONT_MAPPINGS:
            candidate_names.extend(FONT_MAPPINGS[fam_key].get(style_key, []))

        # Add direct name guesses (with hyphen and space variations)
        suffix = ""
        space_suffix = " Regular"
        if bold and italic:
            suffix = "-BoldItalic"
            space_suffix = " Bold Italic"
        elif bold:
            suffix = "-Bold"
            space_suffix = " Bold"
        elif italic:
            suffix = "-Italic"
            space_suffix = " Italic"

        candidate_names.extend([
            f"{family}{space_suffix}.ttf",
            f"{family}{space_suffix}.otf",
            f"{family}{suffix}.ttf",
            f"{family}{suffix}.otf",
            f"{family}.ttf",
            f"{family}.otf",
            f"{fam_key}{suffix.lower()}.ttf",
            f"{fam_key}.ttf",
        ])

        font_dirs = cls.get_system_font_dirs()
        # 1. Search for primary family candidates first
        for candidate in candidate_names:
            for fdir in font_dirs:
                direct = fdir / candidate
                if direct.exists():
                    return direct
                try:
                    for sub in fdir.glob(f"**/{candidate}"):
                        if sub.is_file():
                            return sub
                except Exception:
                    pass

        # 2. Only fall back to generic system fonts if primary family was not found
        generic_fallbacks = [
            "Arial.ttf",
            "arial.ttf",
            "DejaVuSans.ttf",
            "Helvetica.ttc",
        ]
        for candidate in generic_fallbacks:
            for fdir in font_dirs:
                direct = fdir / candidate
                if direct.exists():
                    return direct
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
        size: float = 24.0,
        bold: bool = False,
        italic: bool = False,
    ) -> ImageFont.ImageFont:
        """Load and cache an ImageFont instance at specified pixel size. Falls back gracefully if unavailable."""
        int_size = max(1, int(round(size)))
        cache_key = (family.lower(), int_size, bold, italic)
        if cache_key in cls._font_cache:
            return cls._font_cache[cache_key]

        font_path = cls.find_font_file(family, bold, italic)
        if font_path:
            try:
                font = ImageFont.truetype(str(font_path), size=int_size)
                cls._font_cache[cache_key] = font
                return font
            except Exception as e:
                logger.warning("Failed to load font from %s: %s", font_path, e)

        # Fallback to Pillow's built-in default font
        logger.debug("Falling back to default font for %s (size %d)", family, int_size)
        try:
            # Pillow >= 10.1 has ImageFont.load_default(size=size)
            return ImageFont.load_default(size=int_size)
        except TypeError:
            return ImageFont.load_default()
