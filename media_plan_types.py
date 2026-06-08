from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime

@dataclass
class MediaPlanRow:
    channel: str = ""
    programme: str = ""
    days: str = ""
    time_band: str = ""
    pt_npt: str = ""
    net_rate: float = 0.0
    caption: str = ""
    spots_by_date: Dict[datetime, int] = field(default_factory=dict)

@dataclass
class ParsedMediaPlan:
    client_name: str = ""
    brand_name: str = ""
    rows: List[MediaPlanRow] = field(default_factory=list)
