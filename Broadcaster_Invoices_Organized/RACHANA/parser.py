import re
from typing import List, Optional
import sys
import os
sys.path.append('c:/Users/asus/OneDrive/Desktop/New folder (6)')
from broadcaster_types import ParsedBroadcasterInvoice, BroadcasterSpot, _extract, _clean, _clean_air_time, _parse_num, _get_day_from_date

def parse(pages_text: List[str], full_text: str) -> Optional[ParsedBroadcasterInvoice]:
    invoice_no = _extract(full_text, r'Invoice No\.?\s*:\s*(\S+)')
    
    full_upper = full_text.upper()
    channel = ""
    if "NTV" in full_upper or "RACHANA" in full_upper:
        channel = "NTV"
    if "BHAKTHI" in full_upper:
        channel = "BHAKTHI TV"
    
    # Try to extract channel from 'Our Ref No.: NTV/...' if possible
    ref_match = re.search(r'Our Ref No\.\s*:\s*([^/]+)', full_text, re.IGNORECASE)
    if ref_match:
        channel = ref_match.group(1).strip()
    
    spots = []
    
    # Match lines like: 
    # 1 21-May-24 07:00:00 - 12:00:00 Redmi13 Sustenance Creative 1 20 Sec 1,500.00 60 9,000.00
    row_pattern = re.compile(
        r'^\s*\d+\s+'                           # Sl #
        r'(\d{1,2}-[A-Za-z]{3}-\d{2,4})\s+'     # Date
        r'([\d:]+\s*-\s*[\d:]+)\s+'             # Time band
        r'(.*?)\s+'                             # Product/Creative
        r'(\d+)\s*Sec\s+'                       # Creative duration (e.g. 20)
        r'([\d,]+\.?\d*)\s+'                    # Rate
        r'(\d+)\s+'                             # Total duration (e.g. 60)
        r'([\d,]+\.?\d*)',                      # Amount
        re.IGNORECASE | re.MULTILINE
    )
    
    for match in row_pattern.finditer(full_text):
        date_str = match.group(1).strip()
        time_band = match.group(2).strip()
        creative = match.group(3).strip()
        creative_dur = int(match.group(4).strip())
        rate = _parse_num(match.group(5))
        total_dur = int(match.group(6).strip())
        row_amount = _parse_num(match.group(7))
        
        # Calculate number of spots for this row
        spot_count = 1
        if creative_dur > 0:
            spot_count = total_dur // creative_dur
            
        for _ in range(max(1, spot_count)):
            spot = BroadcasterSpot()
            spot.date = date_str
            spot.day = _get_day_from_date(date_str)
            spot.air_time = _clean_air_time(time_band)
            spot.program = time_band # Since it's a time band, we'll use it as program context
            spot.spot_copy = creative
            spot.brand = "XIAOMI"
            spot.duration = creative_dur
            spot.rate = rate
            spot.amount = (creative_dur / 10.0) * rate # Assuming rate is per 10 secs
            spots.append(spot)

    if not invoice_no and not spots:
        return None
        
    result = ParsedBroadcasterInvoice()
    result.header.invoice_number = invoice_no
    result.header.channel_name = channel
    result.header.broadcaster_name = _extract(full_text, r'^([A-Z][\w\s]+(?:Private|Pvt|Ltd|Limited))', default="RACHANA TELEVISION PVT LTD")
    result.header.advertiser_name = _extract(full_text, r'Client\s*:\s*([\w\s]+(?:Private|Pvt|Ltd|Limited|LTD|PVT))', default="Xiaomi Technology India Pvt Ltd")
    result.header.agency_name = _extract(full_text, r'To\s*Invoice No.*?\n(.*?)(?:\n|$)', default="Group M Media India Pvt Ltd")
    result.header.invoice_date = _extract(full_text, r'Invoice Date\s*:\s*(\S+)')
    result.header.total_spots = len(spots)
    result.spots = spots
    result.format_type = "rachana"
    
    # Ensure amount matches roughly
    if spots:
        result.header.net_amount = sum(s.amount for s in spots)
        result.header.total_amount = result.header.net_amount
        
    return result
