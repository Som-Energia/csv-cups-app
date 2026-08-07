CANONICAL_CUPS_LENGTH = 20
ACCEPTED_API_CUPS_LENGTHS = frozenset((20, 22))


def canonicalize_import_cups(cups: str) -> str:
    """Validate an imported CUPS and return its canonical storage representation."""
    normalized_cups = cups.strip()
    if len(normalized_cups) not in ACCEPTED_API_CUPS_LENGTHS:
        raise ValueError("CUPS must contain exactly 20 or 22 characters.")
    return normalized_cups[:CANONICAL_CUPS_LENGTH]


def canonicalize_lookup_cups(cups: str) -> str:
    """Canonicalize complete CUPS values while retaining partial HTML search input."""
    normalized_cups = cups.strip()
    if len(normalized_cups) in ACCEPTED_API_CUPS_LENGTHS:
        return canonicalize_import_cups(normalized_cups)
    return normalized_cups


def canonicalize_api_cups(cups: str) -> str:
    """Validate an API CUPS input and return its canonical database lookup value."""
    return canonicalize_import_cups(cups)
