import re
from typing import Tuple
from backend.app.core.logging import logger

try:
    from bijoy2unicode import converter
    _bijoy = converter.Unicode()
except Exception as e:
    logger.warning(f"bijoy2unicode module could not be loaded: {e}")
    _bijoy = None


class BijoyConverter:
    """
    Detects and converts legacy ANSI Bijoy (SutonnyMJ font) encoded Bangla
    text to standard UTF-8 Unicode.
    """

    # Typical Bijoy byte sequence markers that do not appear frequently in genuine English text
    BIJOY_CHARACTER_MARKERS = [
        "Av", "wK", "Ges", "cÖ", "hvi", "n‡e", "Kv‡Q", "Av‡Q",
        "GB", "Zvnv", "Dci", "cÖwZ", "e¨vsK", "A_©", "cwiPvjb",
        "evsjv", "evsjv‡`k", "FY", "†kÖwY", "mve©wK", "mvaviY"
    ]

    @classmethod
    def is_bijoy_encoded(cls, text: str) -> bool:
        """
        Determines whether the text appears to be encoded in legacy Bijoy ANSI.
        """
        if not text or len(text) < 10:
            return False
        
        # Count occurrences of Bijoy character combinations
        count = sum(1 for marker in cls.BIJOY_CHARACTER_MARKERS if marker in text)
        return count >= 2

    @classmethod
    def convert_to_unicode(cls, text: str) -> Tuple[str, bool]:
        """
        Converts text if Bijoy encoded.
        Returns: (converted_text, was_converted)
        """
        if not _bijoy or not cls.is_bijoy_encoded(text):
            return text, False

        try:
            converted = _bijoy.convertBijoyToUnicode(text)
            # Verify if conversion produced genuine Unicode Bangla characters
            has_bangla = any(0x0980 <= ord(c) <= 0x09FF for c in converted)
            if has_bangla:
                return converted, True
            return text, False
        except Exception as err:
            logger.warning(f"Bijoy conversion error: {err}")
            return text, False
