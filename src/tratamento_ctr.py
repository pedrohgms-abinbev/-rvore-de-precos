from __future__ import annotations

from pathlib import Path

import pandas as pd


# =============================================================================
# 1. CONFIGURAÇÕES
# =============================================================================

ROOT = Path(__file__).resolve().parents[1]

ARQUIVO_CTR = (
    ROOT
    / "data"
    / "unprocessed"
    / "CTR - Árvore de Preços.xlsx"
)

ARQUIVO_CTR_PROCESSADO = (
    ROOT
    / "data"
    / "processed"
    / "ctr_arvore.csv"
)

ABA_CTR = "Share"

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

UF_POR_MERCADO = {
    "uf manaus - as+c&c": "AM",
    "uf mato grosso - as+c&c": "MT",
    "uf goias - as+c&c": "GO",
    "uf distrito federal - as+c&c": "DF",
    "uf mato grosso do sul - as+c&c": "MS",
    "no: as+c&c": ["AC", "RO"],
}


# =============================================================================
# 2. FUNÇÕES AUXILIARES
# =============================================================================

def normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(coluna).strip() for coluna in df.columns]
    return df


def validar_colunas(
    df: pd.DataFrame,
    colunas_obrigatorias: list[str],
) -> None:
    faltantes = [
        coluna
        for coluna in colunas_obrigatorias
        if coluna not in df.columns
    ]
    if faltantes:
        raise ValueError(
            "Colunas obrigatórias não encontradas no CTR:\n"
            + "\n".join(f"- {coluna}" for coluna in faltantes)
        )


def normalizar_promax(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["PROMAX"] = pd.to_numeric(df["PROMAX"], errors="coerce")
    return df


def validar_promax_arvore(df: pd.DataFrame) -> dict[str, list[int]]:
    esperados = set(PROMAX_ARVORE)
    encontrados = set(
        df["Promax"].dropna().astype(int).unique()
    )
    return {
        "esperados": sorted(esperados),
        "encontrados": sorted(esperados & encontrados),
        "faltantes": sorted(esperados - encontrados),
    }


# =============================================================================
# 3. CÁLCULO DO CTR L3M
# =============================================================================

def tratamento_ctr_l3m(
    dados: pd.DataFrame,
    coluna_produto: str = "PROMAX",
    coluna_uf: str = "UF",
    coluna_vendas: str = "Vendas Normalizadas in hl",
    coluna_m0: str = "m0",
    promax_arvore: list[int] | None = None,
) -> pd.DataFrame:
    """Calcula participação L3M e retorna apenas os Promax da árvore."""
    colunas_exigidas = {
        coluna_produto,
        coluna_uf,
        coluna_vendas,
        coluna_m0,
    }
    colunas_ausentes = colunas_exigidas.difference(dados.columns)
    if colunas_ausentes:
        colunas = ", ".join(sorted(colunas_ausentes))
        raise ValueError(f"Colunas ausentes para o CTR L3M: {colunas}")

    produtos_arvore = (
        PROMAX_ARVORE if promax_arvore is None else promax_arvore
    )
    dados = dados.copy()
    dados[coluna_produto] = pd.to_numeric(
        dados[coluna_produto], errors="coerce"
    )
    dados[coluna_vendas] = pd.to_numeric(
        dados[coluna_vendas], errors="raise"
    )
    dados[coluna_m0] = pd.to_numeric(dados[coluna_m0], errors="coerce")
    dados = dados.dropna(subset=[coluna_uf, coluna_m0]).copy()
    dados[coluna_uf] = dados[coluna_uf].astype("string").str.strip().str.upper()
    dados_l3m = dados.loc[dados[coluna_m0].isin([-1, -2, -3])].copy()

    if dados_l3m.empty:
        raise ValueError(
            "Não há linhas com M0 igual a -1, -2 ou -3 para calcular o CTR L3M."
        )

    vendas_total_uf = (
        dados_l3m.groupby(coluna_uf, as_index=False)[coluna_vendas]
        .sum()
        .rename(columns={coluna_vendas: "Vendas Total UF L3M"})
    )

    vendas_por_produto_uf = (
        dados_l3m.dropna(subset=[coluna_produto])
        .groupby([coluna_uf, coluna_produto], as_index=False)[coluna_vendas]
        .sum()
        .rename(
            columns={
                coluna_produto: "Promax",
                coluna_vendas: "Vendas L3M",
            }
        )
    )
    vendas_por_produto_uf = vendas_por_produto_uf.loc[
        vendas_por_produto_uf["Promax"].isin(produtos_arvore)
    ].copy()
    vendas_por_produto_uf["Promax"] = (
        vendas_por_produto_uf["Promax"].astype(int)
    )

    ctr_l3m = vendas_por_produto_uf.merge(
        vendas_total_uf,
        left_on=coluna_uf,
        right_on=coluna_uf,
        how="left",
        validate="many_to_one",
    )
    ctr_l3m["CTR L3M"] = (
        ctr_l3m["Vendas L3M"]
        .div(ctr_l3m["Vendas Total UF L3M"])
        .where(ctr_l3m["Vendas Total UF L3M"] != 0)
    )

    return (
        ctr_l3m[
            [
                coluna_uf,
                "Promax",
                "Vendas L3M",
                "Vendas Total UF L3M",
                "CTR L3M",
            ]
        ]
        .rename(columns={coluna_uf: "UF"})
        .sort_values(["UF", "Promax"])
        .reset_index(drop=True)
    )


def transformar_para_streamlit(dados: pd.DataFrame) -> pd.DataFrame:
    """Alias para gerar o resultado CTR L3M consumido pelo Streamlit."""
    return tratamento_ctr_l3m(dados)


# =============================================================================
# 4. CARREGAR E PREPARAR CTR
# =============================================================================

def carregar_ctr() -> pd.DataFrame:
    if not ARQUIVO_CTR.exists():
        raise FileNotFoundError(
            f"Arquivo do CTR não encontrado:\n{ARQUIVO_CTR}"
        )

    return normalizar_colunas(
        pd.read_excel(ARQUIVO_CTR, sheet_name=ABA_CTR)
    )


def preparar_ctr() -> pd.DataFrame:
    ctr = carregar_ctr()
    linhas_originais = len(ctr)

    colunas_obrigatorias = [
        "PROMAX",
        "Long Mkt",
        "Vendas Normalizadas in hl",
        "m0",
    ]
    validar_colunas(ctr, colunas_obrigatorias)

    ctr = normalizar_promax(ctr)

    linhas_uf: list[dict[str, object]] = []
    for _, linha in ctr.iterrows():
        chave = str(linha["Long Mkt"]).strip().casefold()
        ufs = UF_POR_MERCADO.get(chave)
        if ufs is None:
            linhas_uf.append({**linha.to_dict(), "UF": pd.NA})
            continue
        if isinstance(ufs, str):
            ufs = [ufs]
        for uf in ufs:
            nova_linha = linha.to_dict()
            nova_linha["UF"] = uf
            linhas_uf.append(nova_linha)

    ctr = pd.DataFrame(linhas_uf)

    ctr["m0"] = pd.to_numeric(ctr["m0"], errors="coerce")
    ctr["Vendas Normalizadas in hl"] = pd.to_numeric(
        ctr["Vendas Normalizadas in hl"], errors="coerce"
    )

    mercados_nao_mapeados = sorted(
        ctr.loc[ctr["UF"].isna(), "Long Mkt"]
        .dropna()
        .astype(str)
        .unique()
    )
    ctr = ctr.dropna(
        subset=["UF", "m0", "Vendas Normalizadas in hl"]
    ).copy()
    ctr = ctr.loc[ctr["m0"].isin([-1, -2, -3])].copy()

    resultado = tratamento_ctr_l3m(ctr)
    validacao_promax = validar_promax_arvore(resultado)

    ARQUIVO_CTR_PROCESSADO.parent.mkdir(parents=True, exist_ok=True)
    resultado.to_csv(
        ARQUIVO_CTR_PROCESSADO,
        index=False,
        encoding="utf-8-sig",
    )

    print("\n")
    print("=" * 80)
    print("TRATAMENTO DO CTR L3M — ÁRVORE DE PREÇOS")
    print("=" * 80)

    print("\nARQUIVO:")
    print(ARQUIVO_CTR)

    print("\nABA:")
    print(ABA_CTR)

    print("\n")
    print("-" * 80)
    print("VOLUME")
    print("-" * 80)
    print(f"Linhas originais: {linhas_originais:,}")
    print(f"Linhas dos meses M0 -1, -2 e -3: {len(ctr):,}")
    print(f"Linhas após filtro dos Promax da árvore: {len(resultado):,}")
    print("Mercados sem UF individual mapeada:")
    if mercados_nao_mapeados:
        for mercado in mercados_nao_mapeados:
            print(f"  - {mercado}")
    else:
        print("  Nenhum")

    print("\n")
    print("-" * 80)
    print("PROMAX")
    print("-" * 80)
    print(f"Promax esperados: {len(PROMAX_ARVORE)}")
    print(f"Promax encontrados: {len(validacao_promax['encontrados'])}")
    if validacao_promax["faltantes"]:
        print("\nPROMAX NÃO ENCONTRADOS:")
        for promax in validacao_promax["faltantes"]:
            print(f"  - {promax}")
    else:
        print("Todos os Promax da árvore foram encontrados.")

    print("\n")
    print("-" * 80)
    print("ARQUIVO PROCESSADO")
    print("-" * 80)
    print(f"Salvo em:\n{ARQUIVO_CTR_PROCESSADO}")

    return resultado


if __name__ == "__main__":
    preparar_ctr()
