import re
from typing import List
import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from broadcaster_types import ParsedBroadcasterInvoice, BroadcasterSpot, _extract, _clean, _clean_air_time, _parse_num, _get_day_from_date

def parse(pages_text: List[str], full_text: str) -> ParsedBroadcasterInvoice:
    result = ParsedBroadcasterInvoice(format_type='network18_band')
    h = result.header

    h.broadcaster_name = "NETWORK18 MEDIA & INVESTMENTS LIMITED"
    h.advertiser_name = _extract(full_text, r'Advertiser\s*:\s*(.+?)(?:\n|TDN)', default="XIAOMI TECHNOLOGY INDIA PRIVATE LIMITED")
    h.agency_name = _extract(full_text, r'Trade\s*Name\s*:\s*(.+?)(?:\n|Invoice)', default="GROUP M MEDIA INDIA PVT. LTD.")
    
    ch_m = re.search(r'activity\s+(?:o|on)\s+(News18\s+\w+)', full_text, re.IGNORECASE)
    h.channel_name = ch_m.group(1) if ch_m else "News18"
    
    h.invoice_number = _extract(full_text, r'Invoice\s*No\.\s*:\s*(\S+)')
    h.invoice_date = _extract(full_text, r'Date\s*:\s*([\d\w\s]+?)(?:\n|PAN)')
    h.billing_period = _extract(full_text, r'period\s*of\s*([\w\s\d]+?)(?:\n|$)')
    h.po_number = _extract(full_text, r'RO\s*No\s*:\s*(\S+)')
    h.brand = _extract(full_text, r'Brand\s*:\s*(\w+)', default="XIAOMI")

    # Match L-Band/J-Band spot lines
    spot_pattern = re.compile(
        r'^(\d{2}/\d{2}/\d{4})\s+'                   # Date
        r'(XIAOMI)\s+'                               # Brand
        r'(L\s+BAND|J\s+BAND|BUG)\s+'                # Type
        r'(\w+)\s+'                                  # Material
        r'(\d+)\s+'                                  # Spots count
        r'([\d,]+\.\d+)\s+'                          # Rate (decimal)
        r'([\d,]+\.\d+)',                            # Amount
        re.IGNORECASE
    )

    for page_text in pages_text:
        for line in page_text.split('\n'):
            m = spot_pattern.search(line.strip())
            if m:
                spots_count = int(m.group(5))
                total_amount = _parse_num(m.group(7))
                
                single_amount = total_amount / spots_count if spots_count > 0 else 0.0
                single_rate = _parse_num(m.group(6))
                
                for _ in range(spots_count):
                    spot = BroadcasterSpot()
                    spot.date = m.group(1)
                    spot.day = _get_day_from_date(spot.date)
                    spot.brand = h.brand
                    spot.tp = m.group(3)
                    spot.program = m.group(3)
                    spot.spot_copy = m.group(4)
                    spot.air_time = "00:00:00"
                    spot.duration = 10
                    spot.rate = round(single_rate, 2)
                    spot.amount = round(single_amount, 2)
                    result.spots.append(spot)

    h.total_spots = len(result.spots)
    h.net_amount = sum(s.amount for s in result.spots)
    return result
