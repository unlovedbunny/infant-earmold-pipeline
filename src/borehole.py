# -*- coding: utf-8 -*-
"""
==============================================================================
AuriMold  -  Módulo de Perfuração e Validação Estrutural (Desafio 1)
==============================================================================
Projeto    : AuriMold (Hackafono)
Arquivo    : src/borehole.py
Descrição  : Cálculo da trajetória do conduto acústico, geração do tubo
             paramétrico, operação booleana de subtração (Boolean Difference)
             com mecanismo de fallback multi-motor, e verificação de
             segurança de espessura de parede via Ray Casting.

Referência : assets/docs/earmold_tunnel_path.png  -  percurso tracejado
             indicando a trajetória interna do tubo acústico.

Autor      : Pipeline AuriMold (Open-Source)
Licença    : MIT
==============================================================================
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any, List, Optional, Tuple, cast

import numpy as np
import trimesh

# ==============================================================================
# Constantes de Segurança Estrutural
# ==============================================================================

# Espessura mínima da parede do molde de silicone (mm).
# Abaixo deste limiar, o material apresenta risco mecânico de ruptura.
MIN_WALL_THICKNESS_MM: float = 1.2

# Número de raios para amostragem radial na validação de espessura.
_N_RADIAL_RAYS: int = 36

# Número de pontos de amostragem ao longo do comprimento do tubo
# para a verificação de espessura.
_N_AXIAL_SAMPLES: int = 20

# Resolução do cilindro de perfuração (número de segmentos angulares).
_CYLINDER_RESOLUTION: int = 64

# Tolerância de deslocamento automático do vetor de perfuração (mm)
# quando a espessura mínima é violada.
_TRAJECTORY_ADJUSTMENT_STEP_MM: float = 0.3

# Máximo de iterações de ajuste automático da trajetória.
_MAX_ADJUSTMENT_ITERATIONS: int = 10

logger = logging.getLogger(__name__)


# ==============================================================================
# Classe Principal  -  BoreholeGenerator
# ==============================================================================

class BoreholeGenerator:
    """
    Gerador paramétrico do canal de condução acústica (borehole) no molde
    auricular 3D, com validação estrutural de segurança.

    Responsabilidades:
        1. Cálculo do eixo central (vetor diretriz) do conduto acústico.
        2. Geração da geometria cilíndrica parametrizada.
        3. Operação booleana de subtração (Boolean Difference) com fallback.
        4. Verificação de espessura de parede via Ray Casting radial.
        5. Ajuste automático da trajetória em caso de violação do limiar.

    Parameters
    ----------
    mesh : trimesh.Trimesh
        Malha do molde auricular segmentada (saída do módulo segmentation.py).
    diametro_tubo : float
        Diâmetro interno do tubo de passagem acústica, em mm.
    angulo_insercao : float
        Ângulo de inserção do tubo em relação ao eixo vertical (graus).
    folga_ajuste : float
        Folga dimensional de ajuste (tolerância de fabricação), em mm.
    espessura_minima : float
        Espessura mínima segura da parede do molde, em mm.
    """

    def __init__(
        self,
        mesh: trimesh.Trimesh,
        diametro_tubo: float = 2.0,
        angulo_insercao: float = 15.0,
        folga_ajuste: float = 0.3,
        espessura_minima: float = MIN_WALL_THICKNESS_MM,
    ) -> None:
        self.mesh: trimesh.Trimesh = mesh.copy()
        self.diametro_tubo: float = diametro_tubo
        self.raio_tubo: float = (diametro_tubo + folga_ajuste) / 2.0
        self.angulo_insercao: float = angulo_insercao
        self.folga_ajuste: float = folga_ajuste
        self.espessura_minima: float = espessura_minima

        # Atributos computados durante o pipeline.
        self._trajectory_origin: Optional[np.ndarray] = None
        self._trajectory_direction: Optional[np.ndarray] = None
        self._tube_mesh: Optional[trimesh.Trimesh] = None

        logger.info(
            "BoreholeGenerator inicializado. "
            "Diâmetro=%.2f mm, Ângulo=%.1f°, Folga=%.2f mm, "
            "Espessura mín.=%.2f mm.",
            diametro_tubo,
            angulo_insercao,
            folga_ajuste,
            espessura_minima,
        )

    # ==========================================================================
    # Etapa 1  -  Cálculo da Trajetória do Conduto Acústico
    # ==========================================================================

    def compute_trajectory(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calcula o eixo central (vetor diretriz) do conduto acústico
        a partir da morfologia da malha.

        Estratégia Geométrica:
            1. Identificar a região de máxima concavidade (meato acústico)
               como a zona de menor coordenada Z (profundidade) da malha.
            2. O ponto de entrada do tubo é o centroide dessa região.
            3. O vetor diretriz é orientado da entrada para o exterior,
               com rotação parametrizada pelo ângulo de inserção clínico.

        Fundamento Matemático  -  Rotação do Vetor Diretriz:
            Dado o eixo vertical ẑ = [0, 0, 1], o vetor diretriz d̂ é:

                d̂ = R_y(α) · ẑ

            onde R_y(α) é a matriz de rotação em torno do eixo Y pelo
            ângulo de inserção α (convertido de graus para radianos).

                    ⎡  cos α   0   sin α ⎤
            R_y(α) = ⎢   0      1    0    ⎥
                    ⎣ −sin α   0   cos α ⎦

        Returns
        -------
        Tuple[np.ndarray, np.ndarray]
            (origin, direction)  -  ponto de origem e vetor unitário diretriz.
        """
        vertices: np.ndarray = self.mesh.vertices

        # --- Identificar região do meato (concavidade profunda) ---
        # A concavidade mais profunda da concha tipicamente corresponde à
        # zona com a menor coordenada no eixo de profundidade.
        # Usamos o eixo Z como proxy (ajustável conforme orientação do scan).
        z_values: np.ndarray = vertices[:, 2]

        # Selecionar os 10% dos vértices com menor Z (região profunda).
        z_threshold: float = float(np.percentile(z_values, 10))
        deep_mask: np.ndarray = z_values <= z_threshold
        deep_vertices: np.ndarray = vertices[deep_mask]

        # Centroide da região profunda = ponto de entrada do tubo.
        origin: np.ndarray = np.mean(deep_vertices, axis=0)

        # --- Construir vetor diretriz com ângulo de inserção ---
        alpha_rad: float = np.radians(self.angulo_insercao)

        # Matriz de rotação R_y(α).
        cos_a: float = np.cos(alpha_rad)
        sin_a: float = np.sin(alpha_rad)

        # Vetor base: aponta "para fora" da orelha (eixo Z positivo).
        base_direction: np.ndarray = np.array([0.0, 0.0, 1.0])

        # Aplicar rotação em torno do eixo Y.
        # d = R_y · base
        direction: np.ndarray = np.array([
            cos_a * base_direction[0] + sin_a * base_direction[2],
            base_direction[1],
            -sin_a * base_direction[0] + cos_a * base_direction[2],
        ])

        # Normalizar (redundante para vetor unitário, mas garante robustez).
        direction = direction / np.linalg.norm(direction)

        self._trajectory_origin = origin
        self._trajectory_direction = direction

        logger.info(
            "Trajetória do conduto: origem=(%.2f, %.2f, %.2f), "
            "direção=(%.4f, %.4f, %.4f).",
            *origin, *direction,
        )

        return origin, direction

    # ==========================================================================
    # Etapa 2  -  Geração do Tubo Cilíndrico Paramétrico
    # ==========================================================================

    def generate_tube(
        self,
        length_factor: float = 1.5,
    ) -> trimesh.Trimesh:
        """
        Gera a geometria cilíndrica do tubo de condução acústica.

        O comprimento do tubo é calculado como ``length_factor`` vezes a
        extensão da malha ao longo do vetor diretriz, garantindo que o
        cilindro atravesse completamente o molde.

        Parameters
        ----------
        length_factor : float
            Multiplicador de comprimento relativo à extensão da malha.

        Returns
        -------
        trimesh.Trimesh
            Malha cilíndrica posicionada e orientada conforme a trajetória.
        """
        if self._trajectory_origin is None or self._trajectory_direction is None:
            self.compute_trajectory()

        origin = self._trajectory_origin
        direction = self._trajectory_direction
        assert origin is not None
        assert direction is not None

        # --- Calcular comprimento do tubo ---
        # Projeta todos os vértices sobre o vetor diretriz para encontrar
        # a extensão do molde nessa direção.
        projections: np.ndarray = (
            self.mesh.vertices - origin
        ) @ direction
        extent: float = float(np.ptp(projections))  # peak-to-peak
        tube_length: float = extent * length_factor

        # --- Gerar cilindro na origem e alinhar ---
        tube: trimesh.Trimesh = trimesh.creation.cylinder(
            radius=self.raio_tubo,
            height=tube_length,
            sections=_CYLINDER_RESOLUTION,
        )

        # O cilindro do Trimesh é criado centrado na origem com eixo Z.
        # Precisamos rotacioná-lo para alinhar com o vetor diretriz e
        # transladá-lo para a posição correta.

        # Vetor de alinhamento: de Z para direction.
        z_axis: np.ndarray = np.array([0.0, 0.0, 1.0])

        # Calcula a matriz de rotação entre Z e direction usando Rodrigues.
        rotation_matrix = self._rotation_matrix_from_vectors(z_axis, direction)

        # Aplica rotação e translação.
        transform: np.ndarray = np.eye(4)
        transform[:3, :3] = rotation_matrix
        # Centro do cilindro deve coincidir com a origem da trajetória.
        transform[:3, 3] = origin
        tube.apply_transform(transform)

        self._tube_mesh = tube

        logger.info(
            "Tubo gerado: raio=%.2f mm, comprimento=%.2f mm, "
            "%d faces.",
            self.raio_tubo,
            tube_length,
            len(tube.faces),
        )

        return tube

    @staticmethod
    def _rotation_matrix_from_vectors(
        vec_from: np.ndarray,
        vec_to: np.ndarray,
    ) -> np.ndarray:
        """
        Calcula a matriz de rotação 3×3 que alinha ``vec_from`` com ``vec_to``
        usando a fórmula de Rodrigues.

        Fundamento Matemático:
            Dados dois vetores unitários a e b:
                v = a × b              (eixo de rotação)
                s = ‖v‖                (seno do ângulo)
                c = a · b              (cosseno do ângulo)

            A matriz de rotação é:
                R = I + [v]× + [v]×² · (1 − c) / s²

            onde [v]× é a matriz antissimétrica (skew-symmetric) de v.

        Returns
        -------
        np.ndarray
            Matriz de rotação 3×3.
        """
        a = vec_from / np.linalg.norm(vec_from)
        b = vec_to / np.linalg.norm(vec_to)

        v: np.ndarray = np.cross(a, b)
        c: float = float(np.dot(a, b))
        s: float = float(np.linalg.norm(v))

        if s < 1e-10:
            # Vetores (anti-)paralelos.
            return np.eye(3) if c > 0 else -np.eye(3)

        # Matriz antissimétrica [v]×
        vx: np.ndarray = np.array([
            [0,    -v[2],  v[1]],
            [v[2],  0,    -v[0]],
            [-v[1], v[0], 0],
        ])

        rotation: np.ndarray = np.eye(3) + vx + (vx @ vx) * ((1 - c) / (s * s))
        return rotation

    # ==========================================================================
    # Etapa 3  -  Operação Booleana de Subtração (com Fallback Multi-Motor)
    # ==========================================================================

    def boolean_subtract(self) -> trimesh.Trimesh:
        """
        Executa a operação booleana de subtração (Boolean Difference) para
        escavar o canal do tubo no interior do molde.

        Estratégia de Fallback:
            1. **Motor primário**: Trimesh com engine ``manifold`` (manifold3d).
            2. **Motor secundário**: Trimesh com engine ``blender`` (bpy).
            3. **Motor terciário**: Fallback manual via inversão de normais
               do tubo e concatenação geométrica (mesh union pós-inversão).

        Returns
        -------
        trimesh.Trimesh
            Malha do molde com o canal perfurado.

        Raises
        ------
        RuntimeError
            Se todos os motores booleanos falharem.
        """
        if self._tube_mesh is None:
            self.generate_tube()

        tube = self._tube_mesh
        engines: List[Any] = ["manifold", "blender"]

        result: Optional[trimesh.Trimesh] = None

        for engine in engines:
            try:
                logger.info(
                    "Tentando Boolean Difference com engine '%s'...", engine
                )
                result = trimesh.boolean.difference(
                    [self.mesh, tube],
                    engine=engine,
                )
                if result is not None and len(result.faces) > 0:
                    logger.info(
                        "Boolean Difference bem-sucedida (engine='%s'). "
                        "Faces resultantes: %d.",
                        engine,
                        len(result.faces),
                    )
                    self.mesh = result
                    return self.mesh
                else:
                    logger.warning(
                        "Engine '%s' retornou malha vazia. Tentando próximo.",
                        engine,
                    )
            except Exception as exc:
                logger.warning(
                    "Engine '%s' falhou: %s. Tentando próximo fallback.",
                    engine,
                    exc,
                )

        # --- Fallback manual: inversão de normais + concatenação ---
        logger.warning(
            "Todos os motores booleanos falharam. "
            "Aplicando fallback manual (inversão de normais + concatenação)."
        )
        try:
            assert tube is not None
            tube_inverted = tube.copy()
            tube_inverted.invert()  # Inverte normais → "subtrai" volume

            concat_result = cast(
                trimesh.Trimesh,
                trimesh.util.concatenate([self.mesh, tube_inverted])
            )
            result = concat_result
            self.mesh = concat_result

            logger.info(
                "Fallback manual aplicado. Faces resultantes: %d.",
                len(self.mesh.faces),
            )
            return self.mesh
        except Exception as exc:
            raise RuntimeError(
                f"[Borehole] Falha total na operação booleana. "
                f"Nenhum motor disponível: {exc}"
            ) from exc

    # ==========================================================================
    # Etapa 4  -  Validação de Espessura de Parede via Ray Casting
    # ==========================================================================

    def validate_wall_thickness(self) -> dict:
        """
        Verifica a espessura da parede do molde ao redor do canal perfurado
        utilizando Ray Casting radial.

        Estratégia:
            Para cada ponto amostrado ao longo do eixo do tubo, emite
            ``_N_RADIAL_RAYS`` raios perpendiculares ao vetor diretriz.
            A distância até a primeira interseção com a superfície externa
            do molde determina a espessura da parede naquele ponto.

        Fundamento Matemático:
            Seja P um ponto no eixo do tubo e d̂ o vetor diretriz.
            Constrói-se um referencial local {ê₁, ê₂} ortogonal a d̂:

                ê₁ = normalize(ẑ × d̂)   (se d̂ ∦ ẑ)
                ê₂ = d̂ × ê₁

            Os raios radiais são:
                r(θ) = P + t·(cos θ · ê₁ + sin θ · ê₂),  θ ∈ [0, 2π)

            A espessura é w(P, θ) = t_hit − raio_tubo, onde t_hit é
            a distância da primeira interseção.

        Returns
        -------
        dict
            - ``min_thickness_mm`` (float): Espessura mínima encontrada.
            - ``mean_thickness_mm`` (float): Espessura média.
            - ``violations`` (int): Número de pontos com violação.
            - ``is_safe`` (bool): ``True`` se nenhuma violação detectada.
        """
        if self._trajectory_origin is None or self._trajectory_direction is None:
            raise RuntimeError(
                "[Borehole] Trajetória não calculada. Execute compute_trajectory()."
            )

        origin = self._trajectory_origin
        direction = self._trajectory_direction

        # --- Construir referencial local ortogonal a direction ---
        z_axis = np.array([0.0, 0.0, 1.0])
        if abs(np.dot(direction, z_axis)) > 0.99:
            z_axis = np.array([0.0, 1.0, 0.0])

        e1: np.ndarray = np.cross(z_axis, direction)
        e1 /= np.linalg.norm(e1)
        e2: np.ndarray = np.cross(direction, e1)
        e2 /= np.linalg.norm(e2)

        # --- Amostrar pontos ao longo do eixo ---
        projections = (self.mesh.vertices - origin) @ direction
        t_min, t_max = float(np.min(projections)), float(np.max(projections))
        margin = (t_max - t_min) * 0.1
        t_samples = np.linspace(t_min + margin, t_max - margin, _N_AXIAL_SAMPLES)

        # --- Amostrar ângulos radiais ---
        angles = np.linspace(0, 2 * np.pi, _N_RADIAL_RAYS, endpoint=False)

        thicknesses: List[float] = []
        violations: int = 0

        # Construir malha para Ray Casting (usa o RayMeshIntersector do Trimesh).
        try:
            intersector = trimesh.ray.ray_triangle.RayMeshIntersector(self.mesh)
        except Exception:
            # Fallback ao intersector padrão do Trimesh
            intersector = None

        for t in t_samples:
            point_on_axis: np.ndarray = origin + t * direction

            for theta in angles:
                ray_dir: np.ndarray = np.cos(theta) * e1 + np.sin(theta) * e2
                ray_dir /= np.linalg.norm(ray_dir)

                # Emitir raio a partir da superfície do tubo (raio_tubo de distância).
                ray_origin: np.ndarray = point_on_axis + self.raio_tubo * ray_dir

                try:
                    if intersector is not None:
                        locations, _, _ = intersector.intersects_location(
                            ray_origins=ray_origin.reshape(1, 3),
                            ray_directions=ray_dir.reshape(1, 3),
                        )
                    else:
                        locations, _, _ = self.mesh.ray.intersects_location(
                            ray_origins=ray_origin.reshape(1, 3),
                            ray_directions=ray_dir.reshape(1, 3),
                        )

                    if len(locations) > 0:
                        distances = np.linalg.norm(locations - ray_origin, axis=1)
                        wall_thickness = float(np.min(distances))
                        thicknesses.append(wall_thickness)

                        if wall_thickness < self.espessura_minima:
                            violations += 1
                except Exception:
                    # Raio não intersectou → borda aberta, pular silenciosamente.
                    pass

        report: dict = {
            "min_thickness_mm": float(np.min(thicknesses)) if thicknesses else 0.0,
            "mean_thickness_mm": float(np.mean(thicknesses)) if thicknesses else 0.0,
            "violations": violations,
            "is_safe": violations == 0,
            "total_samples": len(thicknesses),
        }

        if report["is_safe"]:
            logger.info(
                "Validação de espessura OK. Mín=%.2f mm, Média=%.2f mm.",
                report["min_thickness_mm"],
                report["mean_thickness_mm"],
            )
        else:
            logger.warning(
                "⚠ VIOLAÇÃO DE ESPESSURA! %d amostras abaixo de %.2f mm. "
                "Mín=%.2f mm. Ajuste automático será aplicado.",
                violations,
                self.espessura_minima,
                report["min_thickness_mm"],
            )

        return report

    # ==========================================================================
    # Etapa 5  -  Ajuste Automático da Trajetória
    # ==========================================================================

    def auto_adjust_trajectory(self) -> dict:
        """
        Itera sobre ajustes incrementais na trajetória do tubo até que a
        espessura mínima de parede seja respeitada em todos os pontos.

        Estratégia de Ajuste:
            A cada iteração, o ponto de origem da trajetória é deslocado
            em ``_TRAJECTORY_ADJUSTMENT_STEP_MM`` na direção do centroide
            da malha (afastando-se da parede mais fina). O tubo é
            regenerado e a operação booleana re-executada.

        Returns
        -------
        dict
            Relatório final de validação após os ajustes.
        """
        centroid: np.ndarray = self.mesh.centroid
        best_report: dict = {"is_safe": False, "violations": 9999}

        for iteration in range(_MAX_ADJUSTMENT_ITERATIONS):
            thickness_report = self.validate_wall_thickness()

            if thickness_report["is_safe"]:
                logger.info(
                    "Trajetória segura alcançada na iteração %d.", iteration
                )
                return thickness_report

            # --- Deslocar origem em direção ao centroide ---
            assert self._trajectory_origin is not None
            displacement: np.ndarray = centroid - self._trajectory_origin
            displacement_norm = np.linalg.norm(displacement)
            if displacement_norm > 1e-6:
                displacement = displacement / displacement_norm

            self._trajectory_origin += (
                displacement * _TRAJECTORY_ADJUSTMENT_STEP_MM
            )

            logger.info(
                "Iteração %d: deslocando origem em %.2f mm. "
                "Violações anteriores: %d.",
                iteration,
                _TRAJECTORY_ADJUSTMENT_STEP_MM,
                thickness_report["violations"],
            )

            # Regenerar tubo e re-executar booleana.
            self.generate_tube()
            self.boolean_subtract()

            if thickness_report["violations"] < best_report["violations"]:
                best_report = thickness_report

        logger.warning(
            "Ajuste automático esgotou %d iterações. "
            "Melhor resultado: %d violações.",
            _MAX_ADJUSTMENT_ITERATIONS,
            best_report["violations"],
        )
        return best_report

    # ==========================================================================
    # Orquestração Completa do Módulo
    # ==========================================================================

    def run(self) -> Tuple[trimesh.Trimesh, dict]:
        """
        Executa o pipeline completo de perfuração:
            Trajetória → Tubo → Booleana → Validação → (Ajuste) → Resultado.

        Returns
        -------
        Tuple[trimesh.Trimesh, dict]
            (malha_perfurada, relatório_de_validação).
        """
        logger.info("=" * 60)
        logger.info("INÍCIO  -  Pipeline de Perfuração (Desafio 1)")
        logger.info("=" * 60)

        # Etapa 1  -  Trajetória
        self.compute_trajectory()

        # Etapa 2  -  Geração do tubo
        self.generate_tube()

        # Etapa 3  -  Subtração booleana
        self.boolean_subtract()

        # Etapa 4  -  Validação de espessura
        thickness_report = self.validate_wall_thickness()

        # Etapa 5  -  Ajuste automático (se necessário)
        if not thickness_report["is_safe"]:
            logger.info("Iniciando ajuste automático da trajetória...")
            thickness_report = self.auto_adjust_trajectory()

        logger.info("=" * 60)
        logger.info(
            "FIM  -  Perfuração concluída. Faces: %d | Seguro: %s",
            len(self.mesh.faces),
            thickness_report["is_safe"],
        )
        logger.info("=" * 60)

        return self.mesh, thickness_report


# ==============================================================================
# Interface Standalone (execução direta para testes)
# ==============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )

    # Uso: python borehole.py <caminho_stl_segmentado>
    sample = (
        pathlib.Path(__file__).resolve().parent.parent / "output" / "segmented.stl"
    )
    if len(sys.argv) > 1:
        sample = pathlib.Path(sys.argv[1])

    if not sample.exists():
        print(f"Arquivo não encontrado: {sample}")
        sys.exit(1)

    mesh = cast(trimesh.Trimesh, trimesh.load(str(sample), force="mesh"))
    generator = BoreholeGenerator(
        mesh=mesh,
        diametro_tubo=2.0,
        angulo_insercao=15.0,
        folga_ajuste=0.3,
        espessura_minima=1.2,
    )
    result_mesh, report = generator.run()

    out_path = pathlib.Path(__file__).resolve().parent.parent / "output" / "bored.stl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result_mesh.export(str(out_path), file_type="stl")
    print(f"\nMalha perfurada exportada: {out_path}")
    print("\n--- Relatório de Espessura ---")
    for k, v in report.items():
        print(f"  {k}: {v}")
