# =============================================================================
# TRATAMENTO.PY
# ÁRVORE DE PREÇOS
# Tratamento da Tática Final
# =============================================================================

from pathlib import Path
import pandas as pd


# =============================================================================
# 1. CONFIGURAÇÕES
# =============================================================================

# Diretório raiz do projeto
ROOT = Path(__file__).resolve().parents[1]

# Arquivo original da Tática
ARQUIVO_TATICA = (
    ROOT
    / "data"
    / "unprocessed"
    / "10. Tatica Cerveja.xlsx"
)

# Arquivo processado que será gerado
ARQUIVO_TATICA_PROCESSADA = (
    ROOT
    / "data"
    / "processed"
    / "tatica_arvore.csv"
)

# Aba utilizada no Excel
ABA_TATICA = "Tatica Final"


# =============================================================================
# 2. PROMAX QUE FARÃO PARTE DA ÁRVORE
# =============================================================================

PROMAX_ARVORE = [
    1898,
    1745,
    9224,
    31064,
    20647,
    21946,
    26204,
    1699,
    32498,
    32392,
    12948,
    9069,
    9068,
    9067,
    20498,
    22177,
    21020,
    19668,
    21658,
    4262,
    19729,
    32500,
    20651,
    22180,
    17808,
    30942,
    18780,
    24168,
    18807,
    29580,
    18836,
]

REDES_ECOMMERCE = {
    "AMAZON",
    "LOJAS AMERICANAS",
    "MAGAZINE LUIZA S/A",
    "SHOPPER",
}


# =============================================================================
# 3. FUNÇÕES AUXILIARES
# =============================================================================

def normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove espaços extras dos nomes das colunas.

    Como a Tática possui cabeçalho em duas linhas, o Excel é
    inicialmente carregado como MultiIndex. Aqui utilizamos
    o primeiro nível do cabeçalho.
    """

    df = df.copy()

    if isinstance(df.columns, pd.MultiIndex):

        df.columns = [
            str(col[0]).strip()
            for col in df.columns
        ]

    else:

        df.columns = [
            str(col).strip()
            for col in df.columns
        ]

    return df


def validar_colunas(
    df: pd.DataFrame,
    colunas_obrigatorias: list[str]
) -> None:
    """
    Verifica se todas as colunas necessárias existem.
    """

    faltantes = [
        coluna
        for coluna in colunas_obrigatorias
        if coluna not in df.columns
    ]

    if faltantes:

        mensagem = (
            "Colunas obrigatórias não encontradas "
            "na Tática:\n"
        )

        mensagem += "\n".join(
            f"- {coluna}"
            for coluna in faltantes
        )

        raise ValueError(mensagem)


def normalizar_promax(
    df: pd.DataFrame
) -> pd.DataFrame:
    """
    Converte Promax para formato numérico.
    """

    df = df.copy()

    df["Promax"] = pd.to_numeric(
        df["Promax"],
        errors="coerce"
    )

    return df


def validar_promax_arvore(
    df: pd.DataFrame
) -> dict:
    """
    Verifica quais Promax da árvore estão presentes
    e quais estão ausentes na Tática.
    """

    esperados = set(PROMAX_ARVORE)

    encontrados = set(
        df["Promax"]
        .dropna()
        .astype(int)
        .unique()
    )

    encontrados_arvore = sorted(
        esperados & encontrados
    )

    faltantes = sorted(
        esperados - encontrados
    )

    return {
        "esperados": sorted(esperados),
        "encontrados": encontrados_arvore,
        "faltantes": faltantes,
    }


def validar_granularidade(
    df: pd.DataFrame
) -> pd.Series:
    """
    Verifica se existe mais de um TTC Gôndola
    para a mesma combinação:

        UF
        Rede
        CLUSTER REDE
        Promax

    Essa é a granularidade da Tática.
    """

    grupo = (
        df
        .groupby(
            [
                "UF",
                "Rede",
                "CLUSTER REDE",
                "Promax",
            ],
            dropna=False
        )["TTC Gôndola"]
        .nunique(dropna=True)
    )

    conflitos = grupo[
        grupo > 1
    ]

    return conflitos


def mostrar_conflitos(
    df: pd.DataFrame,
    conflitos: pd.Series
) -> None:
    """
    Mostra os registros que possuem mais de um TTC
    dentro da mesma chave.
    """

    if conflitos.empty:

        print(
            "Nenhum conflito encontrado."
        )

        return

    chaves = conflitos.reset_index()[
        [
            "UF",
            "Rede",
            "CLUSTER REDE",
            "Promax",
        ]
    ]

    detalhes = df.merge(
        chaves,
        on=[
            "UF",
            "Rede",
            "CLUSTER REDE",
            "Promax",
        ],
        how="inner",
    )

    detalhes = detalhes[
        [
            "UF",
            "Rede",
            "CLUSTER REDE",
            "Promax",
            "Nome PGV",
            "Emb. Consolid.",
            "TTC Gôndola",
        ]
    ].sort_values(
        [
            "UF",
            "Rede",
            "CLUSTER REDE",
            "Promax",
            "TTC Gôndola",
        ]
    )

    print("\n")
    print("=" * 80)
    print("CONFLITOS ENCONTRADOS")
    print("=" * 80)

    print(
        detalhes.to_string(
            index=False
        )
    )


# =============================================================================
# 4. LEITURA DA TÁTICA
# =============================================================================

def carregar_tatica() -> pd.DataFrame:
    """
    Carrega a aba 'Tatica Final' do Excel.

    O cabeçalho está nas linhas 3 e 4 da planilha.
    Por isso usamos header=[2, 3].
    """

    if not ARQUIVO_TATICA.exists():

        raise FileNotFoundError(
            "Arquivo da Tática não encontrado:\n"
            f"{ARQUIVO_TATICA}"
        )

    df = pd.read_excel(
        ARQUIVO_TATICA,
        sheet_name=ABA_TATICA,
        header=[2, 3],
    )

    df = normalizar_colunas(df)

    return df


# =============================================================================
# 5. PREPARAR TÁTICA
# =============================================================================

def preparar_tatica() -> pd.DataFrame:
    """
    Executa todo o tratamento da Tática.

    Processo:

    1. Carrega o Excel.
    2. Lê a aba Tatica Final.
    3. Normaliza as colunas.
    4. Valida as colunas necessárias.
    5. Normaliza Promax.
    6. Mantém somente os 31 Promax da árvore.
    7. Valida se algum Promax está faltando.
    8. Valida a granularidade.
    9. Seleciona as colunas necessárias.
    10. Ordena os dados.
    11. Salva o resultado em data/processed.
    """

    # =========================================================================
    # 5.1 CARREGAR TÁTICA
    # =========================================================================

    tatica = carregar_tatica()

    linhas_originais = len(tatica)

    # =========================================================================
    # 5.2 VALIDAR COLUNAS
    # =========================================================================

    colunas_obrigatorias = [
        "Promax",
        "UF",
        "Rede",
        "CLUSTER REDE",
        "Emb. Consolid.",
        "Nome PGV",
        "TTC Gôndola",
        "TTC mínimo ativação (un.)",
    ]

    validar_colunas(
        tatica,
        colunas_obrigatorias
    )

    rede_normalizada = (
        tatica["Rede"]
        .astype("string")
        .str.strip()
        .str.upper()
    )
    linhas_ecommerce = rede_normalizada.isin(
        REDES_ECOMMERCE
    )
    quantidade_ecommerce_removida = int(
        linhas_ecommerce.sum()
    )
    tatica = tatica[~linhas_ecommerce].copy()

    # =========================================================================
    # 5.3 NORMALIZAR PROMAX
    # =========================================================================

    tatica = normalizar_promax(
        tatica
    )

    # =========================================================================
    # 5.4 REMOVER LINHAS SEM PROMAX
    # =========================================================================

    tatica = tatica[
        tatica["Promax"].notna()
    ].copy()

    tatica["Promax"] = (
        tatica["Promax"]
        .astype(int)
    )

    # =========================================================================
    # 5.5 FILTRAR SOMENTE OS PRODUTOS DA ÁRVORE
    # =========================================================================

    tatica_arvore = tatica[
        tatica["Promax"].isin(
            PROMAX_ARVORE
        )
    ].copy()

    # =========================================================================
    # 5.6 VALIDAR PROMAX
    # =========================================================================

    validacao_promax = (
        validar_promax_arvore(
            tatica_arvore
        )
    )

    # =========================================================================
    # 5.7 VALIDAR GRANULARIDADE
    # =========================================================================

    conflitos = validar_granularidade(
        tatica_arvore
    )

    if not conflitos.empty:
        mostrar_conflitos(
            tatica_arvore,
            conflitos
        )
        raise ValueError(
            "A Tática contém mais de um TTC para a mesma "
            "combinação de UF, Rede, CLUSTER REDE e Promax."
        )

    # =========================================================================
    # 5.8 SELECIONAR COLUNAS NECESSÁRIAS
    # =========================================================================

    colunas_saida = [
        "UF",
        "CLUSTER REDE",
        "Promax",
        "Nome PGV",
        "Emb. Consolid.",
        "TTC Gôndola",
        "TTC mínimo ativação (un.)",
    ]

    # =========================================================================
    # 5.9 ORDENAR
    # =========================================================================

    tatica_arvore = (
        tatica_arvore
        .sort_values(
            [
                "UF",
                "CLUSTER REDE",
                "Promax",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    # =========================================================================
    # 5.10 CRIAR PASTA PROCESSED
    # =========================================================================

    ARQUIVO_TATICA_PROCESSADA.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # =========================================================================
    # 5.11 SALVAR CSV PROCESSADO
    # =========================================================================

    tatica_arvore[
        colunas_saida
    ].to_csv(
        ARQUIVO_TATICA_PROCESSADA,
        index=False,
        encoding="utf-8-sig"
    )

    # =========================================================================
    # 5.12 RELATÓRIO
    # =========================================================================

    print("\n")
    print("=" * 80)
    print("TRATAMENTO DA TÁTICA — ÁRVORE DE PREÇOS")
    print("=" * 80)

    print("\nARQUIVO:")
    print(ARQUIVO_TATICA)

    print("\nABA:")
    print(ABA_TATICA)

    # -------------------------------------------------------------------------
    # Volume
    # -------------------------------------------------------------------------

    print("\n")
    print("-" * 80)
    print("VOLUME")
    print("-" * 80)

    print(
        f"Linhas originais: "
        f"{linhas_originais:,}"
    )

    print(
        f"Linhas após filtro dos Promax: "
        f"{len(tatica_arvore):,}"
    )

    print(
        f"Linhas removidas por rede e-commerce: "
        f"{quantidade_ecommerce_removida:,}"
    )

    # -------------------------------------------------------------------------
    # Promax
    # -------------------------------------------------------------------------

    print("\n")
    print("-" * 80)
    print("PROMAX")
    print("-" * 80)

    print(
        f"Promax esperados: "
        f"{len(PROMAX_ARVORE)}"
    )

    print(
        f"Promax encontrados: "
        f"{len(validacao_promax['encontrados'])}"
    )

    if validacao_promax["faltantes"]:

        print(
            "\nATENÇÃO — PROMAX NÃO ENCONTRADOS:"
        )

        for promax in (
            validacao_promax["faltantes"]
        ):
            print(
                f"  - {promax}"
            )

    else:

        print(
            "Todos os Promax da árvore "
            "foram encontrados."
        )

    # -------------------------------------------------------------------------
    # Granularidade
    # -------------------------------------------------------------------------

    print("\n")
    print("-" * 80)
    print("GRANULARIDADE")
    print("-" * 80)

    grupo = (
        tatica_arvore
        .groupby(
            [
                "UF",
                "Rede",
                "CLUSTER REDE",
                "Promax",
            ],
            dropna=False
        )
        .size()
    )

    print(
        "Combinações "
        "UF + Rede + CLUSTER REDE + Promax: "
        f"{len(grupo):,}"
    )

    print(
        "Combinações com mais de um TTC: "
        f"{len(conflitos):,}"
    )

    if conflitos.empty:

        print(
            "\nOK: não existem conflitos de TTC "
            "dentro da granularidade definida."
        )

    # -------------------------------------------------------------------------
    # Promax encontrados
    # -------------------------------------------------------------------------

    print("\n")
    print("-" * 80)
    print("PROMAX ENCONTRADOS")
    print("-" * 80)

    print(
        sorted(
            tatica_arvore[
                "Promax"
            ].unique()
        )
    )

    # -------------------------------------------------------------------------
    # Arquivo processado
    # -------------------------------------------------------------------------

    print("\n")
    print("-" * 80)
    print("ARQUIVO PROCESSADO")
    print("-" * 80)

    print(
        f"Salvo em:\n"
        f"{ARQUIVO_TATICA_PROCESSADA}"
    )

    # =========================================================================
    # 5.13 FINALIZAÇÃO
    # =========================================================================

    print("\n")
    print("=" * 80)
    print("TRATAMENTO CONCLUÍDO")
    print("=" * 80)

    return tatica_arvore[
        colunas_saida
    ]


# =============================================================================
# 6. EXECUÇÃO DIRETA
# =============================================================================

if __name__ == "__main__":

    tatica_arvore = preparar_tatica()

    print("\n")
    print("=" * 80)
    print("PRIMEIRAS 20 LINHAS DA TÁTICA PROCESSADA")
    print("=" * 80)

    print(
        tatica_arvore
        .head(20)
        .to_string(index=False)
    )