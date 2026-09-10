import trimesh
import os
from pathlib import Path
from ..models.geometry import MeshMetrics

def inspect_mesh(filepath: str | Path) -> MeshMetrics:
    """
    Carrega o arquivo STL e extrai as métricas geométricas iniciais.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Arquivo não encontrado: {filepath}")
        
    try:
        # force='mesh' garante que se falhar a dedução, ainda tente como stl/mesh
        mesh = trimesh.load(filepath, force='mesh')
        
        # Converte para uma única malha caso seja Scene
        if isinstance(mesh, trimesh.Scene):
            if len(mesh.geometry) == 0:
                raise ValueError("O arquivo STL não contém geometria.")
            mesh = trimesh.util.concatenate(tuple(trimesh.Trimesh(**g.kwargs) for g in mesh.geometry.values()))

        if not isinstance(mesh, trimesh.Trimesh):
            raise ValueError("Não foi possível carregar a malha corretamente.")

        return MeshMetrics(
            num_vertices=len(mesh.vertices),
            num_faces=len(mesh.faces),
            is_watertight=mesh.is_watertight,
            is_winding_consistent=mesh.is_winding_consistent,
            bounding_box_extents=mesh.extents.tolist(),
            volume=mesh.volume if mesh.is_watertight else None
        )
    except Exception as e:
        raise ValueError(f"Erro ao processar malha 3D: {str(e)}")
