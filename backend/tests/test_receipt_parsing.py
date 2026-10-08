import re
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Tuple


class MatchConfidence(str, Enum):
    EXACT = "exact"
    HIGH = "high"
    UNCERTAIN = "uncertain"
    NONE = "none"


@dataclass
class MockProduct:
    id: int
    name: str
    brand: Optional[str] = None
    barcode: Optional[str] = None
    unit: str = "pcs"
    package_size: Optional[float] = None


@dataclass
class ReceiptLineItem:
    raw_text: str
    parsed_name: str
    unit_price: Optional[float] = None
    quantity: float = 1.0
    matched_product: Optional[MockProduct] = None
    confidence: MatchConfidence = MatchConfidence.NONE

    @property
    def line_total(self) -> Optional[float]:
        if self.unit_price is None:
            return None
        return round(self.quantity * self.unit_price, 2)

    @property
    def parsed_price(self) -> Optional[float]:
        return self.unit_price

    @parsed_price.setter
    def parsed_price(self, val: Optional[float]):
        self.unit_price = val


class ReceiptParser:
    """
    Python mirror of ReceiptScanner / ReceiptOCRService logic in Provision.
    """

    # Skip lines matching typical receipt headers/footers/metadata
    HEADER_FOOTER_KEYWORDS = [
        "TOTAL",
        "CASH",
        "CHANGE",
        "VAT",
        "SUBTOTAL",
        "RECEIPT",
        "THANK YOU",
        "INVOICE",
        "TIN#",
        "OR#",
        "POS#",
        "STORE",
        "SUPERMARKET",
        "MERCHANDISE",
        "ITEMS SOLD",
    ]

    # Regex patterns for multiplier layouts:
    # "2 @ 40.50", "2 @ 40.50 V", "2 x 45.00", "2 * 45.00", "2 PCS @ 45.00", "2PC @ 45.00"
    MULTIPLIER_REGEX = re.compile(
        r"(?:^|\s+)(\d+(?:\.\d+)?)\s*(?:@|[xX]|\*|(?:PCS?|PC)\s*@)\s*[P₱\s]*(\d+\.\d{2})\s*(?:[VBTvbt])?\s*$"
    )

    # Standard trailing price patterns: e.g. "45.50", "P120.00", "₱82.00", "99.00 V", "82.00 B"
    TRAILING_PRICE_REGEX = re.compile(
        r"[P₱\s]*(\d+\.\d{2})\s*(?:[VBTvbt])?\s*$"
    )

    @classmethod
    def is_header_or_footer(cls, line: str) -> bool:
        upper = line.upper()
        return any(kw in upper for kw in cls.HEADER_FOOTER_KEYWORDS)

    @classmethod
    def parse_line(
        cls, line: str, catalog: List[MockProduct]
    ) -> Optional[ReceiptLineItem]:
        trimmed = line.strip()
        if len(trimmed) < 3:
            return None

        if cls.is_header_or_footer(trimmed):
            return None

        extracted_qty = 1.0
        extracted_price: Optional[float] = None
        cleaned_name = trimmed

        # Check multiplier pattern first
        mult_match = cls.MULTIPLIER_REGEX.search(trimmed)
        if mult_match:
            try:
                extracted_qty = float(mult_match.group(1))
                extracted_price = float(mult_match.group(2))
                cleaned_name = trimmed[: mult_match.start()].strip()
            except (ValueError, IndexError):
                pass
        else:
            # Check trailing price pattern
            price_match = cls.TRAILING_PRICE_REGEX.search(trimmed)
            if price_match:
                try:
                    extracted_price = float(price_match.group(1))
                    cleaned_name = trimmed[: price_match.start()].strip()
                except (ValueError, IndexError):
                    pass

        if not cleaned_name:
            return None

        # Clean trailing symbols or punctuation from name
        cleaned_name = re.sub(r"[\s\-_@*]+$", "", cleaned_name).strip()
        if not cleaned_name:
            return None

        matched, confidence = cls.find_best_catalog_match(cleaned_name, catalog)

        # NEVER fall back to product.package_size for unit_price!
        return ReceiptLineItem(
            raw_text=line,
            parsed_name=matched.name if matched else cleaned_name,
            unit_price=extracted_price,  # Strictly extracted price or None
            quantity=extracted_qty,
            matched_product=matched,
            confidence=confidence,
        )

    @classmethod
    def find_best_catalog_match(
        cls, name: str, catalog: List[MockProduct]
    ) -> Tuple[Optional[MockProduct], MatchConfidence]:
        needle = name.lower().strip()
        needle_tokens = [t for t in re.split(r"[^a-zA-Z0-9]+", needle) if len(t) >= 3]
        needle_token_set = set(needle_tokens)

        # 1. Exact match by barcode or case-insensitive exact name
        for product in catalog:
            if product.barcode and product.barcode.lower() == needle:
                return (product, MatchConfidence.EXACT)
            if product.name.lower() == needle:
                return (product, MatchConfidence.EXACT)

        # 2. High confidence match:
        # - Full brand present + at least 1 keyword
        # - Or >= 2 significant tokens (len > 3) match
        for product in catalog:
            p_name = product.name.lower()
            p_tokens = [t for t in re.split(r"[^a-zA-Z0-9]+", p_name) if len(t) >= 3]
            p_token_set = set(p_tokens)

            # Check brand + keyword
            if product.brand:
                b = product.brand.lower()
                if b in needle:
                    remaining_tokens = [t for t in needle_tokens if t != b]
                    if any(t in p_name for t in remaining_tokens):
                        return (product, MatchConfidence.HIGH)

            # Check token overlap
            significant_needle = {t for t in needle_token_set if len(t) > 3}
            significant_prod = {t for t in p_token_set if len(t) > 3}
            overlap = significant_needle.intersection(significant_prod)
            if len(overlap) >= 2:
                return (product, MatchConfidence.HIGH)

        # 3. Uncertain confidence:
        # Single token overlap (e.g. only "tuna" or only "milk" matches)
        for product in catalog:
            p_name = product.name.lower()
            p_token_set = set(re.split(r"[^a-zA-Z0-9]+", p_name))
            overlap = needle_token_set.intersection(p_token_set)
            if len(overlap) >= 1:
                return (product, MatchConfidence.UNCERTAIN)

        return (None, MatchConfidence.NONE)

    @classmethod
    def parse_receipt_lines(
        cls, lines: List[str], catalog: List[MockProduct]
    ) -> List[ReceiptLineItem]:
        items: List[ReceiptLineItem] = []
        for line in lines:
            item = cls.parse_line(line, catalog)
            if item:
                items.append(item)
        return items

    @classmethod
    def deduplicate_and_merge(
        cls, items: List[ReceiptLineItem]
    ) -> List[ReceiptLineItem]:
        """
        Merges items with matching product IDs or identical parsed names/barcodes.
        Increments quantity, preserves or updates unit price.
        """
        merged_map = {}
        for item in items:
            key = None
            if item.matched_product and item.matched_product.id:
                key = f"prod_{item.matched_product.id}"
            elif item.matched_product and item.matched_product.barcode:
                key = f"bar_{item.matched_product.barcode}"
            else:
                key = f"name_{item.parsed_name.lower().strip()}"

            if key in merged_map:
                existing = merged_map[key]
                existing.quantity += item.quantity
                if item.unit_price is not None:
                    existing.unit_price = item.unit_price
            else:
                # Copy item
                merged_map[key] = ReceiptLineItem(
                    raw_text=item.raw_text,
                    parsed_name=item.parsed_name,
                    unit_price=item.unit_price,
                    quantity=item.quantity,
                    matched_product=item.matched_product,
                    confidence=item.confidence,
                )
        return list(merged_map.values())


# ==============================================================================
# TESTS
# ==============================================================================

def test_total_calculation_quantity_times_unit_price():
    """
    Requirement: Total calculation: total = quantity * unit_price
    (e.g. 2 * 45.00 = 90.00, not 45.00).
    """
    item1 = ReceiptLineItem(
        raw_text="2 @ 45.00",
        parsed_name="Item A",
        unit_price=45.0,
        quantity=2.0,
    )
    assert item1.line_total == 90.00
    assert item1.line_total != 45.00

    item2 = ReceiptLineItem(
        raw_text="3 x 102.50",
        parsed_name="Item B",
        unit_price=102.50,
        quantity=3.0,
    )
    assert item2.line_total == 307.50

    item_no_price = ReceiptLineItem(
        raw_text="Item without price",
        parsed_name="Item C",
        unit_price=None,
        quantity=2.0,
    )
    assert item_no_price.line_total is None


def test_package_size_removal_missing_price_is_none():
    """
    Requirement: Items with missing price have unit_price = None,
    never falling back to grams/milliliters package_size.
    """
    catalog = [
        MockProduct(
            id=1,
            name="Century Tuna Flakes in Oil",
            brand="Century",
            package_size=180.0,  # 180 grams - MUST NOT be used as price!
        ),
        MockProduct(
            id=2,
            name="Datu Puti Soy Sauce",
            brand="Datu Puti",
            package_size=1000.0,  # 1000 ml
        ),
    ]

    # Line without price OCR
    line = "CENTURY TUNA FLAKES IN OIL"
    item = ReceiptParser.parse_line(line, catalog)

    assert item is not None
    assert item.matched_product is not None
    assert item.matched_product.name == "Century Tuna Flakes in Oil"
    # Crucial assertion: unit_price MUST be None, NOT 180.0!
    assert item.unit_price is None
    assert item.line_total is None


def test_philippine_supermarket_layout_parsing():
    """
    Requirement: Support common Philippine supermarket receipt layouts
    (SM Megamall, Savemore, Puregold, Robinsons) including quantity multipliers
    like `2 @ 40.50`, `3 x 102.00`, trailing price `P40.50`, tax flags `82.00 V`.
    """
    catalog = [
        MockProduct(id=1, name="Century Tuna Flakes in Oil", brand="Century"),
        MockProduct(id=2, name="Purefoods Corned Beef", brand="Purefoods"),
        MockProduct(id=3, name="San Miguel Pale Pilsen", brand="San Miguel"),
        MockProduct(id=4, name="Gardenia Classic White Bread", brand="Gardenia"),
        MockProduct(id=5, name="Datu Puti Vinegar", brand="Datu Puti"),
    ]

    # SM / Savemore style with @ multiplier and VAT flags
    line_sm_mult = "CENTURY TUNA FLAKES    2 @ 40.50 V"
    item1 = ReceiptParser.parse_line(line_sm_mult, catalog)
    assert item1 is not None
    assert item1.quantity == 2.0
    assert item1.unit_price == 40.50
    assert item1.line_total == 81.00

    # Puregold style with 'x' multiplier
    line_puregold_mult = "PUREFOODS CORNED BEEF  3 x 92.00"
    item2 = ReceiptParser.parse_line(line_puregold_mult, catalog)
    assert item2 is not None
    assert item2.quantity == 3.0
    assert item2.unit_price == 92.00
    assert item2.line_total == 276.00

    # Robinsons style with 'PCS @'
    line_robinsons_mult = "SAN MIGUEL PALE PILSEN 6 PCS @ 52.00 B"
    item3 = ReceiptParser.parse_line(line_robinsons_mult, catalog)
    assert item3 is not None
    assert item3.quantity == 6.0
    assert item3.unit_price == 52.00
    assert item3.line_total == 312.00

    # Trailing price with Peso sign '₱' and tax flag 'T'
    line_peso_sign = "GARDENIA CLASSIC WHITE BREAD  ₱82.00 T"
    item4 = ReceiptParser.parse_line(line_peso_sign, catalog)
    assert item4 is not None
    assert item4.quantity == 1.0
    assert item4.unit_price == 82.00
    assert item4.line_total == 82.00

    # Trailing price with 'P' prefix
    line_p_prefix = "DATU PUTI VINEGAR  P48.00"
    item5 = ReceiptParser.parse_line(line_p_prefix, catalog)
    assert item5 is not None
    assert item5.quantity == 1.0
    assert item5.unit_price == 48.00
    assert item5.line_total == 48.00


def test_header_and_footer_filtering():
    """
    Verify that headers, footers, VAT summaries, TIN, OR# are filtered out.
    """
    headers_footers = [
        "SM SUPERMARKET MEGAMALL",
        "STORE #1029 OR# 982341",
        "TIN# 000-123-456-000",
        "SUBTOTAL   450.00",
        "12% VAT    54.00",
        "TOTAL AMOUNT 504.00",
        "CASH TENDERED 1000.00",
        "CHANGE DUE 496.00",
        "ITEMS SOLD: 5",
        "THANK YOU PLEASE COME AGAIN",
    ]
    catalog = []
    items = ReceiptParser.parse_receipt_lines(headers_footers, catalog)
    assert len(items) == 0


def test_match_confidence_exact_high_uncertain_none():
    """
    Requirement: Implement MatchConfidence (exact, high, uncertain, none).
    Distinguish exact match vs. single-token overlap (uncertain).
    """
    catalog = [
        MockProduct(id=1, name="Century Tuna Flakes in Oil", brand="Century", barcode="4800016552211"),
        MockProduct(id=2, name="Alaska Fortified Powdered Milk Drink", brand="Alaska"),
        MockProduct(id=3, name="Purefoods Tender Juicy Hotdog", brand="Purefoods"),
    ]

    # 1. Exact match by barcode
    prod, conf = ReceiptParser.find_best_catalog_match("4800016552211", catalog)
    assert conf == MatchConfidence.EXACT
    assert prod is not None and prod.id == 1

    # 2. Exact match by name (case-insensitive)
    prod, conf = ReceiptParser.find_best_catalog_match("purefoods tender juicy hotdog", catalog)
    assert conf == MatchConfidence.EXACT
    assert prod is not None and prod.id == 3

    # 3. High confidence: Brand + primary keyword
    prod, conf = ReceiptParser.find_best_catalog_match("ALASKA POWDERED MILK 1KG", catalog)
    assert conf == MatchConfidence.HIGH
    assert prod is not None and prod.id == 2

    # 4. High confidence: >= 2 significant tokens match
    prod, conf = ReceiptParser.find_best_catalog_match("CENTURY TUNA 180G", catalog)
    assert conf == MatchConfidence.HIGH
    assert prod is not None and prod.id == 1

    # 5. Uncertain confidence: Only 1 token overlap (e.g. just generic "hotdog" or "milk")
    prod, conf = ReceiptParser.find_best_catalog_match("GENERIC HOTDOG BUNS", catalog)
    assert conf == MatchConfidence.UNCERTAIN
    assert prod is not None and prod.id == 3  # Matches Purefoods Tender Juicy Hotdog on single token "hotdog"

    # 6. None confidence: No overlap
    prod, conf = ReceiptParser.find_best_catalog_match("COLGATE TOTAL TOOTHPASTE", catalog)
    assert conf == MatchConfidence.NONE
    assert prod is None


def test_deduplication_and_merging_quantities():
    """
    Requirement: Match receipt items against already scanned products
    to increment quantity rather than adding duplicate items.
    """
    product = MockProduct(id=1, name="Century Tuna Flakes in Oil", brand="Century")

    raw_items = [
        ReceiptLineItem(
            raw_text="CENTURY TUNA FLAKES 40.50",
            parsed_name="Century Tuna Flakes in Oil",
            unit_price=40.50,
            quantity=1.0,
            matched_product=product,
            confidence=MatchConfidence.HIGH,
        ),
        ReceiptLineItem(
            raw_text="CENTURY TUNA FLAKES 2 @ 40.50",
            parsed_name="Century Tuna Flakes in Oil",
            unit_price=40.50,
            quantity=2.0,
            matched_product=product,
            confidence=MatchConfidence.HIGH,
        ),
        ReceiptLineItem(
            raw_text="UNMATCHED SNACK 15.00",
            parsed_name="UNMATCHED SNACK",
            unit_price=15.00,
            quantity=1.0,
            matched_product=None,
            confidence=MatchConfidence.NONE,
        ),
    ]

    merged = ReceiptParser.deduplicate_and_merge(raw_items)

    assert len(merged) == 2
    merged_tuna = next(i for i in merged if i.matched_product and i.matched_product.id == 1)
    assert merged_tuna.quantity == 3.0  # 1.0 + 2.0 merged
    assert merged_tuna.unit_price == 40.50
    assert merged_tuna.line_total == 121.50

    unmatched = next(i for i in merged if i.matched_product is None)
    assert unmatched.quantity == 1.0
    assert unmatched.unit_price == 15.00
    assert unmatched.line_total == 15.00
