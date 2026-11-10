"""Egyptian phone number normalisation.

Stored format is the national mobile form `01XXXXXXXXX` (11 digits).
Accepts Arabic-Indic digits, spaces/dashes, and +20 / 0020 prefixes.
"""

from __future__ import annotations

import re

_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_EG_MOBILE = re.compile(r"^01[0125]\d{8}$")


class InvalidPhoneError(ValueError):
    pass


def normalize_phone(raw: str) -> str:
    value = raw.translate(_ARABIC_INDIC)
    value = re.sub(r"[\s\-().]", "", value)
    if value.startswith("+20"):
        value = "0" + value[3:]
    elif value.startswith("0020"):
        value = "0" + value[4:]
    elif value.startswith("20") and len(value) == 12:
        value = "0" + value[2:]
    if not _EG_MOBILE.match(value):
        raise InvalidPhoneError("رقم الهاتف غير صحيح، استخدم رقم موبايل مصري مثل 01012345678")
    return value


def mask_phone(phone: str) -> str:
    """For audit metadata about unknown accounts: keep only the last 3 digits."""
    return "*" * max(len(phone) - 3, 0) + phone[-3:]
