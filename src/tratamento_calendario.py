# =============================================================================
# TRATAMENTO_CALENDARIO.PY
# ÁRVORE DE PREÇOS
# Tratamento do Calendário Direta
# =============================================================================

from pathlib import Path
import pandas as pd


# =============================================================================
# 1. CONFIGURAÇÕES
# =============================================================================

ROOT = Path(__file__).resolve().parents[1]

# Arquivo original
ARQUIVO_CALENDARIO = (
    ROOT
    / "data"
    / "unprocessed"
    / "Calendario Direta Outubro.xlsx"
)

# Arquivo processado
ARQUIVO_CALENDARIO_PROCESSADO = (
    ROOT
    / "data"
    / "processed"
    / "calendario_arvore.csv"
)

# Aba utilizada
ABA_CALENDARIO = "Calendário"


# =============================================================================
# 2. PROMAX DA ÁRVORE
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


# =============================================================================
# 3. FUNÇÕES AUXILIARES
# =============================================================================

def normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove espaços extras dos nomes das colunas.

    Mantém a capitalização original da planilha.
    """

    df = df.copy()

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

        print("\nColunas encontradas no arquivo:")

        for coluna in df.columns:
            print(f"  - {repr(coluna)}")

        raise ValueError(
            "\nColunas obrigatórias não encontradas "
            "no Calendário:\n"
            + "\n".join(
                f"- {coluna}"
                for coluna in faltantes
            )
        )


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
    e quais estão ausentes no Calendário.
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


def validar_duplicidades(
    df: pd.DataFrame
) -> pd.DataFrame:
    """
    Identifica duplicidades na combinação:

        UF + CLUSTER + Promax

    Essa é a granularidade esperada para o Calendário.
    """

    duplicidades = (
        df
        .groupby(
            [
                "UF",
                "CLUSTER",
                "Promax",
            ],
            dropna=False
        )
        .size()
        .reset_index(
            name="Quantidade"
        )
    )

    duplicidades = duplicidades[
        duplicidades["Quantidade"] > 1
    ]

    return duplicidades


def mostrar_duplicidades(
    df: pd.DataFrame,
    duplicidades: pd.DataFrame
) -> None:
    """
    Mostra os registros que possuem duplicidade
    na combinação UF + CLUSTER + Promax.
    """

    if duplicidades.empty:

        print(
            "Nenhuma duplicidade encontrada."
        )

        return

    chaves = duplicidades[
        [
            "UF",
            "CLUSTER",
            "Promax",
        ]
    ]

    detalhes = df.merge(
        chaves,
        on=[
            "UF",
            "CLUSTER",
            "Promax",
        ],
        how="inner"
    )

    print("\n")
    print("=" * 100)
    print(
        "DETALHAMENTO DAS DUPLICIDADES — "
        "UF + CLUSTER + PROMAX"
    )
    print("=" * 100)

    print(
        detalhes.to_string(
            index=False
        )
    )


# =============================================================================
# 4. CARREGAR CALENDÁRIO
# =============================================================================

def carregar_calendario() -> pd.DataFrame:
    """
    Carrega somente a aba Calendário.

    O cabeçalho está na linha 3 do Excel,
    portanto usamos header=2.
    """

    if not ARQUIVO_CALENDARIO.exists():

        raise FileNotFoundError(
            "Arquivo do Calendário não encontrado:\n"
            f"{ARQUIVO_CALENDARIO}"
        )

    df = pd.read_excel(
        ARQUIVO_CALENDARIO,
        sheet_name=ABA_CALENDARIO,
        header=2,
    )

    df = normalizar_colunas(df)

    return df


# =============================================================================
# 5. PREPARAR CALENDÁRIO
# =============================================================================

def preparar_calendario() -> pd.DataFrame:
    """
    Executa todo o tratamento do Calendário.

    Processo:

    1. Carrega a aba Calendário.
    2. Valida as colunas.
    3. Normaliza Promax.
    4. Mantém somente os 31 Promax da árvore.
    5. Valida Promax faltantes.
    6. Valida duplicidades por UF + CLUSTER + Promax.
    7. Seleciona as colunas necessárias.
    8. Ordena.
    9. Salva o CSV processado.
    """

    # =========================================================================
    # 5.1 CARREGAR
    # =========================================================================

    calendario = carregar_calendario()

    linhas_originais = len(calendario)

    # =========================================================================
    # 5.2 VALIDAR COLUNAS
    # =========================================================================

    colunas_obrigatorias = [
        "Promax",
        "UF",
        "CLUSTER",
        "TTC Var",
    ]

    validar_colunas(
        calendario,
        colunas_obrigatorias
    )

    # =========================================================================
    # 5.3 NORMALIZAR PROMAX
    # =========================================================================

    calendario = normalizar_promax(
        calendario
    )
    calendario["UF"] = (
        calendario["UF"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    # =========================================================================
    # 5.4 REMOVER LINHAS SEM PROMAX
    # =========================================================================

    calendario = calendario[
        calendario["Promax"].notna()
    ].copy()

    calendario["Promax"] = (
        calendario["Promax"]
        .astype(int)
    )

    # =========================================================================
    # 5.5 FILTRAR SOMENTE OS PROMAX DA ÁRVORE
    # =========================================================================

    calendario_arvore = calendario[
        calendario["Promax"].isin(
            PROMAX_ARVORE
        )
    ].copy()

    # =========================================================================
    # 5.6 VALIDAR PROMAX
    # =========================================================================

    validacao_promax = (
        validar_promax_arvore(
            calendario_arvore
        )
    )

    # =========================================================================
    # 5.7 VALIDAR DUPLICIDADES
    # =========================================================================

    duplicidades = validar_duplicidades(
        calendario_arvore
    )

    # =========================================================================
    # 5.8 SELECIONAR SOMENTE AS COLUNAS NECESSÁRIAS
    # =========================================================================

    colunas_saida = [
        "Promax",
        "UF",
        "CLUSTER",
        "TTC Var",
    ]

    calendario_arvore = calendario_arvore[
        colunas_saida
    ].copy()

    # =========================================================================
    # 5.9 ORDENAR
    # =========================================================================

    calendario_arvore = (
        calendario_arvore
        .sort_values(
            [
                "UF",
                "CLUSTER",
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

    ARQUIVO_CALENDARIO_PROCESSADO.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # =========================================================================
    # 5.11 SALVAR
    # =========================================================================

    calendario_arvore.to_csv(
        ARQUIVO_CALENDARIO_PROCESSADO,
        index=False,
        encoding="utf-8-sig"
    )

    # =========================================================================
    # 5.12 RELATÓRIO
    # =========================================================================

    print("\n")
    print("=" * 80)
    print(
        "TRATAMENTO DO CALENDÁRIO — "
        "ÁRVORE DE PREÇOS"
    )
    print("=" * 80)

    print("\nARQUIVO:")
    print(ARQUIVO_CALENDARIO)

    print("\nABA:")
    print(ABA_CALENDARIO)

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
        f"{len(calendario_arvore):,}"
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
            "\nPROMAX NÃO ENCONTRADOS:"
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
    # CLUSTER
    # -------------------------------------------------------------------------

    print("\n")
    print("-" * 80)
    print("CLUSTER")
    print("-" * 80)

    print(
        calendario_arvore[
            "CLUSTER"
        ]
        .value_counts(
            dropna=False
        )
        .to_string()
    )

    # -------------------------------------------------------------------------
    # DUPLICIDADES
    # -------------------------------------------------------------------------

    print("\n")
    print("-" * 80)
    print("DUPLICIDADES")
    print("-" * 80)

    print(
        "Duplicidades "
        "UF + CLUSTER + Promax: "
        f"{len(duplicidades):,}"
    )

    if not duplicidades.empty:

        mostrar_duplicidades(
            calendario,
            duplicidades
        )

    else:

        print(
            "OK: não existem duplicidades "
            "na combinação "
            "UF + CLUSTER + Promax."
        )

    # -------------------------------------------------------------------------
    # ARQUIVO PROCESSADO
    # -------------------------------------------------------------------------

    print("\n")
    print("-" * 80)
    print("ARQUIVO PROCESSADO")
    print("-" * 80)

    print(
        "Salvo em:\n"
        f"{ARQUIVO_CALENDARIO_PROCESSADO}"
    )

    # =========================================================================
    # 5.13 FINALIZAÇÃO
    # =========================================================================

    print("\n")
    print("=" * 80)
    print(
        "TRATAMENTO DO CALENDÁRIO CONCLUÍDO"
    )
    print("=" * 80)

    return calendario_arvore


# =============================================================================
# 6. EXECUÇÃO DIRETA
# =============================================================================

if __name__ == "__main__":

    calendario_arvore = preparar_calendario()

    print("\n")
    print("=" * 80)
    print(
        "PRIMEIRAS 20 LINHAS DO "
        "CALENDÁRIO PROCESSADO"
    )
    print("=" * 80)

    print(
        calendario_arvore
        .head(20)
        .to_string(
            index=False
        )
    )