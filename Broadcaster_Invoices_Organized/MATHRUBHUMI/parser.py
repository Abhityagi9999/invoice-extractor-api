import re
from typing import List
import sys
import os
sys.path.append('c:/Users/asus/OneDrive/Desktop/New folder (6)')
from broadcaster_types import ParsedBroadcasterInvoice, BroadcasterSpot, _extract, _clean, _clean_air_time, _parse_num, _get_day_from_date

def parse(pages_text: List[str], full_text: str) -> ParsedBroadcasterInvoice:
    result = ParsedBroadcasterInvoice(format_type='mathrubhumi')
    h = result.header

    h.broadcaster_name = "The Mathrubhumi Printing & Publishing Co. Ltd."
    h.advertiser_name = _extract(full_text, r'Advertiser\s*:?\s*([\w\s]+(?:PVT|PRIVATE)\s*(?:LTD|LIMITED))', default="XIAOMI TECHNOLOGY INDIA PRIVATE LIMITED")
    h.agency_name = _extract(full_text, r'Agency\s+([\w\s]+(?:PVT|PRIVATE)?\s*(?:LTD|LIMITED)?)', default="GROUP M MEDIA INDIA PVT LTD")
    h.channel_name = "Mathrubhumi News"
    h.invoice_number = _extract(full_text, r'Invoice\s*Number\s*:\s*(\S+)')
    h.invoice_date = _extract(full_text, r'Invoice\s*Date\s*:\s*(\S+)')
    h.billing_period = _extract(full_text, r'Billing\s*Period\s*:?\s*(.+?)(?:\n|$)')
    h.po_number = _extract(full_text, r'(?:Release\s*Order\s*No|RO\s*Number)\s*:?\s*(\S+)')
    h.brand = _extract(full_text, r'Description\s*:\s*(\w+)', default="XIAOMI")

    # Get rate from Page 1 summary
    rate_m = re.search(r'(\d+)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s*\n\s*Total', full_text)
    default_rate = 0.0
    if rate_m:
        default_rate = _parse_num(rate_m.group(2))

    # Also try: Sl. No. Spot_Type Duration Total_Spots Net_Rate Total_Amount
    if not default_rate:
        rate_m2 = re.search(r'COMMERCIAL\s+(\d+)\s+(\d+)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)', full_text)
        if rate_m2:
            default_rate = _parse_num(rate_m2.group(3))

    # Parse telecast certificate spots
    in_telecast = False
    skip_words = ['TELECAST CERTIFICATE', 'Mathrubhumi', 'Agency ', 'Address ',
                  'TC Number', 'TC Date', 'MO Number', 'Due Date', 'GST No',
                  'Place of Supply', 'State Code', 'TAN NO', 'Billing Period',
                  'Release Order', 'Advertiser ', 'Date Programe', 'Programme',
                  '(Sec)', 'Campaign Period', 'CIN NO', 'V.M. Nair', 'Vanchiyoor',
                  'Kerala, India', 'Ph-', 'www.', 'Publishing', 'Page ', 'Total',
                  'We certify', 'BANGALORE', 'MARATHAHALLI', 'UMIYA', '8TH FLOOR',
                  'KADUBEESANA', 'SARJAPUR']

    for page_text in pages_text:
        if 'TELECAST CERTIFICATE' in page_text:
            in_telecast = True
        if not in_telecast:
            continue

        lines = page_text.split('\n')
        for line in lines:
            ls = line.strip()
            if not ls:
                continue
            if any(skip in ls for skip in skip_words):
                continue

            # Match: DATE PROGRAMME TIME CAPTION DURATION SPOT_TYPE
            spot_m = re.match(
                r'(\d{1,2}/\d{1,2}/\d{4})\s+'     # Date
                r'(.+?)\s+'                         # Programme Name
                r'(\d{1,2}:\d{2}:\d{2})\s+'         # Time
                r'(.+?)\s+'                         # Caption
                r'(\d+)\s+'                         # Duration
                r'(COMMERCIAL|PROMO)',               # Spot Type
                ls, re.IGNORECASE
            )

            if spot_m:
                spot = BroadcasterSpot()
                spot.date = spot_m.group(1)
                spot.program = _clean(spot_m.group(2))
                spot.air_time = spot_m.group(3)
                spot.spot_copy = _clean(spot_m.group(4))
                spot.duration = int(spot_m.group(5))
                spot.day = _get_day_from_date(spot.date)
                spot.rate = default_rate
                spot.amount = default_rate * (spot.duration / 10) if default_rate else 0.0
                spot.brand = h.brand
                result.spots.append(spot)

    h.total_spots = len(result.spots)
    h.net_amount = sum(s.amount for s in result.spots)
    return result
