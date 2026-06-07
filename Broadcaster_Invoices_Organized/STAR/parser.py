import re
from typing import List
import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from broadcaster_types import ParsedBroadcasterInvoice, BroadcasterSpot, _extract, _clean, _clean_air_time, _parse_num, _get_day_from_date

def parse(pages_text: List[str], full_text: str) -> ParsedBroadcasterInvoice:
    result = ParsedBroadcasterInvoice(format_type='star')
    h = result.header

    h.broadcaster_name = "Star India Pvt. Ltd."

    # ── Parse header from full_text (Star PDFs have multi-column table layout,
    #    where labels and values are on different lines) ──

    # Advertiser: appears after "Advertiser" label, spans to next label
    adv_m = re.search(
        r'Advertiser\s+Agency.*?\n'
        r'((?:XIAOMI|[A-Z][A-Z ]+)(?:\s+(?:TECHNOLOGY|INDIA|PRIVATE|LIMITED|PVT|LTD))*)',
        full_text, re.IGNORECASE
    )
    if adv_m:
        # Get the full advertiser name which may span 2 lines
        adv_name = _clean(adv_m.group(1))
        # Check next line for continuation (e.g., "PRIVATE LIMITED")
        after_adv = full_text[adv_m.end():]
        cont_m = re.match(r'\s*((?:PRIVATE|LIMITED|PVT|LTD|TECHNOLOGY|INDIA)\s*(?:PRIVATE|LIMITED|PVT|LTD|TECHNOLOGY|INDIA)*)', after_adv, re.IGNORECASE)
        if cont_m:
            adv_name += ' ' + _clean(cont_m.group(1))
        h.advertiser_name = adv_name

    # Invoice Number (O-prefix, 10+ digits)
    inv_m = re.search(r'\bO\d{10,}\b', full_text)
    if inv_m:
        h.invoice_number = inv_m.group(0)

    # Station Relation / Channel — on the same line as invoice number
    # Format: "O03300262172 MAA HD South-SIPL"
    stn_m = re.search(
        r'O\d{10,}\s+([A-Z][A-Za-z0-9 ]+?)\s+(?:South|North|East|West|National)',
        full_text
    )
    if stn_m:
        h.channel_name = _clean(stn_m.group(1))
    else:
        # Try from STN column in spot data
        stn_m2 = re.search(r'STN\b.*?\n.*?Spot Buys\s+(\w+)', full_text, re.DOTALL)
        if stn_m2:
            h.channel_name = stn_m2.group(1)

    # Invoice Date — format: dd/mm/yyyy after "Invoice Date"
    dt_m = re.search(r'Invoice\s+Date\s+.*?\n\s*.*?(\d{1,2}/\d{1,2}/\d{4})', full_text, re.DOTALL)
    if dt_m:
        h.invoice_date = dt_m.group(1)

    # Billing Period — the date pattern dd/mm/yyyy- dd/mm/yyyy appears on the line after "Billing Period"
    # but may be preceded by address text on the same line
    bp_m = re.search(r'Billing\s+Period.*?\n.*?(\d{1,2}/\d{1,2}/\d{4}\s*-\s*\d{1,2}/\d{1,2}/\d{4})', full_text, re.DOTALL)
    if bp_m:
        h.billing_period = re.sub(r'\s+', '', bp_m.group(1))

    # PO Number — appears after the billing period dates on the same line
    po_m = re.search(r'PO\s+Number.*?\n.*?([A-Z]+\d{4}/\w+/\d+/\s*\d*)', full_text, re.DOTALL)
    if not po_m:
        po_m = re.search(r'PO\s+Number.*?\n.*?(\S+/\S+/\S+)', full_text, re.DOTALL)
    if po_m:
        h.po_number = _clean(po_m.group(1))

    # Agency
    h.agency_name = _extract(full_text, r'(GROUP\s*M\s*MEDIA\s*INDIA\s*(?:PVT|PRIVATE)?\.?\s*(?:LTD|LIMITED)\.?[\s(]*(?:BA)?[\s)]*)', default="GROUP M MEDIA INDIA PVT. LTD.")
    if not h.advertiser_name or 'Agency' in h.advertiser_name or h.advertiser_name.strip().upper() == 'XIAOMI TECHNOLOGY INDIA':
        h.advertiser_name = _extract(full_text, r'(XIAOMI\s+TECHNOLOGY\s+INDIA\s+(?:PRIVATE\s+)?(?:LIMITED|LTD))', default="XIAOMI TECHNOLOGY INDIA PRIVATE LIMITED")

    # Brand
    h.brand = "Xiaomi"

    # Parse spot table — Star India format
    # Lines look like: 9390385 9 Spot Buys HMAI (...) PROGRAM_NAME [...] DD/MM/YYYY Day HH:MM:SS:FF DUR CAPTION Brand Rate
    current_tp = ""
    current_program_name = ""

    for page_text in pages_text:
        lines = page_text.split('\n')
        for line in lines:
            ls = line.strip()
            if not ls:
                continue

            # Skip headers/footers
            if any(skip in ls for skip in ['ORDER_ID', 'Page ', 'Star India', 'Tax Invoice',
                                            'Original For', 'GSTIN', 'PAN No', 'HSN Code',
                                            'We warrant', 'Help?', 'Printed:', 'signed',
                                            'payments.', 'KARNATAKA', 'Place of Supply']):
                continue

            # Extract TP from time range in parentheses
            tp_m = re.search(r'\((\d{2}:\d{2}-\d{2}:\d{2})\)', ls)
            if tp_m:
                current_tp = tp_m.group(1)

            # Extract program name (text before [CHANNEL_NAME])
            prog_m = re.search(r'([A-Z][A-Z\s\-0-9]+?)\s+\[([^\]]+)\]', ls)
            if prog_m:
                current_program_name = _clean(prog_m.group(1))

            # Find spot data: DATE DAY TIME DUR ... RATE
            spot_m = re.search(
                r'(\d{1,2}/\d{1,2}/\d{4})\s+'           # Date
                r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s*'       # Day
                r'\w?\s*'                                  # Optional extra char
                r'(\d{1,2}:\d{2}:\d{2}(?::\d{2})?)\s+'    # Air Time
                r'(\d{1,2})\s+'                            # Duration
                r'(.*?)'                                   # Spot Copy
                r'\s+(\w+)\s+'                             # Brand
                r'([\d,]+\.\d{2})\s*$',                    # Rate
                ls, re.IGNORECASE
            )

            if spot_m:
                spot = BroadcasterSpot()
                spot.date = spot_m.group(1)
                spot.day = spot_m.group(2).capitalize()
                spot.air_time = _clean_air_time(spot_m.group(3))
                spot.duration = int(spot_m.group(4))
                spot.spot_copy = _clean(spot_m.group(5))
                spot.brand = spot_m.group(6)
                spot.rate = _parse_num(spot_m.group(7))
                spot.amount = spot.rate  # Star rates are per spot
                spot.tp = current_tp
                spot.program = current_program_name
                result.spots.append(spot)

    h.total_spots = len(result.spots)
    h.net_amount = sum(s.amount for s in result.spots)
    return result
