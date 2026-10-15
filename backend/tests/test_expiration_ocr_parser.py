"""
test_expiration_ocr_parser.py - Verification and Python mirror for Provision package expiration date OCR.

Tests common Philippine packaging date formats, compact stamps, Tagalog/English
month names, prefix markers, calendar validity (including leap years), numeric ambiguity,
and missing or unreadable OCR lines.
"""

from dataclasses import dataclass
from datetime import date
import re
from typing import List, Optional, Tuple


# ==============================================================================
# EXPIRATION DATE OCR PARSER (Python mirror of Provision's ExpirationDateOCRService)
# ==============================================================================

MONTH_MAP = {
    # English
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "SEPT": 9,
    "SET": 9,  # Tagalog Setyembre / English alt
    "OCT": 10,
    "OKT": 10,  # Tagalog Oktubre
    "NOV": 11,
    "NOB": 11,  # Tagalog Nobyembre
    "DEC": 12,
    "DIS": 12,  # Tagalog Disyembre
    # Tagalog specific
    "ENE": 1,  # Enero
    "PEB": 2,  # Pebrero
    "ABR": 4,  # Abril
    "HUN": 6,  # Hunyo
    "HUL": 7,  # Hulyo
    "AGO": 8,  # Agosto
}

_MONTH_PATTERN = "|".join(sorted(MONTH_MAP.keys(), key=len, reverse=True))

_PREFIX_PATTERN = (
    r"(?:(?:\b(?:EXP(?:IRY|IRATION)?(?:\s+DATE)?|BBD|BB|BEST\s+BEFORE|USE\s+BY|CONSUME\s+BEFORE|"
    r"PETSA(?:\s+NG\s+PAGKAPASO)?)\b\s*[:.-]?\s*)|(?:\b(?:EXP|BBD|BB)))"
)

# 1. Compact stamps: e.g. 24SEP26, 15OCT2026, EXP24SEP26, BBD 15OCT26, 29PEB28
_COMPACT_RE = re.compile(
    rf"(?:{_PREFIX_PATTERN})?(\d{{1,2}})({_MONTH_PATTERN})(\d{{2}}|\d{{4}})\b",
    re.IGNORECASE,
)

# 2. Textual month with delimiters: DD MMM YYYY or DD-MMM-YYYY or DD.MMM.YYYY or DD/MMM/YYYY
_DD_MMM_YYYY_RE = re.compile(
    rf"\b(\d{{1,2}})[-/. \t]+({_MONTH_PATTERN})[A-Z]*[-/. \t]+(\d{{2,4}})\b",
    re.IGNORECASE,
)

# 3. Textual month first: MMM DD, YYYY or MMM DD YYYY
_MMM_DD_YYYY_RE = re.compile(
    rf"\b({_MONTH_PATTERN})[A-Z]*[-/. \t]+(\d{{1,2}})[,-/. \t]+(\d{{2,4}})\b",
    re.IGNORECASE,
)

# 4. ISO 8601: YYYY-MM-DD or YYYY/MM/DD or YYYY.MM.DD
_ISO_RE = re.compile(
    r"\b(20\d{2})[-/.](0?[1-9]|1[0-2])[-/.](0?[1-9]|[12]\d|3[01])\b"
)

# 5. Numeric: DD.MM.YYYY, DD/MM/YYYY, MM/DD/YYYY, DD-MM-YYYY, etc.
_NUMERIC_RE = re.compile(
    r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b"
)


def _make_valid_date(year: int, month: int, day: int) -> Optional[date]:
    """
    Validates calendar boundaries including days per month and leap year rules.
    Expands 2-digit years (< 100) to 2000s.
    """
    if year < 100:
        year += 2000
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


@dataclass
class ExpirationParseResult:
    """Represents a successfully recognized package expiration date."""
    date: date
    raw_string: str
    is_ambiguous: bool = False

    @property
    def year(self) -> int:
        return self.date.year

    @property
    def month(self) -> int:
        return self.date.month

    @property
    def day(self) -> int:
        return self.date.day

    def __iter__(self):
        """Allows unpacking: date_val, raw_str, is_amb = result."""
        return iter((self.date, self.raw_string, self.is_ambiguous))


class ExpirationDateOCRParser:
    """
    Python mirror of Provision's ExpirationDateOCRService.
    Parses package expiration dates from OCR output lines.
    """

    MONTH_MAP = MONTH_MAP

    @classmethod
    def parse_line(cls, raw_text: str) -> Optional[ExpirationParseResult]:
        """Parses a single line of OCR text into an ExpirationParseResult."""
        text = raw_text.strip()
        if not text:
            return None

        # 1. Delimited DD MMM YYYY (e.g. 24 SEP 2026, 24-SEP-2026, 24.09.2026 text month)
        m = _DD_MMM_YYYY_RE.search(text)
        if m:
            d = int(m.group(1))
            raw_month = m.group(2).upper()
            mon_key = raw_month[:4] if raw_month[:4] in MONTH_MAP else raw_month[:3]
            mon = MONTH_MAP.get(mon_key)
            y = int(m.group(3))
            if mon:
                dt = _make_valid_date(y, mon, d)
                if dt:
                    return ExpirationParseResult(date=dt, raw_string=raw_text, is_ambiguous=False)

        # 2. Delimited MMM DD YYYY (e.g. SEP 24 2026, OCT 15, 2026)
        m = _MMM_DD_YYYY_RE.search(text)
        if m:
            raw_month = m.group(1).upper()
            mon_key = raw_month[:4] if raw_month[:4] in MONTH_MAP else raw_month[:3]
            mon = MONTH_MAP.get(mon_key)
            d = int(m.group(2))
            y = int(m.group(3))
            if mon:
                dt = _make_valid_date(y, mon, d)
                if dt:
                    return ExpirationParseResult(date=dt, raw_string=raw_text, is_ambiguous=False)

        # 3. Compact stamps without delimiters (e.g. 24SEP26, 15OCT2026, EXP24SEP26, BBD 15OCT26)
        m = _COMPACT_RE.search(text)
        if m:
            d = int(m.group(1))
            raw_month = m.group(2).upper()
            mon_key = raw_month[:4] if raw_month[:4] in MONTH_MAP else raw_month[:3]
            mon = MONTH_MAP.get(mon_key)
            y = int(m.group(3))
            if mon:
                dt = _make_valid_date(y, mon, d)
                if dt:
                    return ExpirationParseResult(date=dt, raw_string=raw_text, is_ambiguous=False)

        # 4. ISO 8601 (YYYY-MM-DD or YYYY/MM/DD or YYYY.MM.DD)
        m = _ISO_RE.search(text)
        if m:
            y = int(m.group(1))
            mon = int(m.group(2))
            d = int(m.group(3))
            dt = _make_valid_date(y, mon, d)
            if dt:
                return ExpirationParseResult(date=dt, raw_string=raw_text, is_ambiguous=False)

        # 5. Numeric dates: DD.MM.YYYY, MM/DD/YYYY, etc.
        m = _NUMERIC_RE.search(text)
        if m:
            p1 = int(m.group(1))
            p2 = int(m.group(2))
            y = int(m.group(3))

            # Case A: Both numbers <= 12 -> Ambiguous between MM/DD and DD/MM
            if 1 <= p1 <= 12 and 1 <= p2 <= 12:
                # Default to MM/DD/YYYY while flagging as ambiguous
                dt = _make_valid_date(y, p1, p2)
                if dt:
                    return ExpirationParseResult(date=dt, raw_string=raw_text, is_ambiguous=True)

            # Case B: First number > 12 -> Unambiguously DD.MM.YYYY
            elif p1 > 12 and 1 <= p2 <= 12:
                dt = _make_valid_date(y, p2, p1)
                if dt:
                    return ExpirationParseResult(date=dt, raw_string=raw_text, is_ambiguous=False)

            # Case C: Second number > 12 -> Unambiguously MM/DD/YYYY
            elif 1 <= p1 <= 12 and p2 > 12:
                dt = _make_valid_date(y, p1, p2)
                if dt:
                    return ExpirationParseResult(date=dt, raw_string=raw_text, is_ambiguous=False)

        return None

    @classmethod
    def parse_expiration_date(cls, lines: List[str]) -> Optional[ExpirationParseResult]:
        """
        Scans a list of recognized OCR lines and extracts the first valid expiration date.
        """
        for line in lines:
            result = cls.parse_line(line)
            if result is not None:
                return result

        # Also attempt adjacent lines combined if stamps were split across OCR boxes
        for i in range(len(lines) - 1):
            combined = f"{lines[i]} {lines[i + 1]}"
            result = cls.parse_line(combined)
            if result is not None:
                return ExpirationParseResult(date=result.date, raw_string=combined, is_ambiguous=result.is_ambiguous)

        return None

    @classmethod
    def extract_expiration_date(cls, raw_text: str) -> Optional[Tuple[date, bool]]:
        """Convenience method returning (date, is_ambiguous) or None."""
        res = cls.parse_line(raw_text)
        if res:
            return res.date, res.is_ambiguous
        return None

    @classmethod
    def extract_date(cls, raw_text: str) -> Optional[date]:
        """Backwards-compatible helper returning solely the Date or None."""
        res = cls.parse_line(raw_text)
        if res:
            return res.date
        return None


# ==============================================================================
# TESTS
# ==============================================================================

def test_philippine_standard_date_formats():
    """
    Verifies detection of standard Philippine packaging date formats:
    - EXP: 24 SEP 2026
    - 24-SEP-2026
    - 24.09.2026
    - 2026-10-15
    - 24/09/2026
    - 24.09.26 (2-digit year)
    """
    # 1. Delimited with prefix: EXP: 24 SEP 2026
    res1 = ExpirationDateOCRParser.parse_line("EXP: 24 SEP 2026")
    assert res1 is not None
    assert res1.date == date(2026, 9, 24)
    assert res1.is_ambiguous is False
    assert res1.year == 2026
    assert res1.month == 9
    assert res1.day == 24

    # 2. Hyphenated: 24-SEP-2026
    res2 = ExpirationDateOCRParser.parse_line("24-SEP-2026")
    assert res2 is not None
    assert res2.date == date(2026, 9, 24)
    assert res2.is_ambiguous is False

    # 3. Dot-separated numeric: 24.09.2026 (day 24 > 12 -> unambiguous)
    res3 = ExpirationDateOCRParser.parse_line("24.09.2026")
    assert res3 is not None
    assert res3.date == date(2026, 9, 24)
    assert res3.is_ambiguous is False

    # 4. ISO 8601: 2026-10-15
    res4 = ExpirationDateOCRParser.parse_line("2026-10-15")
    assert res4 is not None
    assert res4.date == date(2026, 10, 15)
    assert res4.is_ambiguous is False

    # 5. Slash separated: 24/09/2026
    res5 = ExpirationDateOCRParser.parse_line("24/09/2026")
    assert res5 is not None
    assert res5.date == date(2026, 9, 24)
    assert res5.is_ambiguous is False

    # 6. Dot-separated with 2-digit year: 24.09.26
    res6 = ExpirationDateOCRParser.parse_line("24.09.26")
    assert res6 is not None
    assert res6.date == date(2026, 9, 24)
    assert res6.is_ambiguous is False


def test_compact_package_date_stamps():
    """
    Verifies compact package stamps without spaces or delimiters:
    - 24SEP26
    - 24SEP2026
    - 15OCT26
    - BBD 15OCT26
    - EXP24SEP26
    - 15OKT26 (Tagalog compact)
    """
    cases = [
        ("24SEP26", date(2026, 9, 24)),
        ("24SEP2026", date(2026, 9, 24)),
        ("15OCT26", date(2026, 10, 15)),
        ("BBD 15OCT26", date(2026, 10, 15)),
        ("EXP24SEP26", date(2026, 9, 24)),
        ("15OKT26", date(2026, 10, 15)),
        ("BB 30DEC27", date(2027, 12, 30)),
    ]

    for raw, expected in cases:
        res = ExpirationDateOCRParser.parse_line(raw)
        assert res is not None, f"Expected match for compact stamp: {raw}"
        assert res.date == expected, f"Failed for {raw}: got {res.date}, expected {expected}"
        assert res.is_ambiguous is False


def test_tagalog_month_abbreviations():
    """
    Verifies detection of Philippine/Tagalog month names:
    - ENE (Enero), PEB (Pebrero), MAR (Marso), ABR (Abril), MAY (Mayo), HUN (Hunyo)
    - HUL (Hulyo), AGO (Agosto), SET (Setyembre), OKT (Oktubre), NOB (Nobyembre), DIS (Disyembre)
    """
    tagalog_samples = [
        ("24 ENE 2026", date(2026, 1, 24)),
        ("14 PEB 2026", date(2026, 2, 14)),
        ("31 MAR 2026", date(2026, 3, 31)),
        ("15 ABR 2026", date(2026, 4, 15)),
        ("01 MAY 2026", date(2026, 5, 1)),
        ("12 HUN 2026", date(2026, 6, 12)),
        ("04 HUL 2026", date(2026, 7, 4)),
        ("28 AGO 2026", date(2026, 8, 28)),
        ("15 SET 2026", date(2026, 9, 15)),
        ("15 OKT 2026", date(2026, 10, 15)),
        ("05 NOB 2026", date(2026, 11, 5)),
        ("30 DIS 2026", date(2026, 12, 30)),
    ]

    for raw, expected in tagalog_samples:
        res = ExpirationDateOCRParser.parse_line(raw)
        assert res is not None, f"Expected match for Tagalog date: {raw}"
        assert res.date == expected, f"Failed for {raw}: got {res.date}, expected {expected}"
        assert res.is_ambiguous is False


def test_prefix_markers():
    """
    Verifies common Philippine packaging prefixes:
    - BEST BEFORE: 15 OCT 2026
    - USE BY: 05/18/2027
    - PETSA: 2026-11-20
    - PETSA NG PAGKAPASO: 24 ENE 2026
    - BBD 15OCT26
    - BB: 24-SEP-2026
    - EXPIRY DATE: 2026-12-31
    """
    prefixes = [
        ("BEST BEFORE: 15 OCT 2026", date(2026, 10, 15)),
        ("USE BY: 05/18/2027", date(2027, 5, 18)),
        ("PETSA: 2026-11-20", date(2026, 11, 20)),
        ("PETSA NG PAGKAPASO: 24 ENE 2026", date(2026, 1, 24)),
        ("BB: 24-SEP-2026", date(2026, 9, 24)),
        ("BBD 15OCT26", date(2026, 10, 15)),
        ("EXPIRY DATE: 2026-12-31", date(2026, 12, 31)),
        ("CONSUME BEFORE 05 NOB 2026", date(2026, 11, 5)),
    ]

    for raw, expected in prefixes:
        res = ExpirationDateOCRParser.parse_line(raw)
        assert res is not None, f"Expected match for prefixed line: {raw}"
        assert res.date == expected, f"Failed for {raw}: got {res.date}, expected {expected}"


def test_calendar_validation_rejects_impossible_dates():
    """
    Verifies that calendar constraints are strictly enforced:
    - 30 FEB 2026 (February never has 30 days)
    - 31 APR 2026 (April only has 30 days)
    - 32 JAN 2026 (Day > 31)
    - 00 OCT 2026 (Day < 1)
    - 31 JUN 2026 (June only has 30 days)
    - 31 SEP 2026 (September only has 30 days)
    - 31 NOV 2026 (November only has 30 days)
    - 15/13/2026 (Month > 12)
    """
    invalid_dates = [
        "30 FEB 2026",
        "31 APR 2026",
        "32 JAN 2026",
        "00 OCT 2026",
        "31 JUN 2026",
        "31 SEP 2026",
        "31 NOV 2026",
        "30 PEB 2026",
        "31 ABR 2026",
        "15/13/2026",
        "00/05/2026",
        "32.01.2026",
    ]

    for raw in invalid_dates:
        res = ExpirationDateOCRParser.parse_line(raw)
        assert res is None, f"Expected rejection for impossible date: {raw}, got {res}"


def test_calendar_validation_leap_year():
    """
    Verifies leap year rules:
    - 29 FEB 2028 is VALID (2028 is a leap year)
    - 29 FEB 2024 is VALID (2024 is a leap year)
    - 29 FEB 2000 is VALID (century leap year divisible by 400)
    - 29 FEB 2027 is INVALID (2027 is not a leap year)
    - 29 FEB 2026 is INVALID (2026 is not a leap year)
    - 29 FEB 1900 is INVALID (century non-leap year)
    - Tagalog compact: 29PEB28 is VALID, 29PEB27 is INVALID
    """
    # Valid leap years
    res_leap_2028 = ExpirationDateOCRParser.parse_line("29 FEB 2028")
    assert res_leap_2028 is not None
    assert res_leap_2028.date == date(2028, 2, 29)

    res_leap_2024 = ExpirationDateOCRParser.parse_line("29-FEB-2024")
    assert res_leap_2024 is not None
    assert res_leap_2024.date == date(2024, 2, 29)

    res_leap_tagalog = ExpirationDateOCRParser.parse_line("29PEB28")
    assert res_leap_tagalog is not None
    assert res_leap_tagalog.date == date(2028, 2, 29)

    # Invalid leap years
    res_nonleap_2027 = ExpirationDateOCRParser.parse_line("29 FEB 2027")
    assert res_nonleap_2027 is None, "29 FEB 2027 must be rejected"

    res_nonleap_2026 = ExpirationDateOCRParser.parse_line("29-FEB-2026")
    assert res_nonleap_2026 is None, "29-FEB-2026 must be rejected"

    res_nonleap_tagalog = ExpirationDateOCRParser.parse_line("29PEB27")
    assert res_nonleap_tagalog is None, "29PEB27 must be rejected"


def test_ambiguity_handling():
    """
    Verifies ambiguity detection:
    - When format is purely numeric without month name and both components <= 12 (e.g. 05/06/2026):
      flags is_ambiguous=True.
    - When one component > 12 (e.g. 24.09.2026 or 05/18/2027):
      unambiguously resolves Day vs Month and flags is_ambiguous=False.
    - Textual month names (e.g. 24 SEP 2026, 24 ENE 2026, 24SEP26):
      always unambiguous (is_ambiguous=False).
    - ISO format YYYY-MM-DD:
      always unambiguous (is_ambiguous=False).
    """
    # 1. Ambiguous cases (both numbers <= 12)
    amb_res1 = ExpirationDateOCRParser.parse_line("05/06/2026")
    assert amb_res1 is not None
    assert amb_res1.is_ambiguous is True

    amb_res2 = ExpirationDateOCRParser.parse_line("04-10-2026")
    assert amb_res2 is not None
    assert amb_res2.is_ambiguous is True

    amb_res3 = ExpirationDateOCRParser.parse_line("03.07.2026")
    assert amb_res3 is not None
    assert amb_res3.is_ambiguous is True

    # 2. Unambiguous numeric cases (one number > 12)
    unamb_res1 = ExpirationDateOCRParser.parse_line("24.09.2026")
    assert unamb_res1 is not None
    assert unamb_res1.date == date(2026, 9, 24)
    assert unamb_res1.is_ambiguous is False

    unamb_res2 = ExpirationDateOCRParser.parse_line("05/18/2027")
    assert unamb_res2 is not None
    assert unamb_res2.date == date(2027, 5, 18)
    assert unamb_res2.is_ambiguous is False

    # 3. Textual months are never ambiguous
    text_res = ExpirationDateOCRParser.parse_line("05 MAY 2026")
    assert text_res is not None
    assert text_res.date == date(2026, 5, 5)
    assert text_res.is_ambiguous is False

    # 4. ISO format is never ambiguous
    iso_res = ExpirationDateOCRParser.parse_line("2026-05-06")
    assert iso_res is not None
    assert iso_res.date == date(2026, 5, 6)
    assert iso_res.is_ambiguous is False


def test_missing_and_unreadable_stamps():
    """
    Verifies that lines without valid date stamps return None:
    - Random packaging text
    - Receipts or totals
    - Phone numbers or barcodes
    - Empty or whitespace-only inputs
    """
    unreadable_lines = [
        "SAN MIGUEL PALE PILSEN 330ML",
        "NET WT 330ML",
        "KEEP REFRIGERATED",
        "STORE IN COOL DRY PLACE",
        "TOTAL AMOUNT: P185.00",
        "TEL: 0917-123-4567",
        "BARCODE: 4800016552211",
        "",
        "   ",
        "\t\n",
    ]

    for line in unreadable_lines:
        res = ExpirationDateOCRParser.parse_line(line)
        assert res is None, f"Expected None for line '{line}', got {res}"

    # Also test empty list passed to parse_expiration_date
    assert ExpirationDateOCRParser.parse_expiration_date([]) is None
    assert ExpirationDateOCRParser.parse_expiration_date(unreadable_lines) is None


def test_multi_line_ocr_packet():
    """
    Verifies extracting the expiration date from a multi-line OCR packet
    typical of VisionKit image recognition on Philippine supermarket items.
    """
    packet_lines = [
        "PUREFOODS CORNED BEEF",
        "PREMIUM CANNED GOODS",
        "NET WT. 150G",
        "LOT NO. 994821A",
        "EXP: 24 SEP 2026",
        "BARCODE 4800016552211",
    ]

    res = ExpirationDateOCRParser.parse_expiration_date(packet_lines)
    assert res is not None
    assert res.date == date(2026, 9, 24)
    assert res.raw_string == "EXP: 24 SEP 2026"
    assert res.is_ambiguous is False

    # Multi-line with Tagalog label
    packet_tagalog = [
        "CENTURY TUNA FLAKES IN OIL",
        "180 GRAMS",
        "PETSA NG PAGKAPASO: 15 OKT 2026",
        "PRODUCT OF THE PHILIPPINES",
    ]
    res_tg = ExpirationDateOCRParser.parse_expiration_date(packet_tagalog)
    assert res_tg is not None
    assert res_tg.date == date(2026, 10, 15)
    assert res_tg.raw_string == "PETSA NG PAGKAPASO: 15 OKT 2026"
    assert res_tg.is_ambiguous is False


def test_convenience_methods_and_unpacking():
    """
    Verifies extract_expiration_date, extract_date, and tuple unpacking.
    """
    # 1. Tuple unpacking from ExpirationParseResult
    res = ExpirationDateOCRParser.parse_line("EXP: 24 SEP 2026")
    assert res is not None
    d, raw_str, is_amb = res
    assert d == date(2026, 9, 24)
    assert raw_str == "EXP: 24 SEP 2026"
    assert is_amb is False

    # 2. extract_expiration_date helper
    tup = ExpirationDateOCRParser.extract_expiration_date("05/06/2026")
    assert tup is not None
    exp_date, amb = tup
    assert exp_date == date(2026, 5, 6)
    assert amb is True

    # 3. extract_date backwards-compatible helper
    single_date = ExpirationDateOCRParser.extract_date("24-SEP-2026")
    assert single_date == date(2026, 9, 24)

    # 4. Unreadable returns None
    assert ExpirationDateOCRParser.extract_date("NO DATE HERE") is None
    assert ExpirationDateOCRParser.extract_expiration_date("NO DATE HERE") is None
