import re
from typing import List
import sys
import os
sys.path.append('c:/Users/asus/OneDrive/Desktop/New folder (6)')
from broadcaster_types import ParsedBroadcasterInvoice, BroadcasterSpot, _extract, _clean, _clean_air_time, _parse_num, _get_day_from_date

def parse(pages_text: List[str], full_text: str) -> ParsedBroadcasterInvoice:
    result = ParsedBroadcasterInvoice(format_type='asianet')
    h = result.header

    h.broadcaster_name = "ASIANET NEWS NETWORK PVT LTD"
    h.advertiser_name = _extract(full_text, r'Advertiser\s*\n?\s*(XIAOMI[A-Z\s]+(?:PVT|PRIVATE)\s*(?:LTD|LIMITED))', default="XIAOMI TECHNOLOGY INDIA PRIVATE LIMITED")
    h.agency_name = _extract(full_text, r'Agency\s*:?\s*\n?\s*(GROUP\s*M?\s*MEDIA\s*INDIA\s*(?:PVT|PRIVATE)?\.?\s*(?:LTD|LIMITED)[\w\-\s]*)', default="GROUPM MEDIA INDIA PVT LTD")
    h.channel_name = _extract(full_text, r'Channel\s*:\s*([\w\s]+?)(?:\n|Inv)')
    h.invoice_number = _extract(full_text, r'Invoice\s*No\.?\s*(\S+)')
    h.invoice_date = _extract(full_text, r'Invoice\s*Date\s*:?\s*(\d{1,2}[\-/]\w{3}[\-/]\d{4})')
    h.billing_period = _extract(full_text, r'Inv\s*Period\s*:?\s*(.+?)(?:\n|$)')
    h.po_number = _extract(full_text, r'(?:Agency\s*)?RO\s*No\.?\s*:?\s*(\S+)')
    h.brand = _extract(full_text, r'Brand\s*:?\s*(\w+)', default="XIAOMI")

    days_pat = r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)'

    # Find TELECAST CERTIFICATE pages
    in_telecast = False
    telecast_lines = []

    for page_text in pages_text:
        if 'TELECAST CERTIFICATE' in page_text:
            in_telecast = True
        if in_telecast:
            telecast_lines.extend(page_text.split('\n'))

    # Parse Asianet spot lines
    # Example: 1 NAMASTHE KERALAM 21-May-2024 Tue 07:00-12:00 08:48:42 XIAOMI REDMI 13 SUSTENANCE CREATIVE 1 - 20 SEC 20 1,500.00 3,000.00
    skip_words = ['Sr No', 'TELECAST CERTIFICATE', 'ASIANET NEWS', 'Page ', 'Regd Office',
                  'Corp Office', 'PAN:', 'GSTIN:', 'CIN No', 'Category:', 'HSN/SAC',
                  'Advertiser', 'Agency', 'Channel', 'Brand:', 'Pin Code', 'State:',
                  'Business Place', 'Break Rate', 'Per 10', 'Total:', 'In Words',
                  'Net Amount', 'Add:', 'IGST', 'CGST', 'SGST', 'Total Due',
                  'certify', 'Please issue', 'Quires', 'Kindly', 'Interest',
                  'All the payments', 'company reserves', 'Reverse',
                  'IRN No', 'ACK No', 'ACK Dt', 'computer generated',
                  'Authorized', 'Region', 'Invoice', 'PRIVATE LIMITED']

    for line in telecast_lines:
        ls = line.strip()
        if not ls:
            continue
        if any(skip in ls for skip in skip_words):
            continue

        # Match: Sr_No PROGRAMME DATE Day Time_Band Air_Time CAPTION DUR RATE AMOUNT
        m = re.match(
            r'(\d+)\s+'                                  # Sr No
            r'(.+?)\s+'                                  # Programme
            r'(\d{1,2}[\-/]\w{3}[\-/]\d{4})\s+'         # Date
            r'(' + days_pat + r')\s+'                    # Day
            r'(\d{1,2}:\d{2}[\-]\d{1,2}:\d{2})\s+'      # Time Band (TP)
            r'(\d{1,2}:\d{2}:\d{2})\s+'                  # Air Time
            r'(.+)',                                      # Rest (caption + dur + rate + amount)
            ls
        )

        if m:
            spot = BroadcasterSpot()
            spot.program = _clean(m.group(2))
            spot.date = m.group(3)
            spot.day = m.group(4)
            spot.tp = m.group(5)
            spot.air_time = m.group(6)

            remainder = m.group(7)
            # Extract numbers from end: DUR RATE AMOUNT
            nums = re.findall(r'([\d,]+\.?\d*)', remainder)
            if len(nums) >= 3:
                spot.duration = int(_parse_num(nums[-3]))
                spot.rate = _parse_num(nums[-2])
                spot.amount = _parse_num(nums[-1])
                # Caption is everything before the last 3 numbers
                caption = remainder
                for n in nums[-3:]:
                    idx = caption.rfind(n)
                    if idx >= 0:
                        caption = caption[:idx]
                spot.spot_copy = _clean(caption)
            elif len(nums) >= 1:
                spot.duration = int(_parse_num(nums[0])) if _parse_num(nums[0]) in [10, 20, 30] else 20

            spot.brand = h.brand
            result.spots.append(spot)

    h.total_spots = len(result.spots)
    h.net_amount = sum(s.amount for s in result.spots)
    return result
