from pathlib import Path
import pandas as pd


# ============================================================
# CONFIGURAÇÕES
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

ARQUIVO_ENTRADA = (
    BASE_DIR
    / "data"
    / "processed"
    / "tatica_arvore.csv"
)

ARQUIVO_SAIDA = (
    BASE_DIR
    / "data"
    / "processed"
    / "tatica_delta.csv"
)


# ============================================================
# COLUNAS
# ============================================================

COLUNAS_OBRIGATORIAS = [
    "UF",
    "CLUSTER REDE",
    "Promax",
    "Nome PGV",
    "Emb. Consolid.",
    "TTC Gôndola",
    "TTC mínimo ativação (un.)",
]

CHAVE_ANALISE = [
    "UF",
    "CLUSTER REDE",
    "Promax",
]


# ============================================================
# FUNÇÃO PARA CONVERTER PREÇO
# ============================================================

def normalizar_numero(valor):
    """
    Converte valores de preço para float.

    Aceita:
        3.39
        3,39
        R$ 3,39
        1.234,56
    """

    if pd.isna(valor):
        return pd.NA

    if isinstance(valor, (int, float)):
        return float(valor)

    valor = str(valor).strip()

    if not valor:
        return pd.NA

    valor = (
        valor
        .replace("R$", "")
        .replace(" ", "")
    )

    if "," in valor:
        valor = (
            valor
            .replace(".", "")
            .replace(",", ".")
        )

    try:
        return float(valor)

    except ValueError:
        return pd.NA


# ============================================================
# FUNÇÃO PARA ENCONTRAR A MODA
# ============================================================

def calcular_moda(serie):
    """
    Retorna a moda da série.

    Regras:
    - 1 única moda -> retorna o preço.
    - Mais de uma moda -> retorna NA.
    - Série vazia -> retorna NA.

    O empate não será resolvido automaticamente,
    evitando uma escolha arbitrária.
    """

    serie = serie.dropna()

    if serie.empty:
        return pd.NA

    modas = serie.mode()

    if len(modas) == 1:
        return float(modas.iloc[0])

    return pd.NA


def calcular_preco_pp(serie):
    """
    Usa a moda de TTC mínimo, considerando também os zeros.

    Só mantém PP quando a moda é positiva, única e aparece mais de uma vez.
    """

    precos = serie.dropna()
    if precos.empty:
        return 0.0

    modas = precos.mode()
    if len(modas) != 1:
        return 0.0

    preco = float(modas.iloc[0])
    if preco <= 0 or int(precos.eq(preco).sum()) < 2:
        return 0.0

    return preco


# ============================================================
# FUNÇÃO PARA IDENTIFICAR O MÉTODO
# ============================================================

def identificar_metodo(serie):
    """
    Identifica como o TTC_Tatica_Final foi determinado.
    """

    serie = serie.dropna()

    if serie.empty:
        return "SEM_PRECO"

    modas = serie.mode()

    quantidade_precos = serie.nunique()

    if quantidade_precos == 1:
        return "PREÇO ÚNICO"

    if len(modas) == 1:
        return "MODA"

    return "EMPATE_MODA"


# ============================================================
# INÍCIO
# ============================================================

print("=" * 70)
print("ANÁLISE DE DELTA E DEFINIÇÃO DO PREÇO TÁTICA")
print("=" * 70)


# ============================================================
# VERIFICAR ARQUIVO
# ============================================================

if not ARQUIVO_ENTRADA.exists():

    raise FileNotFoundError(
        f"\nArquivo não encontrado:\n"
        f"{ARQUIVO_ENTRADA}\n\n"
        f"Execute primeiro:\n"
        f"python src/tratamento.py"
    )


# ============================================================
# LEITURA
# ============================================================

print("\nLendo:")

print(ARQUIVO_ENTRADA)

df = pd.read_csv(
    ARQUIVO_ENTRADA
)

print(
    f"\nLinhas carregadas: "
    f"{len(df):,}"
)


# ============================================================
# VALIDAR COLUNAS
# ============================================================

faltantes = [
    coluna
    for coluna in COLUNAS_OBRIGATORIAS
    if coluna not in df.columns
]

if faltantes:

    raise ValueError(
        "\nColunas obrigatórias ausentes:\n"
        + "\n".join(
            f" - {coluna}"
            for coluna in faltantes
        )
    )


# ============================================================
# GARANTIR QUE REDE NÃO SEJA NECESSÁRIA
# ============================================================

if "Rede" in df.columns:

    print(
        "\nATENÇÃO: a coluna 'Rede' ainda está presente."
    )

else:

    print(
        "\nValidação: base sem coluna 'Rede'."
    )


# ============================================================
# LIMPEZA
# ============================================================

df["UF"] = (
    df["UF"]
    .astype("string")
    .str.strip()
)

df["CLUSTER REDE"] = (
    df["CLUSTER REDE"]
    .astype("string")
    .str.strip()
)

df["Promax"] = pd.to_numeric(
    df["Promax"],
    errors="coerce"
)

df["TTC Gôndola"] = (
    df["TTC Gôndola"]
    .apply(normalizar_numero)
)

df["TTC mínimo ativação (un.)"] = (
    df["TTC mínimo ativação (un.)"]
    .apply(normalizar_numero)
)


# ============================================================
# REMOVER LINHAS INVÁLIDAS
# ============================================================

linhas_antes = len(df)

df = df.dropna(
    subset=[
        "UF",
        "CLUSTER REDE",
        "Promax",
        "TTC Gôndola",
    ]
).copy()

linhas_removidas = (
    linhas_antes - len(df)
)

if linhas_removidas > 0:

    print(
        f"\nLinhas removidas por dados inválidos: "
        f"{linhas_removidas:,}"
    )


df["Promax"] = (
    df["Promax"]
    .astype(int)
)


# ============================================================
# CALCULAR MÍNIMO, MÁXIMO E QUANTIDADE DE PREÇOS
# ============================================================

delta = (
    df.groupby(
        CHAVE_ANALISE,
        as_index=False
    )
    .agg(
        TTC_Gondola_Minimo=(
            "TTC Gôndola",
            "min"
        ),

        TTC_Minimo=(
            "TTC mínimo ativação (un.)",
            calcular_preco_pp
        ),

        TTC_Maximo=(
            "TTC Gôndola",
            "max"
        ),

        Qtd_Precos=(
            "TTC Gôndola",
            "nunique"
        ),

        Qtd_Observacoes=(
            "TTC Gôndola",
            "count"
        ),
    )
)


# ============================================================
# CALCULAR MODA
# ============================================================

moda = (
    df.groupby(CHAVE_ANALISE)["TTC Gôndola"]
    .apply(calcular_moda)
    .reset_index(
        name="TTC_Tatica_Final"
    )
)

delta = delta.merge(
    moda,
    on=CHAVE_ANALISE,
    how="left",
)


# ============================================================
# IDENTIFICAR MÉTODO
# ============================================================

metodo = (
    df.groupby(CHAVE_ANALISE)["TTC Gôndola"]
    .apply(identificar_metodo)
    .reset_index(
        name="Metodo"
    )
)

delta = delta.merge(
    metodo,
    on=CHAVE_ANALISE,
    how="left",
)


# ============================================================
# DELTA ABSOLUTO
# ============================================================

delta["Delta_TTC"] = (
    delta["TTC_Maximo"]
    - delta["TTC_Gondola_Minimo"]
)


# ============================================================
# DELTA PERCENTUAL
# ============================================================

delta["Delta_%"] = pd.NA

mask = (
    delta["TTC_Gondola_Minimo"] > 0
)

delta.loc[mask, "Delta_%"] = (
    (
        delta.loc[mask, "TTC_Maximo"]
        /
        delta.loc[mask, "TTC_Gondola_Minimo"]
    )
    - 1
) * 100


# ============================================================
# INFORMAÇÕES DO PRODUTO
# ============================================================

produto_info = (
    df.groupby(
        "Promax",
        as_index=False
    )
    .agg(
        Nome_PGV=(
            "Nome PGV",
            "first"
        ),

        Emb_Consolid=(
            "Emb. Consolid.",
            "first"
        ),
    )
)


delta = delta.merge(
    produto_info,
    on="Promax",
    how="left",
)


# ============================================================
# PREÇO DA MODA
# ============================================================

# Caso exista empate entre modas, TTC_Tatica_Final
# permanece vazio e será analisado separadamente.


# ============================================================
# ORGANIZAR COLUNAS
# ============================================================

delta = delta[
    [
        "UF",
        "CLUSTER REDE",
        "Promax",
        "Nome_PGV",
        "Emb_Consolid",
        "TTC_Minimo",
        "TTC_Gondola_Minimo",
        "TTC_Maximo",
        "Delta_TTC",
        "Delta_%",
        "Qtd_Precos",
        "Qtd_Observacoes",
        "TTC_Tatica_Final",
        "Metodo",
    ]
]


# ============================================================
# ORDENAÇÃO
# ============================================================

delta = delta.sort_values(
    [
        "UF",
        "CLUSTER REDE",
        "Promax",
    ]
).reset_index(
    drop=True
)


# ============================================================
# SALVAR
# ============================================================

ARQUIVO_SAIDA.parent.mkdir(
    parents=True,
    exist_ok=True
)

delta.to_csv(
    ARQUIVO_SAIDA,
    index=False,
    encoding="utf-8-sig",
    decimal=",",
)


# ============================================================
# RESUMO
# ============================================================

print("\n" + "=" * 70)
print("RESUMO DA ANÁLISE")
print("=" * 70)

print(
    f"\nCombinações analisadas: "
    f"{len(delta):,}"
)

print(
    f"Preço único: "
    f"{(delta['Metodo'] == 'PREÇO ÚNICO').sum():,}"
)

print(
    f"Moda utilizada: "
    f"{(delta['Metodo'] == 'MODA').sum():,}"
)

print(
    f"Empate de moda: "
    f"{(delta['Metodo'] == 'EMPATE_MODA').sum():,}"
)

print(
    f"Sem preço: "
    f"{(delta['Metodo'] == 'SEM_PRECO').sum():,}"
)


# ============================================================
# DIVERGÊNCIAS
# ============================================================

divergencias = delta[
    delta["Qtd_Precos"] > 1
].copy()

print("\n" + "=" * 70)
print("DIVERGÊNCIAS DE PREÇO")
print("=" * 70)

print(
    f"\nCombinações com mais de um preço: "
    f"{len(divergencias):,}"
)


if len(divergencias) > 0:

    print(
        divergencias[
            [
                "UF",
                "CLUSTER REDE",
                "Promax",
                "TTC_Gondola_Minimo",
                "TTC_Maximo",
                "Delta_TTC",
                "Delta_%",
                "Qtd_Precos",
                "TTC_Tatica_Final",
                "Metodo",
            ]
        ].to_string(
            index=False
        )
    )


# ============================================================
# EMPATES DE MODA
# ============================================================

empates = delta[
    delta["Metodo"] == "EMPATE_MODA"
].copy()

print("\n" + "=" * 70)
print("EMPATES DE MODA")
print("=" * 70)

if len(empates) == 0:

    print(
        "\nNenhum empate de moda encontrado."
    )

else:

    print(
        f"\nForam encontrados "
        f"{len(empates)} empates."
    )

    print(
        empates[
            [
                "UF",
                "CLUSTER REDE",
                "Promax",
                "Nome_PGV",
                "TTC_Gondola_Minimo",
                "TTC_Maximo",
                "Qtd_Precos",
            ]
        ].to_string(
            index=False
        )
    )


# ============================================================
# TOP MAIORES DELTAS
# ============================================================

print("\n" + "=" * 70)
print("TOP 20 MAIORES DELTAS")
print("=" * 70)

top_delta = (
    delta
    .sort_values(
        "Delta_%",
        ascending=False
    )
    .head(20)
)

print(
    top_delta[
        [
            "UF",
            "CLUSTER REDE",
            "Promax",
            "TTC_Gondola_Minimo",
            "TTC_Maximo",
            "Delta_TTC",
            "Delta_%",
            "Qtd_Precos",
            "TTC_Tatica_Final",
            "Metodo",
        ]
    ].to_string(
        index=False
    )
)


# ============================================================
# DISTRIBUIÇÃO DO DELTA
# ============================================================

print("\n" + "=" * 70)
print("DISTRIBUIÇÃO DO DELTA %")
print("=" * 70)

faixas = pd.cut(
    delta["Delta_%"],
    bins=[
        -0.000001,
        0,
        1,
        2,
        5,
        10,
        20,
        float("inf"),
    ],
    labels=[
        "0%",
        ">0% até 1%",
        ">1% até 2%",
        ">2% até 5%",
        ">5% até 10%",
        ">10% até 20%",
        ">20%",
    ],
)

distribuicao = (
    faixas
    .value_counts(
        sort=False
    )
    .rename_axis(
        "Faixa"
    )
    .reset_index(
        name="Quantidade"
    )
)

print(
    distribuicao.to_string(
        index=False
    )
)


# ============================================================
# ARQUIVO FINAL
# ============================================================

print("\n" + "=" * 70)
print("ARQUIVO GERADO")
print("=" * 70)

print(
    f"\n{ARQUIVO_SAIDA}"
)

print(
    "\nA análise foi concluída com sucesso."
)

print("=" * 70)