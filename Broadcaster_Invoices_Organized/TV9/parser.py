import re
from typing import List
import sys
import os
sys.path.append('c:/Users/asus/OneDrive/Desktop/New folder (6)')
from broadcaster_types import ParsedBroadcasterInvoice, BroadcasterSpot, _extract, _clean, _clean_air_time, _parse_num, _get_day_from_date

def parse(pages_text: List[str], full_text: str) -> ParsedBroadcasterInvoice:
    result = ParsedBroadcasterInvoice(format_type='tv9')
    h = result.header

    h.broadcaster_name = "ASSOCIATED BROADCASTING COMPANY PVT LTD"
    h.advertiser_name = _extract(full_text, r'Advertiser\s*\n?\s*(XIAOMI[A-Z\s]+(?:PVT|PRIVATE)\s*(?:LTD|LIMITED))', default="XIAOMI TECHNOLOGY INDIA PRIVATE LIMITED")
    h.agency_name = _extract(full_text, r'Agency\s*(?:Name\s*)?\s*(GROUP\s*M?\s*MEDIA\s*INDIA\s*(?:PVT|PRIVATE)?\.?\s*(?:LTD|LIMITED)[\w\-\s]*)', default="GROUPM MEDIA INDIA PVT LTD")
    h.channel_name = _extract(full_text, r'Channel\s*:\s*([\w\s]+?)(?:\n|Invoice)') or "TV9 BHARATVARSH"
    h.invoice_number = _extract(full_text, r'Invoice\s*Number\s*:\s*(\S+)')
    h.invoice_date = _extract(full_text, r'Invoice\s*Date\s*:\s*(\S+)')
    h.billing_period = _extract(full_text, r'Invoice\s*Period\s*:\s*([\d\/\s\-]+)')
    h.po_number = _extract(full_text, r'Agency\s*Ref\.?No\s*:\s*(\S+)')
    h.brand = _extract(full_text, r'Brand\s*:\s*(\w+)', default="XIAOMI")

    # Parse TV9 spot list
    spot_pattern = re.compile(
        r'^(.+?)\s+'                                 # Programme
        r'(\d{2}:\d{2}:\d{2}\s*-\s*\d{2}:\d{2}:\d{2})\s+' # Time Band (TP)
        r'(\d{1,2}/\d{1,2}/\d{4})\s+'                # Date
        r'(RODP|BS|COMMERCIAL)\s+'                   # Inventory Type
        r'(\d{2}:\d{2}:\d{2})\s+'                    # Tx Time
        r'(.+?)\s+'                                  # Caption
        r'(\d+)\s+'                                  # No. of spots
        r'(\d+)\s+'                                  # Duration (secs)
        r'([\d,.]+|\.\d{2})',                        # Amount
        re.IGNORECASE
    )

    for page_text in pages_text:
        for line in page_text.split('\n'):
            m = spot_pattern.search(line.strip())
            if m:
                spots_count = int(m.group(7))
                total_amount = _parse_num(m.group(9))
                
                single_duration = int(m.group(8))
                single_amount = total_amount / spots_count if spots_count > 0 else 0.0
                single_rate = single_amount / (single_duration / 10) if single_duration > 0 else 0.0
                
                for _ in range(spots_count):
                    spot = BroadcasterSpot()
                    spot.program = _clean(m.group(1))
                    spot.tp = m.group(2)
                    spot.date = m.group(3)
                    spot.day = _get_day_from_date(spot.date)
                    spot.air_time = m.group(5)
                    spot.spot_copy = _clean(m.group(6))
                    spot.duration = single_duration
                    spot.rate = round(single_rate, 2)
                    spot.amount = round(single_amount, 2)
                    spot.brand = h.brand
                    result.spots.append(spot)

    h.total_spots = len(result.spots)
    h.net_amount = sum(s.amount for s in result.spots)
    return result
