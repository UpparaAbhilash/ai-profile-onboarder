"""Remove government ID numbers BEFORE text leaves our server.

Only the last 4 digits of an Aadhaar number are kept, for masked display
(XXXX-XXXX-1234). The full number is never stored and never sent to the AI.
"""
import re
from dataclasses import dataclass

REDACTED = "[REDACTED-ID]"

# 12 digits, first digit 2-9, optionally grouped 4-4-4, written after a label.
AADHAAR_WITH_LABEL = re.compile(
    r"(?i)\b(?:aadhaa?r|uid)\b[^\d\n]{0,30}([2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4})\b"
)
# The typical printed format "2345 6789 0123" even without a label.
# Separators are required here so 12-digit phone numbers are not matched.
AADHAAR_SPACED = re.compile(r"\b([2-9]\d{3}[ -]\d{4}[ -]\d{4})\b")


@dataclass(frozen=True)
class RedactionResult:
    text: str
    aadhaar_last4: str | None


def redact_sensitive_ids(text: str) -> RedactionResult:
    last4 = None

    def replace(match: re.Match) -> str:
        nonlocal last4
        number = match.group(1)
        if last4 is None:
            last4 = re.sub(r"\D", "", number)[-4:]
        return match.group(0).replace(number, REDACTED)

    text = AADHAAR_WITH_LABEL.sub(replace, text)
    text = AADHAAR_SPACED.sub(replace, text)
    return RedactionResult(text=text, aadhaar_last4=last4)