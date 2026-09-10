# Plano de Trabalho AuriMold (Hackafono)

Este documento apresenta o planejamento arquitetural e o cronograma de desenvolvimento para o projeto AuriMold. O objetivo central é implementar um pipeline computacional open-source e automatizado para o processamento de escaneamentos 3D de orelhas de bebês (formato `.stl`), culminando na geração de moldes 3D anatomossensíveis otimizados para a manufatura em silicone de próteses auditivas infantis.

## User Review Required

> [!IMPORTANT]
> **Aprovação de Milestone 1:** Em conformidade com a *Regra Estrita de Execução por Milestones* imposta no requisito 5, nenhuma linha de código será gerada nesta etapa inicial. O desenvolvimento prático (escrita do código Python) está estritamente condicionado à **aprovação explícita** da V.S.a. deste Plano de Trabalho.

## Open Questions

Não há pendências de requisitos no momento. A infraestrutura e a stack tecnológica estão perfeitamente definidas no escopo (Python 3.x, Trimesh, Open3D, NumPy, SciPy e integração serverless com OpenRouter/Hugging Face).

## Fases e Marcos (Milestones) de Desenvolvimento

O desenvolvimento será segregado modularmente para garantir o encapsulamento das responsabilidades, facilidade de testes matemáticos e orquestração limpa.

### Fase 1: Segmentação e Higienização Topológica (Desafio 0)
*   **Módulo:** `src/segmentation.py`
*   **Descrição:** Carregamento de malhas tridimensionais (como `RAVI_2.stl`) e execução de algoritmos de processamento geométrico para extração das regiões de interesse (concha e meato acústico externo).
*   **Marcos Técnicos:**
    1.  Leitura e higienização inicial (remoção de vértices isolados e faces degeneradas).
    2.  Modelagem matemática de planos de corte e análise de curvatura (Gaussiana/Média) para extração da região delimitada em `assets/docs/scan_trim_region.png`.
    3.  Rotinas de reparo topológico: *hole filling*, reorientação global de normais consistentes para o exterior e validação da característica manifold (estanqueidade / *is_watertight*).

### Fase 2: Operações Booleanas e Perfuração Paramétrica (Desafio 1)
*   **Módulo:** `src/borehole.py`
*   **Descrição:** Modelagem computacional da trajetória do tubo acústico referenciada em `assets/docs/earmold_tunnel_path.png` e execução de subtrações booleanas (*Boolean Difference*), acoplada a um sistema de segurança estrutural.
*   **Marcos Técnicos:**
    1.  Cálculo analítico do eixo diretor (vetor) baseado na morfologia interna do conduto acústico.
    2.  Geração paramétrica da geometria cilíndrica (tubo de passagem).
    3.  **Validação Estrutural de Segurança:** Implementação de análise espacial via *Ray Casting* ou *Mesh Distance Maps*. Emissão de alerta e reajuste automático do vetor de perfuração caso a espessura residual da parede seja inferior ao limiar crítico de $1.2\text{ mm}$, mitigando os riscos mecânicos de rasgar o material de silicone da prótese.

### Fase 3: Orquestração, Integração LLM e Pipeline (Desafio 2)
*   **Módulo:** `src/main_pipeline.py` (Classe `EarmoldPipeline`), `requirements.txt` e `README.md`
*   **Descrição:** Consolidação dos módulos anteriores em um fluxo de dados paramétrico e executável.
*   **Marcos Técnicos:**
    1.  Orquestração dos parâmetros clínicos (`diametro_tubo`, `folga_ajuste`, `angulo_insercao`, `espessura_minima`).
    2.  **Integração de Agentes IA (OpenRouter API - free):** O pipeline invocará um modelo LLM (ex: Gemma 2, Llama 3) utilizando a rota gratuita. Os dados topológicos, métricas de volume e flags de validação estrutural serão enviados ao modelo para a geração autônoma de um relatório final de conformidade clínica.
    3.  Exportação da malha tridimensional limpa e furada para o diretório `output/`.

## Arquitetura de IA a Custo Zero

A arquitetura para relatórios de conformidade e validações auxiliares foi desenhada minimizando os custos operacionais, usando modelos abertos (Llama 3/Gemma 2) e provedores gratuitos. O código de orquestração empregará a biblioteca `requests` nativa do Python, enviando payloads JSON otimizados (sem dependências pesadas de SDKs como LangChain, para máxima velocidade). Caso detectada a necessidade de análise visual rápida, poderemos implementar rotinas assíncronas utilizando a Hugging Face Serverless Inference API.

## Validações Técnicas e Diretrizes de Qualidade (Quality Assurance)

1.  **Tipagem Estática (Type Hints):** Uso estrito das anotações do módulo `typing` (ex: `np.ndarray`, `Tuple`, `List`) garantindo a integridade dos dados e tensores sendo trafegados entre os módulos geométricos.
2.  **Segurança de Execução (Try/Except):** Envelopamento integral das rotinas de cálculo complexo, com tratativas específicas para exceções de degeneração geométrica (ex: `QhullError` ou erros do motor booleano do Trimesh/Open3D).
3.  **Rigor Científico/Acadêmico:** Comentários estruturados contextualizando os pormenores matemáticos (transformações afins, equações de planos) para máxima transparência do código aberto.

## Verification Plan

### Automated Tests
- Execução sintética local simulando a linha de comando do `main_pipeline.py` para processar a malha de entrada e validar se a saída possui a estanqueidade verdadeira (`is_watertight == True`).
- Verificação do motor booleano via asserções no volume da malha de saída em relação à malha de entrada.

### Manual Verification
- Visualização do arquivo STL de saída (output) assegurando que o tubo foi precisamente escavado seguindo as diretrizes das imagens fornecidas (`earmold_tunnel_path.png`), em harmonia com a anatomia do meato acústico.
