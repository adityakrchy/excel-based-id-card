"""Hindi font detection and conversion utilities (Kruti Dev, DevLys, Mangal, Unicode Devanagari)."""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Kruti Dev 010 / DevLys 010 to Unicode Devanagari mapping table
# Ordered from longest/most specific to single characters
CHARS_KD: List[str] = [
    "ñ", "Q+Z", "sas", "aa", ")Z", "ZZ", "‘", "’", "“", "”",
    "å", "ƒ", "„", "…", "†", "‡", "ˆ", "‰", "Š", "‹",
    "¶+", "d+", "[+k", "[+", "x+", "T+", "t+", "M+", "<+", "Q+", ";+", "j+", "u+",
    "Ùk", "Ù", "ä", "–", "—", "é", "™", "=kk", "f=k",
    "à", "á", "â", "ã", "ºz", "º", "í", "{k", "{", "=", "«",
    "Nî", "Vî", "Bî", "Mî", "<î", "|", "K", "}",
    "J", "Vª", "Mª", "<ªª", "Nª", "Ø", "Ý", "nzZ", "æ", "ç", "Á", "xz", "#", ":",
    "v‚", "vks", "vkS", "vk", "v", "b±", "Ã", "bZ", "b", "m", "Å", ",s", ",", "_",
    "ô", "d", "Dk", "D", "[k", "[", "x", "Xk", "X", "Ä", "?k", "?", "³",
    "pkS", "p", "Pk", "P", "N", "t", "Tk", "T", ">", "÷", "¥",
    "ê", "ë", "V", "B", "ì", "ï", "M+", "<+", "M", "<", ".k", ".",
    "r", "Rk", "R", "Fk", "F", ")", "n", "/k", "èk", "/", "Ë", "è", "u", "Uk", "U",
    "i", "Ik", "I", "Q", "¶", "c", "Ck", "C", "Hk", "H", "e", "Ek", "E",
    ";", "¸", "j", "y", "Yk", "Y", "G", "o", "Ok", "O",
    "'k", "'", "\"k", "\"", "l", "Lk", "L", "g",
    "È", "z",
    "Ì", "Í", "Î", "Ï", "Ñ", "Ò", "Ó", "Ô", "Ö", "Ø", "Ù", "Ük", "Ü",
    "‚", "ks", "kS", "k", "h", "q", "w", "`", "s", "S",
    "a", "¡", "%", "W", "•", "·", "∙", "·", "~j", "~", "\\", "+", " ः",
    "^", "*", "Þ", "ß", "(", "¼", "½", "¿", "À", "¾", "A", "-", "&", "Œ", "]", "~ ", "@"
]

CHARS_UNICODE: List[str] = [
    "॰", "QZ+", "sa", "a", "र्द्ध", "Z", "\"", "\"", "'", "'",
    "०", "१", "२", "३", "४", "५", "६", "७", "८", "९",
    "फ़्", "क़", "ख़", "ख़्", "ग़", "ज़्", "ज़", "ड़", "ढ़", "फ़", "य़", "ऱ", "ऩ",
    "त्त", "त्त्", "क्त", "दृ", "कृ", "न्न", "न्न्", "=k", "f=",
    "ह्न", "ह्य", "हृ", "ह्म", "ह्र", "ह्", "द्द", "क्ष", "क्ष्", "त्र", "त्र्",
    "छ्य", "ट्य", "ठ्य", "ड्य", "ढ्य", "द्य", "ज्ञ", "द्व",
    "श्र", "ट्र", "ड्र", "ढ्र", "छ्र", "क्र", "फ्र", "र्द्र", "द्र", "प्र", "प्र", "ग्र", "रु", "रू",
    "ऑ", "ओ", "औ", "आ", "अ", "ईं", "ई", "ई", "इ", "उ", "ऊ", "ऐ", "ए", "ऋ",
    "क्क", "क", "क", "क्", "ख", "ख्", "ग", "ग", "ग्", "घ", "घ", "घ्", "ङ",
    "चौ", "च", "च", "च्", "छ", "ज", "ज", "ज्", "झ", "झ्", "ञ",
    "ट्ट", "ट्ठ", "ट", "ठ", "ड्ड", "ड्ढ", "ड़", "ढ़", "ड", "ढ", "ण", "ण्",
    "त", "त", "त्", "थ", "थ्", "द्ध", "द", "ध", "ध", "ध्", "ध्", "ध्", "न", "न", "न्",
    "प", "प", "प्", "फ", "फ्", "ब", "ब", "ब्", "भ", "भ्", "म", "म", "म्",
    "य", "य्", "र", "ल", "ल", "ल्", "ळ", "व", "व", "व्",
    "श", "श्", "ष", "ष्", "स", "स", "स्", "ह",
    "ीं", "्र",
    "द्द", "ट्ट", "ट्ठ", "ड्ड", "कृ", "भ", "्य", "ड्ढ", "झ्", "क्र", "त्त्", "श", "श्",
    "ॉ", "ो", "ौ", "ा", "ी", "ु", "ू", "ृ", "े", "ै",
    "ं", "ँ", "ः", "ॅ", "ऽ", "ऽ", "ऽ", "ऽ", "्र", "्", "?", "़", ":",
    "‘", "’", "“", "”", ";", "(", ")", "{", "}", "=", "।", ".", "-", "॰", ",", "् ", "/"
]

# Set of Devanagari vowel signs / matras in Unicode
UNICODE_MATRAS = set(
    "\u093e\u093f\u0940\u0941\u0942\u0943\u0944\u0947\u0948\u094b\u094c\u0902\u0901\u0903\u0945\u0946\u0949\u094a"
)

# Common Kruti Dev signatures (words or substrings that uniquely appear in Kruti Dev text)
KRUTI_COMMON_PATTERNS = [
    "Jh ", "iz[kaM", "[kaM", "dqekj", "dk;Z", "inkf/kdkjh", "fodkl", "vk'kq", "uxj", "fuxe",
    "Øe", "la[;k", "fofM", "ernku", "dsUnz", "vH;qfDr", "flagokM+k", "dsoVh", "fgeka'kq",
    "feJ", "lkfgy", "unhe", "eaMy", "pkS/kjh", "Hkwfe", "lq/kkj", "lekgŸkkZ", "vfHk;ark",
    "Lukrd", "fuokZpu", "{ks=", "tkys", "fiUVq", "lnj", "njHkaxk", "f'k{kd"
]

# High-frequency Kruti Dev character pairs and special glyphs
KRUTI_SPECIAL_CHARS = set("¼½~åäèéñçÁÍÎÏÖÙØÝæºí÷¥êëìï¶¸")
KRUTI_BIGRAMS = [
    "[k", "?k", "pkS", "Tk", ".k", "Rk", "Fk", "Hk", "Ek", "Yk", "Ok",
    "'k", "\"k", "Lk", "vks", "vkS", "f'", "f\"", "f[", "f?", "f="
]


class HindiConverter:
    """Detects and converts Hindi legacy encodings (Kruti Dev / DevLys) to Unicode (Mangal / UTF-8)."""

    @staticmethod
    def is_unicode_devanagari(text: str) -> bool:
        """Return True if text contains Unicode Devanagari characters (code points 0x0900-0x097F)."""
        if not text:
            return False
        return any(0x0900 <= ord(c) <= 0x097F for c in text)

    @staticmethod
    def is_krutidev_font(font_name: Optional[str]) -> bool:
        """Return True if the font name corresponds to a legacy Hindi font (Kruti Dev, DevLys, etc.)."""
        if not font_name:
            return False
        fn = font_name.lower().strip()
        legacy_names = [
            "kruti", "krutidev", "devlys", "chanakya", "shiva", "walkman",
            "kruti dev", "devlys 010", "kruti dev 010"
        ]
        return any(name in fn for name in legacy_names)

    @staticmethod
    def detect_krutidev_text(text: str) -> bool:
        """Heuristically detect if a string is typed in Kruti Dev / DevLys legacy encoding."""
        if not text:
            return False
        s = str(text).strip()
        if not s or s.isdigit():
            return False

        # If already Unicode Devanagari, it is not Kruti Dev
        dev_count = sum(1 for c in s if 0x0900 <= ord(c) <= 0x097F)
        if dev_count > len(s) * 0.2:
            return False

        # Check for known Kruti signature words
        for pat in KRUTI_COMMON_PATTERNS:
            if pat in s:
                return True

        # Check for special Kruti Dev glyphs (characters that don't occur in standard English)
        for char in s:
            if char in KRUTI_SPECIAL_CHARS:
                return True

        # Check for Kruti bigram frequency
        bigram_matches = sum(1 for bg in KRUTI_BIGRAMS if bg in s)
        if bigram_matches >= 2:
            return True

        # Check for combinations like 'Jh' (Shree) at the start of names
        if s.startswith("Jh ") or " Jh " in s or s.startswith("eks0 ") or " eks0 " in s:
            return True

        return False

    @classmethod
    def kruti_to_unicode(cls, text: str) -> str:
        """Convert a string encoded in Kruti Dev 010 / DevLys 010 to Unicode Devanagari."""
        if not text:
            return ""
        s = str(text)

        # Skip pure digits or empty strings
        if s.isdigit():
            return s

        # If already predominantly Unicode Devanagari, preserve
        dev_count = sum(1 for c in s if 0x0900 <= ord(c) <= 0x097F)
        if dev_count > len(s) * 0.4:
            return s

        # Initial space cleanups
        s = s.replace(" \xaa", "\xaa").replace(" ~j", "~j").replace(" z", "z")

        # Symbol mapping substitution
        for kd, uni in zip(CHARS_KD, CHARS_UNICODE):
            s = s.replace(kd, uni)

        s = s.replace("±", "Zं")
        s = s.replace("Æ", "र्f")

        # Reposition 'f' (Chhoti 'i' matra: ि)
        # In Kruti Dev, 'f' precedes the consonant/cluster, whereas in Unicode it follows it.
        def _fix_i_matra(val: str) -> str:
            pattern = re.compile(r"f((?:[\u0915-\u0939]\u094d)*[\u0915-\u0939\u0958-\u095f])")
            while True:
                m = pattern.search(val)
                if not m:
                    break
                cluster = m.group(1)
                val = val[:m.start()] + cluster + "\u093f" + val[m.end():]
            return val

        s = _fix_i_matra(s)

        # Reposition 'fa' (Chhoti 'i' matra with anusvara: िं)
        s = s.replace("Ç", "fa").replace("É", "र्fa").replace("¯", "fa")
        def _fix_fa(val: str) -> str:
            pattern = re.compile(r"fa((?:[\u0915-\u0939]\u094d)*[\u0915-\u0939\u0958-\u095f])")
            while True:
                m = pattern.search(val)
                if not m:
                    break
                cluster = m.group(1)
                val = val[:m.start()] + cluster + "\u093f\u0902" + val[m.end():]
            return val

        s = _fix_fa(s)

        # Any leftover 'f' before a single character
        misplaced = re.search(r"f(.)", s)
        while misplaced:
            ch = misplaced.group(1)
            s = s.replace("f" + ch, ch + "\u093f", 1)
            misplaced = re.search(r"f(.)", s)

        s = s.replace("Ê", "ीZ")

        # Reposition 'Z' (Reph: र्)
        # In Kruti Dev, 'Z' is typed after the consonant/matra, but in Unicode Devanagari,
        # 'र्' precedes the consonant cluster.
        while "Z" in s:
            pos_z = s.index("Z")
            idx = pos_z - 1
            # Scan backward past any matras/vowel signs
            while idx >= 0 and s[idx] in UNICODE_MATRAS:
                idx -= 1
            # Scan backward past consonant and halant
            if idx >= 0:
                if s[idx] == "\u094d" and idx > 0:
                    idx -= 1
                while idx > 1 and s[idx - 1] == "\u094d":
                    idx -= 2
            if idx >= 0:
                cluster = s[idx:pos_z]
                s = s[:idx] + "\u0930\u094d" + cluster + s[pos_z + 1:]
            else:
                s = s.replace("Z", "\u0930\u094d", 1)

        # Clean up double halants
        s = s.replace("\u094d\u094d", "\u094d")
        return s

    @classmethod
    def convert_value(
        cls,
        val: Any,
        font_name: Optional[str] = None,
        mode: str = "auto",
    ) -> str:
        """Convert a single cell value according to font_name and conversion mode.

        Modes:
            'auto': Auto-detect Kruti Dev font or text characteristics. If detected, convert.
            'kruti_to_unicode': Force Kruti Dev -> Unicode conversion for all legacy strings.
            'chanakya_to_unicode': Force the legacy Devanagari conversion used for the
                Chanakya legacy font.  Chanakya shares the consonant layout with
                Kruti Dev, so the same mapping table is used for the supported subset.
            'none': Preserve raw value without conversion (for Mangal/Unicode or raw Latin).
        """
        if val is None:
            return ""
        s = str(val)
        if not s:
            return ""

        if mode == "none":
            return s

        if mode == "kruti_to_unicode":
            return cls.kruti_to_unicode(s)

        if mode == "chanakya_to_unicode":
            return cls.kruti_to_unicode(s)

        # mode == 'auto'
        if cls.is_krutidev_font(font_name):
            return cls.kruti_to_unicode(s)

        if cls.detect_krutidev_text(s):
            return cls.kruti_to_unicode(s)

        return s
