# -*- coding: utf-8 -*-
"""
==============================================================================
AuriMold  -  Pipeline Paramétrico e Executável (Desafio 2)
==============================================================================
Projeto    : AuriMold (Hackafono)
Arquivo    : src/main_pipeline.py
Descrição  : Classe orquestradora EarmoldPipeline que recebe parâmetros
             clínicos, executa o fluxo completo (segmentação → perfuração →
             validação → relatório IA → exportação) e disponibiliza
             interface CLI via argparse.

Integração : OpenRouter API (rota gratuita) para geração de relatório
             de conformidade clínica via LLM (Gemma 2 / Llama 3 / Qwen).

Autor      : Pipeline AuriMold (Open-Source)
Licença    : MIT
==============================================================================
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import pathlib
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import trimesh

# Importações dos módulos internos do projeto.
# Utiliza importação relativa quando executado como pacote, ou absoluta
# quando executado diretamente via CLI.
try:
    from segmentation import MeshSegmenter
    from borehole import BoreholeGenerator
except ImportError:
    from src.segmentation import MeshSegmenter
    from src.borehole import BoreholeGenerator

# ==============================================================================
# Constantes de Integração com APIs de IA
# ==============================================================================

# OpenRouter API  -  Rota Gratuita
_OPENROUTER_API_URL: str = "https://openrouter.ai/api/v1/chat/completions"
_OPENROUTER_FREE_MODEL: str = "google/gemma-2-9b-it:free"

# Hugging Face Serverless Inference API
_HF_INFERENCE_URL: str = "https://api-inference.huggingface.co/models/"
_HF_DEFAULT_MODEL: str = "google/flan-t5-base"

# Timeout para chamadas HTTP (segundos).
_API_TIMEOUT_S: int = 30

logger = logging.getLogger(__name__)


# ==============================================================================
# Dataclass  -  Parâmetros Clínicos
# ==============================================================================

@dataclass
class ClinicalParameters:
    """
    Encapsula os parâmetros clínicos definidos pela fonoaudióloga
    para a personalização do molde auricular.

    Attributes
    ----------
    diametro_tubo : float
        Diâmetro interno do tubo de condução acústica (mm).
    folga_ajuste : float
        Folga dimensional para tolerância de fabricação (mm).
    angulo_insercao : float
        Ângulo de inserção do tubo relativo ao eixo vertical (graus).
    espessura_minima : float
        Espessura mínima segura da parede do molde (mm).
    caminho_entrada : str
        Caminho do arquivo .stl de entrada (escaneamento bruto).
    caminho_saida : str
        Caminho do arquivo .stl de saída (molde processado).
    """

    diametro_tubo: float = 2.0
    folga_ajuste: float = 0.3
    angulo_insercao: float = 15.0
    espessura_minima: float = 1.2
    caminho_entrada: str = ""
    caminho_saida: str = ""


# ==============================================================================
# Classe Principal  -  EarmoldPipeline
# ==============================================================================

class EarmoldPipeline:
    """
    Orquestra o fluxo completo do pipeline AuriMold:

        Carga → Segmentação → Perfuração → Validação → Relatório IA → Exportação

    Parameters
    ----------
    params : ClinicalParameters
        Parâmetros clínicos do molde auricular.
    openrouter_api_key : str, optional
        Chave da API do OpenRouter. Se ``None``, tenta ler de
        ``OPENROUTER_API_KEY`` no ambiente.
    hf_api_key : str, optional
        Chave da API do Hugging Face. Se ``None``, tenta ler de
        ``HF_API_TOKEN`` no ambiente.
    """

    def __init__(
        self,
        params: ClinicalParameters,
        openrouter_api_key: Optional[str] = None,
        hf_api_key: Optional[str] = None,
    ) -> None:
        self.params: ClinicalParameters = params
        self.openrouter_api_key: Optional[str] = (
            openrouter_api_key or os.environ.get("OPENROUTER_API_KEY")
        )
        self.hf_api_key: Optional[str] = (
            hf_api_key or os.environ.get("HF_API_TOKEN")
        )

        # Estado interno do pipeline.
        self._segmentation_report: Dict[str, Any] = {}
        self._borehole_report: Dict[str, Any] = {}
        self._ai_report: str = ""
        self._final_mesh: Optional[trimesh.Trimesh] = None

        # Validar caminhos de entrada.
        entrada = pathlib.Path(self.params.caminho_entrada).resolve()
        if not entrada.exists():
            raise FileNotFoundError(
                f"[Pipeline] Arquivo de entrada não encontrado: {entrada}"
            )

        logger.info(
            "EarmoldPipeline inicializado.\n"
            "  Entrada : %s\n"
            "  Saída   : %s\n"
            "  Params  : diâmetro=%.2f mm, folga=%.2f mm, "
            "ângulo=%.1f°, espessura_min=%.2f mm",
            self.params.caminho_entrada,
            self.params.caminho_saida,
            self.params.diametro_tubo,
            self.params.folga_ajuste,
            self.params.angulo_insercao,
            self.params.espessura_minima,
        )

    # ==========================================================================
    # Fase 1  -  Segmentação (Desafio 0)
    # ==========================================================================

    def _run_segmentation(self) -> trimesh.Trimesh:
        """Executa o módulo de segmentação e retorna a malha processada."""
        logger.info("-" * 60)
        logger.info("FASE 1  -  Segmentação e Higienização Topológica")
        logger.info("-" * 60)

        segmenter = MeshSegmenter(self.params.caminho_entrada)
        mesh, report = segmenter.run()

        self._segmentation_report = report
        return mesh

    # ==========================================================================
    # Fase 2  -  Perfuração (Desafio 1)
    # ==========================================================================

    def _run_borehole(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """Executa o módulo de perfuração e retorna a malha perfurada."""
        logger.info("-" * 60)
        logger.info("FASE 2  -  Perfuração e Validação Estrutural")
        logger.info("-" * 60)

        generator = BoreholeGenerator(
            mesh=mesh,
            diametro_tubo=self.params.diametro_tubo,
            angulo_insercao=self.params.angulo_insercao,
            folga_ajuste=self.params.folga_ajuste,
            espessura_minima=self.params.espessura_minima,
        )
        result_mesh, report = generator.run()

        self._borehole_report = report
        return result_mesh

    # ==========================================================================
    # Fase 3  -  Integração com IA (Relatório de Conformidade)
    # ==========================================================================

    def _generate_ai_report(self) -> str:
        """
        Gera um relatório de conformidade clínica utilizando um modelo LLM
        via a rota gratuita do OpenRouter.

        Payload:
            Envia as métricas topológicas (volume, estanqueidade, espessura)
            e os parâmetros clínicos ao modelo para análise e validação
            textual automatizada.

        Returns
        -------
        str
            Relatório textual de conformidade gerado pelo modelo LLM.
            Retorna string vazia se a integração falhar (não-bloqueante).
        """
        logger.info("-" * 60)
        logger.info("FASE 3  -  Integração IA (Relatório de Conformidade)")
        logger.info("-" * 60)

        # Importa requests sob demanda para não bloquear o pipeline
        # caso não esteja instalado.
        try:
            import requests
        except ImportError:
            logger.warning(
                "Biblioteca 'requests' não disponível. "
                "Relatório IA desativado."
            )
            return ""

        if not self.openrouter_api_key:
            logger.warning(
                "OPENROUTER_API_KEY não configurada. "
                "Relatório IA desativado. Defina a variável de ambiente "
                "ou passe a chave no construtor."
            )
            return self._generate_hf_report_fallback()

        # --- Montar prompt clínico-técnico ---
        metrics_summary: str = json.dumps(
            {
                "parametros_clinicos": {
                    "diametro_tubo_mm": self.params.diametro_tubo,
                    "folga_ajuste_mm": self.params.folga_ajuste,
                    "angulo_insercao_graus": self.params.angulo_insercao,
                    "espessura_minima_mm": self.params.espessura_minima,
                },
                "segmentacao": self._segmentation_report,
                "perfuracao": self._borehole_report,
                "malha_final": {
                    "n_vertices": (
                        len(self._final_mesh.vertices)
                        if self._final_mesh is not None
                        else 0
                    ),
                    "n_faces": (
                        len(self._final_mesh.faces)
                        if self._final_mesh is not None
                        else 0
                    ),
                    "is_watertight": (
                        bool(self._final_mesh.is_watertight)
                        if self._final_mesh is not None
                        else False
                    ),
                },
            },
            indent=2,
            ensure_ascii=False,
        )

        system_prompt: str = (
            "Você é um engenheiro biomédico especialista em próteses auditivas "
            "infantis. Analise as métricas do molde auricular 3D abaixo e emita "
            "um relatório sintético de conformidade clínica em português, "
            "indicando se o molde está apto para fabricação em silicone, "
            "destacando riscos e recomendações."
        )

        user_prompt: str = (
            f"Métricas do molde processado pelo pipeline AuriMold:\n\n"
            f"```json\n{metrics_summary}\n```\n\n"
            f"Emita o relatório de conformidade."
        )

        payload: dict = {
            "model": _OPENROUTER_FREE_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 1024,
            "temperature": 0.3,
        }

        headers: dict = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/aurimold/hackafono",
            "X-Title": "AuriMold Pipeline",
        }

        try:
            response = requests.post(
                _OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=_API_TIMEOUT_S,
            )
            response.raise_for_status()
            data: dict = response.json()

            report_text: str = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )

            if report_text:
                logger.info("Relatório de conformidade gerado com sucesso.")
                self._ai_report = report_text
                return report_text
            else:
                logger.warning("Resposta da API vazia. Tentando fallback HF.")
                return self._generate_hf_report_fallback()

        except Exception as exc:
            logger.warning(
                "Falha na chamada OpenRouter (%s). Tentando fallback HF.",
                exc,
            )
            return self._generate_hf_report_fallback()

    def _generate_hf_report_fallback(self) -> str:
        """
        Fallback: gera um relatório simplificado via Hugging Face
        Serverless Inference API.

        Returns
        -------
        str
            Relatório textual ou string vazia se falhar.
        """
        try:
            import requests
        except ImportError:
            return ""

        if not self.hf_api_key:
            logger.warning(
                "HF_API_TOKEN não configurada. Relatório IA desativado."
            )
            return self._generate_local_report()

        prompt: str = (
            f"Analyze this 3D earmold for infant hearing aid. "
            f"Wall thickness min: {self._borehole_report.get('min_thickness_mm', 'N/A')} mm. "
            f"Is watertight: {self._segmentation_report.get('is_watertight', 'N/A')}. "
            f"Tube diameter: {self.params.diametro_tubo} mm. "
            f"Provide a brief compliance assessment."
        )

        headers: dict = {"Authorization": f"Bearer {self.hf_api_key}"}
        payload: dict = {"inputs": prompt}

        try:
            response = requests.post(
                f"{_HF_INFERENCE_URL}{_HF_DEFAULT_MODEL}",
                headers=headers,
                json=payload,
                timeout=_API_TIMEOUT_S,
            )
            response.raise_for_status()
            data = response.json()

            if isinstance(data, list) and len(data) > 0:
                text = data[0].get("generated_text", "")
                if text:
                    self._ai_report = text
                    logger.info("Relatório gerado via HuggingFace (fallback).")
                    return text

        except Exception as exc:
            logger.warning("Fallback HuggingFace falhou: %s", exc)

        return self._generate_local_report()

    def _generate_local_report(self) -> str:
        """
        Gera um relatório de conformidade local (sem API externa)
        baseado nas métricas computadas pelo pipeline.

        Returns
        -------
        str
            Relatório textual estruturado.
        """
        logger.info("Gerando relatório de conformidade local (sem API).")

        is_watertight = self._segmentation_report.get("is_watertight", False)
        is_safe = self._borehole_report.get("is_safe", False)
        min_thick = self._borehole_report.get("min_thickness_mm", 0.0)
        volume = self._segmentation_report.get("volume_mm3", 0.0)

        status = "✅ APROVADO" if (is_watertight and is_safe) else "⚠️ REQUER REVISÃO"

        report = (
            f"{'=' * 60}\n"
            f"RELATÓRIO DE CONFORMIDADE  -  AuriMold Pipeline\n"
            f"{'=' * 60}\n\n"
            f"Status Geral: {status}\n\n"
            f"--- Parâmetros Clínicos ---\n"
            f"  Diâmetro do tubo     : {self.params.diametro_tubo:.2f} mm\n"
            f"  Folga de ajuste      : {self.params.folga_ajuste:.2f} mm\n"
            f"  Ângulo de inserção   : {self.params.angulo_insercao:.1f}°\n"
            f"  Espessura mín. requerida : {self.params.espessura_minima:.2f} mm\n\n"
            f"--- Métricas de Segmentação ---\n"
            f"  Estanque (watertight)  : {'Sim' if is_watertight else 'Não'}\n"
            f"  Volume do molde        : {volume:.2f} mm³\n"
            f"  Buracos preenchidos    : {self._segmentation_report.get('holes_filled', 'N/A')}\n\n"
            f"--- Métricas de Perfuração ---\n"
            f"  Espessura mín. medida  : {min_thick:.2f} mm\n"
            f"  Espessura média        : {self._borehole_report.get('mean_thickness_mm', 0.0):.2f} mm\n"
            f"  Violações de espessura : {self._borehole_report.get('violations', 0)}\n"
            f"  Parede segura          : {'Sim' if is_safe else 'Não'}\n\n"
        )

        if not is_watertight:
            report += (
                "⚠️ ATENÇÃO: A malha não é estanque. Operações booleanas podem "
                "ter produzido artefatos. Verifique manualmente no fatiador.\n\n"
            )

        if not is_safe:
            report += (
                "⚠️ ATENÇÃO: Espessura mínima da parede está abaixo do limiar "
                f"de segurança ({self.params.espessura_minima:.2f} mm). "
                "O molde apresenta risco de ruptura durante a moldagem.\n\n"
            )

        report += f"{'=' * 60}\n"

        self._ai_report = report
        return report

    # ==========================================================================
    # Fase 4  -  Exportação
    # ==========================================================================

    def _export(self, mesh: trimesh.Trimesh) -> pathlib.Path:
        """
        Exporta a malha final processada para o caminho de saída.

        Returns
        -------
        pathlib.Path
            Caminho absoluto do arquivo exportado.
        """
        logger.info("-" * 60)
        logger.info("FASE 4  -  Exportação do STL Final")
        logger.info("-" * 60)

        output_path = pathlib.Path(self.params.caminho_saida).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        mesh.export(str(output_path), file_type="stl")
        logger.info("Malha exportada para: %s", output_path)

        # Salvar relatório IA ao lado do STL.
        if self._ai_report:
            report_path = output_path.with_suffix(".report.txt")
            report_path.write_text(self._ai_report, encoding="utf-8")
            logger.info("Relatório de conformidade salvo em: %s", report_path)

        return output_path

    # ==========================================================================
    # Execução Completa do Pipeline
    # ==========================================================================

    def run(self) -> Dict[str, Any]:
        """
        Executa o pipeline completo AuriMold.

        Fluxo:
            Carga → Segmentação → Perfuração → Validação →
            Relatório IA → Exportação

        Returns
        -------
        Dict[str, Any]
            Dicionário com todas as métricas e caminhos de saída:
            - ``segmentation_report`` (dict)
            - ``borehole_report`` (dict)
            - ``ai_report`` (str)
            - ``output_path`` (str)
            - ``elapsed_seconds`` (float)
            - ``success`` (bool)
        """
        logger.info("=" * 60)
        logger.info("  AuriMold Pipeline  -  Início da Execução  ")
        logger.info("=" * 60)

        start_time = time.time()

        result: Dict[str, Any] = {
            "segmentation_report": {},
            "borehole_report": {},
            "ai_report": "",
            "output_path": "",
            "elapsed_seconds": 0.0,
            "success": False,
        }

        try:
            # Fase 1  -  Segmentação
            mesh = self._run_segmentation()
            result["segmentation_report"] = self._segmentation_report

            # Fase 2  -  Perfuração
            mesh = self._run_borehole(mesh)
            result["borehole_report"] = self._borehole_report
            self._final_mesh = mesh

            # Fase 3  -  Relatório IA
            ai_report = self._generate_ai_report()
            result["ai_report"] = ai_report

            # Fase 4  -  Exportação
            output_path = self._export(mesh)
            result["output_path"] = str(output_path)
            result["success"] = True

        except Exception as exc:
            logger.error(
                "ERRO FATAL no pipeline: %s", exc, exc_info=True
            )
            result["success"] = False

        elapsed = time.time() - start_time
        result["elapsed_seconds"] = round(elapsed, 2)

        logger.info("=" * 60)
        logger.info(
            "  AuriMold Pipeline  -  Concluído em %.2f s | Sucesso: %s",
            elapsed,
            result["success"],
        )
        logger.info("=" * 60)

        return result


# ==============================================================================
# Interface CLI (Command Line Interface) via argparse
# ==============================================================================

def build_cli_parser() -> argparse.ArgumentParser:
    """Constrói o parser de argumentos CLI do pipeline AuriMold."""

    parser = argparse.ArgumentParser(
        prog="aurimold",
        description=(
            "AuriMold (Hackafono)  -  Pipeline computacional para geração "
            "de moldes auriculares 3D a partir de escaneamentos .stl."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos de uso:\n"
            "  python main_pipeline.py -i samples/RAVI_2.stl -o output/molde.stl\n"
            "  python main_pipeline.py -i scan.stl -o molde.stl --diametro 2.5 --angulo 20\n"
        ),
    )

    parser.add_argument(
        "-i", "--input",
        type=str,
        required=True,
        help="Caminho do arquivo .stl de entrada (escaneamento bruto).",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        required=True,
        help="Caminho do arquivo .stl de saída (molde processado).",
    )
    parser.add_argument(
        "--diametro",
        type=float,
        default=2.0,
        help="Diâmetro do tubo de condução acústica em mm (default: 2.0).",
    )
    parser.add_argument(
        "--folga",
        type=float,
        default=0.3,
        help="Folga de ajuste / tolerância de fabricação em mm (default: 0.3).",
    )
    parser.add_argument(
        "--angulo",
        type=float,
        default=15.0,
        help="Ângulo de inserção do tubo em graus (default: 15.0).",
    )
    parser.add_argument(
        "--espessura-min",
        type=float,
        default=1.2,
        help="Espessura mínima segura da parede em mm (default: 1.2).",
    )
    parser.add_argument(
        "--openrouter-key",
        type=str,
        default=None,
        help="Chave da API OpenRouter (ou defina OPENROUTER_API_KEY).",
    )
    parser.add_argument(
        "--hf-key",
        type=str,
        default=None,
        help="Chave da API HuggingFace (ou defina HF_API_TOKEN).",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Ativar logs detalhados (nível DEBUG).",
    )

    return parser


def main() -> None:
    """Ponto de entrada principal para execução via CLI."""
    parser = build_cli_parser()
    args = parser.parse_args()

    # Configurar logging.
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Montar parâmetros clínicos.
    params = ClinicalParameters(
        diametro_tubo=args.diametro,
        folga_ajuste=args.folga,
        angulo_insercao=args.angulo,
        espessura_minima=args.espessura_min,
        caminho_entrada=args.input,
        caminho_saida=args.output,
    )

    # Executar pipeline.
    pipeline = EarmoldPipeline(
        params=params,
        openrouter_api_key=args.openrouter_key,
        hf_api_key=args.hf_key,
    )
    result = pipeline.run()

    # Exibir resumo final.
    print("\n" + "=" * 60)
    print("  RESUMO FINAL  -  AuriMold Pipeline")
    print("=" * 60)
    print(f"  Sucesso         : {result['success']}")
    print(f"  Tempo total     : {result['elapsed_seconds']:.2f} s")
    print(f"  Arquivo saída   : {result['output_path']}")
    print(f"  Watertight      : {result['segmentation_report'].get('is_watertight', 'N/A')}")
    print(f"  Parede segura   : {result['borehole_report'].get('is_safe', 'N/A')}")
    print(f"  Espessura mín.  : {result['borehole_report'].get('min_thickness_mm', 'N/A')} mm")
    print("=" * 60)

    if result.get("ai_report"):
        print("\n--- Relatório de Conformidade ---")
        print(result["ai_report"])

    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
