import re
from .normalize import fa_to_en


def normalize_numeric_text(text: str) -> str:
    """Prepare a string that contains numeric data for reliable parsing."""
    if not isinstance(text, str):
        return ""

    t = fa_to_en(text)
    t = t.replace("،", ",")

    # Remove thousand separators like 1,200 -> 1200 while keeping decimal commas.
    t = re.sub(r"(\d),(?=\d{3}(?:\D|$))", r"\1", t)

    # Convert remaining commas to dots to support decimal comma formats.
    t = t.replace(",", ".")

    # Normalise minus signs or other unicode dashes.
    t = t.replace("−", "-")

    # Treat ranges such as 3983-3989 as separate numbers instead of negatives.
    t = re.sub(r"(?<=\d)-(\s*)?(?=\d)", " ", t)

    return t


def extract_numbers(text: str) -> list[float]:
    """Extract floating point numbers from a text block."""
    normalised = normalize_numeric_text(text)
    matches = re.findall(r"-?\d+(?:\.\d+)?", normalised)
    return [float(m) for m in matches]
