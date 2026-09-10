from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class MeshMetrics(BaseModel):
    num_vertices: int
    num_faces: int
    is_watertight: bool
    is_winding_consistent: bool
    bounding_box_extents: List[float]
    volume: Optional[float] = None
