import pandas as pd
from typing import Optional, List
from datetime import datetime
from media_plan_types import ParsedMediaPlan, MediaPlanRow

def _find_target_sheet_and_header(excel: pd.ExcelFile) -> tuple[Optional[str], Optional[int]]:
    """Find the sheet that contains the media plan data and the row index of its header."""
    for sheet in excel.sheet_names:
        # Ignore sheets that are obviously not plans
        if 'ESTIMATE' in sheet.upper() or 'BSL' in sheet.upper() or 'DUMP' in sheet.upper() or 'SPOT' in sheet.upper():
            continue
            
        try:
            df = pd.read_excel(excel, sheet_name=sheet, header=None, nrows=30)
        except Exception:
            continue
            
        # Look for header row
        for idx in range(min(30, len(df))):
            row_strs = [str(x).upper().strip() for x in df.iloc[idx].values if pd.notna(x)]
            has_channel = any('CHANNEL' in x for x in row_strs)
            has_prog = any('PROGRAM' in x for x in row_strs)
            has_time = any('TIME' in x for x in row_strs)
            
            # If we see Channel and Programme, it's definitely our table!
            if has_channel and (has_prog or has_time):
                return sheet, idx
                
    return None, None

def is_media_plan(file_path: str) -> bool:
    """Check if the file is an Excel file containing a Media Plan table."""
    if not str(file_path).lower().endswith(('.xlsx', '.xls')):
        return False
    try:
        excel = pd.ExcelFile(file_path)
        sheet, header_idx = _find_target_sheet_and_header(excel)
        return sheet is not None
    except Exception:
        return False

def parse_media_plan(file_path: str) -> Optional[ParsedMediaPlan]:
    """Parse the Base Plan sheet of a Media Plan Excel file."""
    try:
        excel = pd.ExcelFile(file_path)
        
        target_sheet, header_row_idx = _find_target_sheet_and_header(excel)
        if not target_sheet:
            print("Could not find any sheet with a Media Plan table structure.")
            return None
            
        # Read without headers to locate the header row manually
        df = pd.read_excel(excel, sheet_name=target_sheet, header=None)
        
        result = ParsedMediaPlan()
        
        # Extract Client and Brand from the first 5 rows
        for i in range(min(5, len(df))):
            label = str(df.iloc[i, 0]).strip().upper()
            val = str(df.iloc[i, 1]).strip()
            if val.lower() == 'nan':
                val = ""
                
            if 'CLIENT' in label:
                result.client_name = val
            elif 'BRAND' in label and 'TG' not in label:
                result.brand_name = val
                
        header_row = df.iloc[header_row_idx]
        
        # Map column indices for fixed columns
        col_map = {}
        date_cols = []
        
        for col_idx in range(len(header_row)):
            col_name = header_row[col_idx]
            
            # Extract date columns
            if isinstance(col_name, datetime):
                date_cols.append(col_idx)
            elif isinstance(col_name, str):
                name_upper = col_name.strip().upper()
                if 'CHANNEL' in name_upper: col_map['channel'] = col_idx
                elif 'PROGRAMME' in name_upper or 'PROGRAM' in name_upper: col_map['programme'] = col_idx
                elif 'DAYS' in name_upper or name_upper == 'DAY': col_map['days'] = col_idx
                elif 'TIMEBAND' in name_upper or 'TIME BAND' in name_upper or name_upper == 'TIME': col_map['time_band'] = col_idx
                elif 'PT/NPT' in name_upper or 'PT / NPT' in name_upper: col_map['pt_npt'] = col_idx
                elif 'NETT RATE' in name_upper or 'NET RATE' in name_upper: col_map['net_rate'] = col_idx
                elif 'CAPTION' in name_upper: col_map['caption'] = col_idx

        # Iterate through data rows
        for i in range(header_row_idx + 1, len(df)):
            row = df.iloc[i]
            
            # Stop if we hit an empty channel or an end marker
            channel_val = row[col_map.get('channel', 0)]
            if pd.isna(channel_val) or str(channel_val).strip() == '':
                continue
            if 'TOTAL' in str(channel_val).upper():
                continue
                
            plan_row = MediaPlanRow()
            
            def get_val(key):
                if key in col_map:
                    v = row[col_map[key]]
                    return "" if pd.isna(v) else v
                return ""
                
            plan_row.channel = str(get_val('channel')).strip()
            plan_row.programme = str(get_val('programme')).strip()
            days_val = get_val('days')
            try:
                d_float = float(days_val)
                if d_float.is_integer():
                    plan_row.days = str(int(d_float))
                else:
                    plan_row.days = str(round(d_float, 2))
            except (ValueError, TypeError):
                plan_row.days = str(days_val).strip()
            
            tb_val = get_val('time_band')
            try:
                # Try to parse as float and round it to 2 decimal places if it's a number
                tb_float = float(tb_val)
                # If it's effectively an integer (e.g., 6.0), format without decimals
                if tb_float.is_integer():
                    plan_row.time_band = str(int(tb_float))
                else:
                    plan_row.time_band = str(round(tb_float, 2))
            except (ValueError, TypeError):
                plan_row.time_band = str(tb_val).strip()
                
            plan_row.pt_npt = str(get_val('pt_npt')).strip()
            
            rate_val = get_val('net_rate')
            try:
                plan_row.net_rate = float(rate_val) if rate_val else 0.0
            except ValueError:
                plan_row.net_rate = 0.0
                
            plan_row.caption = str(get_val('caption')).strip()
            
            # Extract spots for dates
            has_any_spots = False
            for d_idx in date_cols:
                date_val = header_row[d_idx] # This is a datetime
                spots_val = row[d_idx]
                if not pd.isna(spots_val):
                    try:
                        spots = int(float(spots_val))
                        if spots > 0:
                            plan_row.spots_by_date[date_val] = spots
                            has_any_spots = True
                    except (ValueError, TypeError):
                        pass
            
            # Only add rows that have at least some spots or valid data
            result.rows.append(plan_row)
            
        return result
        
    except Exception as e:
        print(f"Error parsing Media Plan {file_path}: {e}")
        return None
