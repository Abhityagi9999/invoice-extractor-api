from dataclasses import dataclass

@dataclass
class ParsedPOInvoice:
    """Stores data extracted from a Purchase Order (PO) PDF."""
    advertiser_name: str = ""
    po_number: str = ""
    po_date: str = ""
    agency_name: str = ""
    brand: str = ""
    description: str = ""
    po_amount: float = 0.0
