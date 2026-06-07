import re
from typing import List
import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from broadcaster_types import ParsedBroadcasterInvoice, BroadcasterSpot, _extract, _clean, _clean_air_time, _parse_num, _get_day_from_date

def parse(pages_text: List[str], full_text: str) -> ParsedBroadcasterInvoice:
    result = ParsedBroadcasterInvoice(format_type='news18_lokmat')
    h = result.header

    h.broadcaster_name = "IBN LOKMAT NEWS PVT LTD"
    h.advertiser_name = _extract(full_text, r'Advertiser\s*:\s*(.+?)(?:\n|UIN)', default="XIAOMI TECHNOLOGY INDIA PVT LTD")
    h.agency_name = _extract(full_text, r'Trade\s*Name\s*:\s*(.+?)(?:\n|Invoice)', default="GROUP M MEDIA INDIA PVT. LTD.")
    h.channel_name = "NEWS18 LOKMAT"
    h.invoice_number = _extract(full_text, r'Invoice\s*No\.\s*:\s*(\S+)')
    h.invoice_date = _extract(full_text, r'Date\s*:\s*([\d\w\s]+?)(?:\n|State)')
    h.billing_period = _extract(full_text, r'period\s*of\s*([\w\s\d]+?)(?:\n|$)')
    h.po_number = _extract(full_text, r'RO\s*No\.\s*:\s*(\S+)')
    h.brand = _extract(full_text, r'Brand\s*:\s*(.+?)(?:\n|Place)', default="XIAOMI MOBILES")

    # Parse Lokmat spots
    spot_pattern = re.compile(
        r'^(\d{2}/\d{2}/\d{4})\s+'                   # Date
        r'(XIAOMI\s+MOBILES)\s+'                     # Brand
        r'(.+?)\s+'                                  # Caption + Program
        r'(\d{2}:\d{2}:\d{2})\s+'                    # Time (IST)
        r'(\d+)\s+'                                  # Duration
        r'([\d,]+\.\d{2})\s+'                        # Rate
        r'([\d,]+\.\d{2})$',                         # Amount
        re.IGNORECASE
    )

    for page_text in pages_text:
        for line in page_text.split('\n'):
            m = spot_pattern.search(line.strip())
            if m:
                spot = BroadcasterSpot()
                spot.date = m.group(1)
                spot.day = _get_day_from_date(spot.date)
                spot.brand = m.group(2)
                
                cap_prog = m.group(3)
                if "SUSTENANCE" in cap_prog:
                    parts = cap_prog.split("SUSTENANCE")
                    spot.spot_copy = _clean(parts[0] + " SUSTENANCE")
                    spot.program = _clean(parts[1])
                else:
                    spot.spot_copy = cap_prog
                    spot.program = "News18 Lokmat Ad"
                    
                spot.tp = ""
                spot.air_time = m.group(4)
                spot.duration = int(m.group(5))
                spot.rate = _parse_num(m.group(6))
                spot.amount = _parse_num(m.group(7))
                result.spots.append(spot)

    h.total_spots = len(result.spots)
    h.net_amount = sum(s.amount for s in result.spots)
    return result
