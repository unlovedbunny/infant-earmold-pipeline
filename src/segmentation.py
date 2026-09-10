# -*- coding: utf-8 -*-
"""
==============================================================================
AuriMold  -  Módulo de Segmentação e Tratamento de Malha (Desafio 0)
==============================================================================
Projeto    : AuriMold (Hackafono)
Arquivo    : src/segmentation.py
Descrição  : Carregamento, verificação de escala universal, segmentação
             anatômica por curvatura/plano de corte e reparo topológico
             de malhas 3D de escaneamentos auriculares infantis (.stl).

Referência : assets/docs/scan_trim_region.png  -  demarcação em vermelho
             indicando a região (concha/meato) a ser preservada.

Autor      : Pipeline AuriMold (Open-Source)
Licença    : MIT
==============================================================================
"""

from __future__ import annotations

import logging
import pathlib
from typing import Optional, Tuple, cast

import numpy as np
import trimesh


# ==============================================================================
# Constantes Geométricas e Limiares Clínicos
# ==============================================================================

# Faixa dimensional esperada para um molde auricular infantil, em milímetros.
# Utilizada na heurística de detecção automática de escala.
_EXPECTED_BBOX_MIN_MM: float = 10.0   # Limite inferior razoável (mm)
_EXPECTED_BBOX_MAX_MM: float = 80.0   # Limite superior razoável (mm)

# Fator de conversão metros → milímetros (scanners profissionais podem
# exportar em metros por padrão, ex: Artec Eva).
_M_TO_MM: float = 1000.0

# Percentil de curvatura utilizado na segmentação por curvatura Gaussiana.
# Vértices com |K| abaixo deste percentil são considerados "planos" e
# portanto candidatos a pertencer ao excesso de material (background).
_CURVATURE_PERCENTILE_THRESHOLD: float = 40.0

# Margem relativa (%) para expansão do plano de corte orientado pela
# bounding-box da região de interesse segmentada.
_CUTTING_PLANE_MARGIN: float = 0.05

logger = logging.getLogger(__name__)


# ==============================================================================
# Classe Principal  -  MeshSegmenter
# ==============================================================================

class MeshSegmenter:
    """
    Pipeline de segmentação de malhas auriculares 3D.

    Responsabilidades:
        1. Carregamento e higienização de arquivos .stl brutos.
        2. Verificação de Escala Universal (bounding box → normalização mm).
        3. Segmentação anatômica via análise de curvatura Gaussiana (K) e
           planos de corte orientados pela bounding-box.
        4. Reparo topológico: hole-filling, recálculo de normais e
           verificação de fechamento estanque (manifold / watertight).

    Attributes
    ----------
    mesh : trimesh.Trimesh
        Malha 3D carregada e processada.
    filepath : pathlib.Path
        Caminho absoluto do arquivo .stl de entrada.
    """

    def __init__(self, filepath: str | pathlib.Path) -> None:
        """
        Inicializa o segmentador carregando e higienizando a malha.

        Parameters
        ----------
        filepath : str | pathlib.Path
            Caminho para o arquivo .stl bruto de entrada.

        Raises
        ------
        FileNotFoundError
            Se o arquivo especificado não existir no disco.
        ValueError
            Se o arquivo não puder ser interpretado como malha 3D.
        """
        self.filepath: pathlib.Path = pathlib.Path(filepath).resolve()
        if not self.filepath.exists():
            raise FileNotFoundError(
                f"[Segmentation] Arquivo não encontrado: {self.filepath}"
            )

        logger.info("Carregando malha de: %s", self.filepath)

        try:
            loaded = trimesh.load(
                str(self.filepath),
                file_type="stl",
                force="mesh",
            )
        except Exception as exc:
            raise ValueError(
                f"[Segmentation] Falha ao interpretar o arquivo como malha: {exc}"
            ) from exc

        if not isinstance(loaded, trimesh.Trimesh):
            raise ValueError(
                "[Segmentation] O arquivo não contém uma malha triangular válida."
            )

        self.mesh: trimesh.Trimesh = loaded
        self._sanitize_initial()
        logger.info(
            "Malha carregada: %d vértices, %d faces.",
            len(self.mesh.vertices),
            len(self.mesh.faces),
        )

    # ==========================================================================
    # Etapa 0  -  Higienização Inicial
    # ==========================================================================

    def _sanitize_initial(self) -> None:
        """
        Remove artefatos topológicos triviais do escaneamento bruto:
        vértices duplicados, faces degeneradas e componentes isolados.
        """
        self.mesh.merge_vertices()
        # Trimesh 5.x removeu remove_degenerate_faces() - usar a mascara.
        degen_mask = self.mesh.nondegenerate_faces()
        self.mesh.update_faces(degen_mask)
        # Trimesh 5.x: unique_faces() retorna mascara de faces unicas.
        unique_mask = self.mesh.unique_faces()
        self.mesh.update_faces(unique_mask)
        self.mesh.remove_unreferenced_vertices()

        # Preserva somente a maior componente conexa (descarta fragmentos
        # de ruído espúrio gerados pelo scanner).
        components = self.mesh.split(only_watertight=False)
        if len(components) > 1:
            largest = max(components, key=lambda c: c.area)
            logger.info(
                "Descartando %d componentes isoladas (ruído). "
                "Preservando componente principal (%.1f mm²).",
                len(components) - 1,
                largest.area,
            )
            self.mesh = largest

    # ==========================================================================
    # Etapa 1  -  Verificação de Escala Universal
    # ==========================================================================

    def normalize_scale(self) -> float:
        """
        Verifica a escala geométrica da malha e normaliza para milímetros.

        Estratégia:
            Calcula a extensão máxima da bounding-box. Se a extensão estiver
            na faixa de metros (tipicamente < 0.1 unidades, que corresponde
            a < 100 mm), aplica o fator ×1000 para converter a milímetros.

        Fundamento Matemático:
            Seja ``e = max(bbox_max - bbox_min)`` a extensão máxima.
            - Se ``e < _EXPECTED_BBOX_MIN_MM`` ⟹ unidades prováveis em metros.
            - Se ``_EXPECTED_BBOX_MIN_MM ≤ e ≤ _EXPECTED_BBOX_MAX_MM`` ⟹ mm.
            - Se ``e > _EXPECTED_BBOX_MAX_MM`` ⟹ emite aviso (escala incomum).

        Returns
        -------
        float
            Fator de escala aplicado (1.0 se nenhuma normalização necessária).
        """
        bbox = self.mesh.bounding_box.extents  # (dx, dy, dz)
        max_extent: float = float(np.max(bbox))

        scale_factor: float = 1.0

        if max_extent < _EXPECTED_BBOX_MIN_MM:
            # Provável escala em metros → converter para milímetros.
            scale_factor = _M_TO_MM
            self.mesh.apply_scale(scale_factor)
            logger.warning(
                "Escala detectada em METROS (extensão máx. = %.4f). "
                "Aplicando fator ×%.0f → milímetros.",
                max_extent,
                scale_factor,
            )
        elif max_extent > _EXPECTED_BBOX_MAX_MM:
            logger.warning(
                "Extensão máxima da bounding-box (%.2f) excede o esperado "
                "(%.0f mm). Verifique a escala do arquivo de entrada.",
                max_extent,
                _EXPECTED_BBOX_MAX_MM,
            )
        else:
            logger.info(
                "Escala verificada: extensão máxima = %.2f mm (OK).",
                max_extent,
            )

        return scale_factor

    # ==========================================================================
    # Etapa 2  -  Segmentação por Curvatura e Plano de Corte
    # ==========================================================================

    def compute_vertex_curvature(self) -> np.ndarray:
        """
        Calcula a curvatura discreta Gaussiana (K) por vértice.

        Fundamento Matemático:
            A curvatura Gaussiana discreta no vértice v_i é dada pelo
            déficit angular (Descartes):

                K(v_i) = 2π − Σ_j θ_j

            onde θ_j são os ângulos das faces incidentes em v_i.

            Regiões com alta curvatura absoluta |K| correspondem a
            cavidades anatômicas (concha, tragus, antitragus, meato),
            enquanto |K| ≈ 0 indica superfícies planas (background do scan).

        Returns
        -------
        np.ndarray
            Vetor de curvaturas Gaussianas, shape (n_vertices,).
        """
        n_vertices: int = len(self.mesh.vertices)
        curvatures: np.ndarray = np.full(n_vertices, 2.0 * np.pi)

        # Obter ângulos internos de cada face por vértice.
        # face_angles: (n_faces, 3)  -  ângulo em cada canto da face.
        face_angles: np.ndarray = self.mesh.face_angles

        for face_idx, face in enumerate(self.mesh.faces):
            for corner_idx in range(3):
                vertex_id: int = face[corner_idx]
                curvatures[vertex_id] -= face_angles[face_idx, corner_idx]

        # Normaliza pela área de Voronoi mista (aproximação simplificada
        # usando a área das faces adjacentes / 3).
        vertex_areas: np.ndarray = np.zeros(n_vertices, dtype=np.float64)
        face_areas: np.ndarray = self.mesh.area_faces
        for face_idx, face in enumerate(self.mesh.faces):
            area_contrib: float = face_areas[face_idx] / 3.0
            for vid in face:
                vertex_areas[vid] += area_contrib

        # Evita divisão por zero em vértices degenerados.
        safe_areas: np.ndarray = np.where(
            vertex_areas > 1e-12, vertex_areas, 1e-12
        )
        curvatures /= safe_areas

        return curvatures

    def segment_by_curvature(
        self,
        percentile: float = _CURVATURE_PERCENTILE_THRESHOLD,
    ) -> np.ndarray:
        """
        Segmenta a malha identificando os vértices da região de interesse
        (concha/meato) com base no módulo da curvatura Gaussiana.

        Estratégia:
            Vértices com |K| acima do percentil informado são classificados
            como pertencentes à região anatômica de interesse (concavidades
            e protuberâncias), enquanto vértices "planos" são classificados
            como excesso de material do escaneamento.

        Parameters
        ----------
        percentile : float
            Percentil-limiar de curvatura (0–100). Default: 40.

        Returns
        -------
        np.ndarray
            Máscara booleana de vértices, shape (n_vertices,).
            ``True`` = pertence à região de interesse.
        """
        curvatures: np.ndarray = self.compute_vertex_curvature()
        abs_curvatures: np.ndarray = np.abs(curvatures)
        threshold: float = float(np.percentile(abs_curvatures, percentile))

        mask: np.ndarray = abs_curvatures >= threshold
        n_selected: int = int(np.sum(mask))
        logger.info(
            "Segmentação por curvatura: %d/%d vértices selecionados "
            "(percentil=%.0f, limiar K=%.4f).",
            n_selected,
            len(curvatures),
            percentile,
            threshold,
        )
        return mask

    def trim_mesh(
        self,
        vertex_mask: Optional[np.ndarray] = None,
    ) -> trimesh.Trimesh:
        """
        Aplica o corte da malha, preservando apenas as faces cujos vértices
        estejam na região de interesse (máscara) com refinamento via
        plano de corte orientado pela bounding-box da região segmentada.

        Estratégia Combinada:
            1. Seleciona faces cuja maioria dos vértices pertence à máscara.
            2. Calcula a bounding-box da submesh resultante.
            3. Aplica um plano de corte ortogonal para refinar as bordas
               (removendo triangulação residual em regiões periféricas).

        Parameters
        ----------
        vertex_mask : np.ndarray, optional
            Máscara booleana de vértices. Se ``None``, utiliza a segmentação
            automática por curvatura.

        Returns
        -------
        trimesh.Trimesh
            Malha segmentada (somente região anatômica de interesse).
        """
        if vertex_mask is None:
            vertex_mask = self.segment_by_curvature()

        # --- Passo 1: Selecionar faces por maioria de vértices na máscara ---
        # Uma face é preservada se pelo menos 2 de seus 3 vértices estão
        # na região de interesse.
        face_vertex_flags: np.ndarray = vertex_mask[self.mesh.faces]  # (n_faces, 3)
        face_votes: np.ndarray = face_vertex_flags.sum(axis=1)        # (n_faces,)
        face_mask: np.ndarray = face_votes >= 2

        selected_faces: np.ndarray = self.mesh.faces[face_mask]

        if len(selected_faces) == 0:
            logger.warning(
                "Nenhuma face sobreviveu ao corte por curvatura. "
                "Retornando malha original sem alterações."
            )
            return self.mesh

        # Reconstrói a submesh a partir das faces selecionadas.
        submesh = cast(
            trimesh.Trimesh,
            self.mesh.submesh([np.where(face_mask)[0]], append=True)
        )

        # --- Passo 2: Plano de corte via bounding-box ---
        # Calcula o centroide e extents da submesh para posicionar o plano.
        centroid: np.ndarray = submesh.centroid
        extents: np.ndarray = submesh.bounding_box.extents

        # Identifica o eixo de menor extensão como normal do plano de corte.
        # Em moldes auriculares, tipicamente o eixo Z (profundidade) é o menor.
        cut_axis: int = int(np.argmin(extents))

        # Posiciona o plano de corte ligeiramente abaixo do mínimo da BBox
        # com margem de segurança.
        bbox_min: np.ndarray = submesh.bounds[0]
        cut_origin: np.ndarray = centroid.copy()
        cut_origin[cut_axis] = bbox_min[cut_axis] - (
            extents[cut_axis] * _CUTTING_PLANE_MARGIN
        )

        plane_normal: np.ndarray = np.zeros(3)
        plane_normal[cut_axis] = 1.0  # Aponta para "dentro" do molde

        try:
            trimmed = trimesh.intersections.slice_mesh_plane(
                submesh,
                plane_normal=plane_normal,
                plane_origin=cut_origin,
            )
            if trimmed is not None and len(trimmed.faces) > 0:
                submesh = trimmed
                logger.info(
                    "Plano de corte aplicado no eixo %d. "
                    "Faces restantes: %d.",
                    cut_axis,
                    len(submesh.faces),
                )
        except Exception as exc:
            logger.warning(
                "Plano de corte falhou (%s). Prosseguindo sem refinamento.", exc
            )

        self.mesh = submesh
        return self.mesh

    # ==========================================================================
    # Etapa 3  -  Reparo Topológico
    # ==========================================================================

    def repair_topology(self) -> dict:
        """
        Executa o pipeline completo de reparo topológico:
            1. Preenchimento de buracos (hole filling).
            2. Reorientação consistente das normais para fora.
            3. Verificação de manifold e estanqueidade (watertight).

        Returns
        -------
        dict
            Dicionário com métricas do reparo:
            - ``holes_filled`` (int): Quantidade de buracos preenchidos.
            - ``normals_fixed`` (bool): Se as normais foram recalculadas.
            - ``is_watertight`` (bool): Status final de estanqueidade.
            - ``is_manifold`` (bool): Status final de manifold.
            - ``volume_mm3`` (float): Volume da malha reparada (mm³).
        """
        report: dict = {
            "holes_filled": 0,
            "normals_fixed": False,
            "is_watertight": False,
            "is_manifold": False,
            "volume_mm3": 0.0,
        }

        # --- 3.1 Preenchimento de Buracos ---
        # Trimesh identifica arestas de borda (boundary edges) como
        # indicadores de furos topológicos. Cada ciclo de arestas de borda
        # constitui um buraco que deve ser triangulado.
        try:
            initial_holes = len(self.mesh.outline().entities) if self.mesh.outline() else 0
        except Exception:
            initial_holes = 0

        trimesh.repair.fill_holes(self.mesh)
        self.mesh.merge_vertices()

        try:
            final_holes = len(self.mesh.outline().entities) if self.mesh.outline() else 0
        except Exception:
            final_holes = 0

        report["holes_filled"] = max(0, initial_holes - final_holes)

        if report["holes_filled"] > 0:
            logger.info(
                "Preenchidos %d buracos topológicos.", report["holes_filled"]
            )

        # --- 3.2 Orientação Consistente de Normais ---
        # Garante que todas as normais das faces apontem para o exterior
        # da superfície, condição obrigatória para operações booleanas
        # e exportação para fatiadores.
        try:
            trimesh.repair.fix_normals(self.mesh, multibody=False)
            report["normals_fixed"] = True
            logger.info("Normais reorientadas para o exterior.")
        except Exception as exc:
            logger.warning("Falha ao reorientar normais: %s", exc)

        # --- 3.3 Verificação de Manifold e Estanqueidade ---
        # Uma malha é manifold se cada aresta é compartilhada por exatamente
        # 2 faces. Estanque (watertight) implica manifold + sem buracos.
        report["is_manifold"] = bool(self.mesh.is_volume)
        report["is_watertight"] = bool(self.mesh.is_watertight)

        if report["is_watertight"]:
            report["volume_mm3"] = float(self.mesh.volume)
            logger.info(
                "Malha ESTANQUE (watertight). Volume: %.2f mm³.",
                report["volume_mm3"],
            )
        else:
            logger.warning(
                "Malha NÃO estanque após reparo. is_manifold=%s, is_watertight=%s. "
                "O pipeline prosseguirá, mas operações booleanas podem falhar.",
                report["is_manifold"],
                report["is_watertight"],
            )

        return report

    # ==========================================================================
    # Orquestração Completa do Módulo
    # ==========================================================================

    def run(self) -> Tuple[trimesh.Trimesh, dict]:
        """
        Executa o pipeline completo de segmentação:
            Escala → Segmentação → Corte → Reparo Topológico.

        Returns
        -------
        Tuple[trimesh.Trimesh, dict]
            Tupla (malha_processada, relatório_de_reparo).
        """
        logger.info("=" * 60)
        logger.info("INÍCIO  -  Pipeline de Segmentação (Desafio 0)")
        logger.info("=" * 60)

        # Etapa 1  -  Normalização de escala
        scale = self.normalize_scale()
        logger.info("Fator de escala aplicado: %.1f", scale)

        # Etapa 2  -  Segmentação por curvatura e corte
        self.trim_mesh()

        # Etapa 3  -  Reparo topológico
        repair_report = self.repair_topology()

        logger.info("=" * 60)
        logger.info(
            "FIM  -  Segmentação concluída. Faces: %d | Watertight: %s",
            len(self.mesh.faces),
            repair_report["is_watertight"],
        )
        logger.info("=" * 60)

        return self.mesh, repair_report


# ==============================================================================
# Interface Standalone (execução direta para testes)
# ==============================================================================

def segment_stl(
    input_path: str | pathlib.Path,
    output_path: Optional[str | pathlib.Path] = None,
) -> Tuple[trimesh.Trimesh, dict]:
    """
    Função utilitária para segmentar um arquivo STL em uma única chamada.

    Parameters
    ----------
    input_path : str | pathlib.Path
        Caminho do arquivo .stl bruto.
    output_path : str | pathlib.Path, optional
        Caminho de saída para salvar a malha segmentada. Se ``None``,
        não salva em disco (retorna somente o objeto em memória).

    Returns
    -------
    Tuple[trimesh.Trimesh, dict]
        Tupla (malha_segmentada, relatório).
    """
    segmenter = MeshSegmenter(input_path)
    mesh, report = segmenter.run()

    if output_path is not None:
        out = pathlib.Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        mesh.export(str(out), file_type="stl")
        logger.info("Malha segmentada exportada para: %s", out)

    return mesh, report


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )

    sample = pathlib.Path(__file__).resolve().parent.parent / "samples" / "RAVI_2.stl"
    out_dir = pathlib.Path(__file__).resolve().parent.parent / "output"

    if len(sys.argv) > 1:
        sample = pathlib.Path(sys.argv[1])

    mesh, report = segment_stl(sample, out_dir / "segmented.stl")
    print("\n--- Relatório de Segmentação ---")
    for k, v in report.items():
        print(f"  {k}: {v}")
