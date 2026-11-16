from pathlib import Path
import pandas as pd


# ============================================================
# CONFIGURAÇÕES
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

ARQUIVO_DE_PARA = (
    BASE_DIR
    / "cadastro"
    / "de_para.xlsx"
)

ARQUIVO_TATICA = (
    BASE_DIR
    / "data"
    / "processed"
    / "tatica_delta.csv"
)

ARQUIVO_CALENDARIO = (
    BASE_DIR
    / "data"
    / "processed"
    / "calendario_arvore.csv"
)

ARQUIVO_SAIDA = (
    BASE_DIR
    / "data"
    / "processed"
    / "arvore_precos.csv"
)


# ============================================================
# COLUNAS
# ============================================================

COLUNAS_DE_PARA = [
    "Promax",
    "Nome",
    "Nome Abreviado",
    "NomeImg",
]

COLUNAS_TATICA = [
    "UF",
    "CLUSTER REDE",
    "Promax",
    "TTC_Minimo",
    "TTC_Tatica_Final",
]

COLUNAS_CALENDARIO = [
    "Promax",
    "UF",
    "CLUSTER",
    "TTC Var",
]


# ============================================================
# FUNÇÕES
# ============================================================

def normalizar_numero(valor):

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
# INÍCIO
# ============================================================

print("=" * 70)
print("CONSOLIDAÇÃO DA ÁRVORE DE PREÇOS")
print("=" * 70)


# ============================================================
# VERIFICAR ARQUIVOS
# ============================================================

arquivos = {
    "De/Para": ARQUIVO_DE_PARA,
    "Tática": ARQUIVO_TATICA,
    "Calendário": ARQUIVO_CALENDARIO,
}

for nome, arquivo in arquivos.items():

    if not arquivo.exists():

        raise FileNotFoundError(
            f"\nArquivo de {nome} não encontrado:\n"
            f"{arquivo}"
        )

    print(
        f"\n{nome}: OK"
    )


# ============================================================
# LEITURA DO DE/PARA
# ============================================================

print("\n" + "=" * 70)
print("DE/PARA")
print("=" * 70)

de_para = pd.read_excel(
    ARQUIVO_DE_PARA
)

de_para.columns = (
    de_para.columns
    .astype(str)
    .str.strip()
)

de_para = de_para.rename(
    columns={
        "NomeAbreviado": "Nome Abreviado",
    }
)

faltantes = [
    coluna
    for coluna in COLUNAS_DE_PARA
    if coluna not in de_para.columns
]

if faltantes:

    raise ValueError(
        "Colunas ausentes no De/Para:\n"
        + "\n".join(
            f" - {coluna}"
            for coluna in faltantes
        )
    )


de_para = de_para[
    COLUNAS_DE_PARA
].copy()

de_para["Promax"] = pd.to_numeric(
    de_para["Promax"],
    errors="coerce"
)

de_para = de_para.dropna(
    subset=["Promax"]
).copy()

de_para["Promax"] = (
    de_para["Promax"]
    .astype(int)
)


# ============================================================
# VALIDAR DUPLICIDADE DO DE/PARA
# ============================================================

duplicados = de_para[
    de_para["Promax"].duplicated(
        keep=False
    )
]

if not duplicados.empty:

    print(
        "\nATENÇÃO: existem Promax duplicados "
        "no De/Para:"
    )

    print(
        duplicados.to_string(
            index=False
        )
    )

    raise ValueError(
        "O De/Para precisa possuir "
        "um único registro por Promax."
    )


print(
    f"\nPromax no De/Para: "
    f"{len(de_para):,}"
)


# ============================================================
# LEITURA DA TÁTICA
# ============================================================

print("\n" + "=" * 70)
print("TÁTICA")
print("=" * 70)

tatica = pd.read_csv(
    ARQUIVO_TATICA
)

tatica.columns = (
    tatica.columns
    .astype(str)
    .str.strip()
)

faltantes = [
    coluna
    for coluna in COLUNAS_TATICA
    if coluna not in tatica.columns
]

if faltantes:

    raise ValueError(
        "Colunas ausentes na Tática:\n"
        + "\n".join(
            f" - {coluna}"
            for coluna in faltantes
        )
    )


tatica = tatica[
    COLUNAS_TATICA
].copy()

tatica["_CLUSTER_REDE_JOIN"] = (
    tatica["CLUSTER REDE"]
    .astype("string")
    .str.strip()
    .str.upper()
)

tatica["Promax"] = pd.to_numeric(
    tatica["Promax"],
    errors="coerce"
)

tatica["TTC_Minimo"] = (
    tatica["TTC_Minimo"]
    .apply(normalizar_numero)
)

tatica["TTC_Tatica_Final"] = (
    tatica["TTC_Tatica_Final"]
    .apply(normalizar_numero)
)


# ============================================================
# VALIDAR TÁTICA
# ============================================================

chave_tatica = [
    "UF",
    "_CLUSTER_REDE_JOIN",
    "Promax",
]

duplicados = tatica.duplicated(
    subset=chave_tatica,
    keep=False
)

if duplicados.any():

    print(
        "\nDuplicidades encontradas na Tática:"
    )

    print(
        tatica.loc[
            duplicados
        ].sort_values(
            chave_tatica
        ).to_string(
            index=False
        )
    )

    raise ValueError(
        "\nA Tática precisa ter apenas "
        "um TTC_Tatica_Final por "
        "UF + CLUSTER REDE + Promax."
    )


print(
    f"\nLinhas Tática: "
    f"{len(tatica):,}"
)


# ============================================================
# LEITURA DO CALENDÁRIO
# ============================================================

print("\n" + "=" * 70)
print("CALENDÁRIO")
print("=" * 70)

calendario = pd.read_csv(
    ARQUIVO_CALENDARIO
)

calendario.columns = (
    calendario.columns
    .astype(str)
    .str.strip()
)

faltantes = [
    coluna
    for coluna in COLUNAS_CALENDARIO
    if coluna not in calendario.columns
]

if faltantes:

    raise ValueError(
        "Colunas ausentes no Calendário:\n"
        + "\n".join(
            f" - {coluna}"
            for coluna in faltantes
        )
    )


calendario = calendario[
    COLUNAS_CALENDARIO
].copy()


calendario["Promax"] = pd.to_numeric(
    calendario["Promax"],
    errors="coerce"
)

calendario["TTC Var"] = (
    calendario["TTC Var"]
    .apply(normalizar_numero)
)

calendario["UF"] = (
    calendario["UF"]
    .astype("string")
    .str.strip()
    .str.upper()
)

calendario["CLUSTER"] = (
    calendario["CLUSTER"]
    .astype("string")
    .str.strip()
)

calendario["_CLUSTER_REDE_JOIN"] = (
    calendario["CLUSTER"]
    .str.upper()
)

linhas_calendario_antes = len(calendario)
calendario = calendario.drop_duplicates().copy()

print(
    "Linhas duplicadas idênticas removidas do Calendário: "
    f"{linhas_calendario_antes - len(calendario):,}"
)


# ============================================================
# VALIDAR CALENDÁRIO
# ============================================================

chave_calendario = [
    "UF",
    "_CLUSTER_REDE_JOIN",
    "Promax",
]

duplicados = calendario.duplicated(
    subset=chave_calendario,
    keep=False
)

if duplicados.any():

    print(
        "\nATENÇÃO: existem duplicidades "
        "no Calendário:"
    )

    print(
        calendario.loc[
            duplicados
        ]
        .sort_values(
            chave_calendario
        )
        .to_string(
            index=False
        )
    )

    raise ValueError(
        "\nO Calendário possui mais de "
        "um registro para "
        "UF + CLUSTER + Promax."
    )


print(
    f"\nLinhas Calendário: "
    f"{len(calendario):,}"
)


# ============================================================
# FILTRAR CALENDÁRIO PELOS PROMAX DO DE/PARA
# ============================================================

promax_arvore = set(
    de_para["Promax"]
)

calendario = calendario[
    calendario["Promax"].isin(
        promax_arvore
    )
].copy()


# ============================================================
# CONSOLIDAÇÃO
# ============================================================

print("\n" + "=" * 70)
print("CONSOLIDAÇÃO")
print("=" * 70)


# ------------------------------------------------------------
# TÁTICA
# ------------------------------------------------------------

# O De/Para é a base mestre.
#
# Para cada UF da Tática, fazemos o produto da árvore
# com a UF encontrada na Tática.
#
# Isso garante que TODOS os produtos da árvore
# continuem existindo mesmo sem Calendário.

ufs_tatica = (
    tatica["UF"]
    .dropna()
    .unique()
)

if len(ufs_tatica) == 0:

    raise ValueError(
        "Nenhuma UF encontrada na Tática."
    )


# Criar uma base de produtos x UFs
base = de_para.assign(
    _key=1
)

df_ufs = pd.DataFrame(
    {
        "UF": ufs_tatica,
        "_key": 1,
    }
)

base = base.merge(
    df_ufs,
    on="_key",
    how="left"
).drop(
    columns="_key"
)


# ------------------------------------------------------------
# JOIN COM TÁTICA
# ------------------------------------------------------------

base = base.merge(
    tatica,
    on=[
        "UF",
        "Promax",
    ],
    how="left",
)


# ============================================================
# JOIN COM CALENDÁRIO
# ============================================================

# O Calendário pode possuir Varejo e Atacado.
# Relacionamos cada linha ao cluster correspondente:
#
# UF + CLUSTER REDE + Promax.

base = base.merge(
    calendario,
    on=[
        "UF",
        "Promax",
        "_CLUSTER_REDE_JOIN",
    ],
    how="left",
    suffixes=(
        "",
        "_Calendario",
    ),
)


# ============================================================
# RENOMEAR CAMPOS
# ============================================================

base = base.rename(
    columns={
        "TTC Var": "TTC_Calendario",
    }
)


# ============================================================
# ORGANIZAÇÃO FINAL
# ============================================================

COLUNAS_FINAIS = [
    "UF",
    "Promax",
    "Nome",
    "Nome Abreviado",
    "NomeImg",
    "CLUSTER REDE",
    "CLUSTER",
    "Emb. Consolid.",
    "Nome PGV",
    "TTC_Minimo",
    "TTC_Tatica_Final",
    "TTC_Calendario",
]

# Adicionar somente as colunas existentes
COLUNAS_FINAIS = [
    coluna
    for coluna in COLUNAS_FINAIS
    if coluna in base.columns
]

base = base[
    COLUNAS_FINAIS
].copy()


# ============================================================
# ORDENAR
# ============================================================

ordem = [
    "UF",
    "Promax",
]

base = base.sort_values(
    [
        coluna
        for coluna in ordem
        if coluna in base.columns
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

base.to_csv(
    ARQUIVO_SAIDA,
    index=False,
    encoding="utf-8-sig",
    decimal=",",
    na_rep="-",
)


# ============================================================
# VALIDAÇÕES FINAIS
# ============================================================

print("\n" + "=" * 70)
print("VALIDAÇÃO FINAL")
print("=" * 70)

print(
    f"\nLinhas finais: "
    f"{len(base):,}"
)

print(
    f"Promax únicos: "
    f"{base['Promax'].nunique():,}"
)

print(
    f"UFs: "
    f"{base['UF'].nunique():,}"
)


# ------------------------------------------------------------
# PROMAX DO DE/PARA AUSENTES
# ------------------------------------------------------------

promax_finais = set(
    base["Promax"].unique()
)

promax_faltantes = (
    promax_arvore
    - promax_finais
)

if promax_faltantes:

    print(
        "\nERRO: existem Promax do De/Para "
        "que não estão na base final:"
    )

    for promax in sorted(
        promax_faltantes
    ):
        print(
            f" - {promax}"
        )

    raise ValueError(
        "Todos os Promax do De/Para "
        "devem aparecer na árvore."
    )

else:

    print(
        "\nTodos os Promax do De/Para "
        "estão presentes."
    )


# ------------------------------------------------------------
# COBERTURA TÁTICA
# ------------------------------------------------------------

taticas_preenchidas = (
    base["TTC_Tatica_Final"]
    .notna()
    .sum()
)

print(
    f"\nTTC Tática preenchido: "
    f"{taticas_preenchidas:,} "
    f"de {len(base):,}"
)


# ------------------------------------------------------------
# COBERTURA CALENDÁRIO
# ------------------------------------------------------------

if "TTC_Calendario" in base.columns:

    calendario_preenchido = (
        base["TTC_Calendario"]
        .notna()
        .sum()
    )

    print(
        f"TTC Calendário preenchido: "
        f"{calendario_preenchido:,} "
        f"de {len(base):,}"
    )


# ------------------------------------------------------------
# DISPONIBILIDADE POWERPACK
# ------------------------------------------------------------

if "TTC_Minimo" in base.columns:

    pp_disponivel = (
        base["TTC_Minimo"]
        .gt(0)
        .sum()
    )

    print(
        f"PowerPack disponível (TTC_Minimo > 0): "
        f"{pp_disponivel:,} "
        f"de {len(base):,}"
    )


# ============================================================
# ARQUIVO
# ============================================================

print("\n" + "=" * 70)
print("CONSOLIDAÇÃO CONCLUÍDA")
print("=" * 70)

print(
    f"\nArquivo gerado:"
)

print(
    ARQUIVO_SAIDA
)

print(
    "\nA base consolidada está pronta."
)

print("=" * 70)