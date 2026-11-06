"""Arabic text normalisation helpers."""

from __future__ import annotations

import re
import unicodedata

ARABIC_INDIC_DIGITS = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789",
)

# Letter variants that people type interchangeably on plates and in names:
# alef forms -> alef, alef maqsura -> yeh, teh marbuta -> heh, hamza seats.
_LETTER_FOLD = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ة": "ه",
        "ؤ": "و",
        "ئ": "ي",
    }
)
# Tatweel and Arabic diacritics.
_TATWEEL_AND_MARKS = re.compile("[ـً-ٰٟ]")
_PLATE_ALLOWED = re.compile("[^0-9A-Zء-ي]")


def to_latin_digits(value: str) -> str:
    return value.translate(ARABIC_INDIC_DIGITS)


def collapse_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def plate_key(plate: str) -> str:
    """Canonical key for plate uniqueness: 'أ ب ج ١٢٣٤' == 'ا-ب-ج 1234'."""
    value = unicodedata.normalize("NFKC", plate)
    value = _TATWEEL_AND_MARKS.sub("", value)
    value = to_latin_digits(value).translate(_LETTER_FOLD).upper()
    return _PLATE_ALLOWED.sub("", value)


EG_NATIONAL_ID = re.compile(r"^[23]\d{13}$")


def normalize_national_id(value: str) -> str:
    """Egyptian national ID: 14 digits, first digit is the birth century (2/3)."""
    digits = re.sub(r"\D", "", to_latin_digits(value))
    if not EG_NATIONAL_ID.match(digits):
        raise ValueError("الرقم القومي يجب أن يتكون من 14 رقمًا")
    return digits
