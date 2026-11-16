# =============================================================================
# ATUALIZAR_AC_RO_TATICA_ARVORE.PY
# Atualiza TTC Tática no CSV final com a moda de POLÍTICA ASR
# exclusivamente para AC e RO.
# =============================================================================

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import shutil
import unicodedata

import pandas as pd


# =============================================================================
# 1. CONFIGURAÇÕES
# =============================================================================

ROOT = Path(__file__).resolve().parents[1]

ARQUIVO_TATICA_CSV = ROOT / "data" / "processed" / "tatica_arvore.csv"
PASTA_FONTE_POLITICA = ROOT / "data" / "unprocessed"
NOME_ARQUIVO_POLITICA = "Árvore Cerveja - Setembro 26 Atualizada.xlsx"
NOME_ABA_POLITICA = "Política"

# Colunas fixas no Excel da Política: D = UF, H = SKU, Z = POLÍTICA ASR.
COLUNA_UF_EXCEL = "D"
COLUNA_SKU_EXCEL = "H"
COLUNA_PRECO_EXCEL = "Z"

# A Tática Final normalmente tem TTC Gôndola. Se houver TTC Tática,
# ela terá prioridade.
COLUNAS_PRECO_CSV = ("TTC Tática", "TTC Gôndola")


# =============================================================================
# 2. FUNÇÕES AUXILIARES
# =============================================================================

def normalizar_texto(valor: object) -> str:
    """Normaliza texto ignorando acentos, caixa e espaços extras."""
    if pd.isna(valor):
        return ""

    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(
        caractere for caractere in texto
        if not unicodedata.combining(caractere)
    )
    texto = texto.casefold().strip()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def localizar_arquivo_politica() -> Path:
    """Localiza o Excel mesmo com diferenças na codificação Unicode do nome."""
    if not PASTA_FONTE_POLITICA.exists():
        raise FileNotFoundError(
            f"Pasta da fonte não encontrada: {PASTA_FONTE_POLITICA}"
        )

    nome_esperado = normalizar_texto(Path(NOME_ARQUIVO_POLITICA).stem)
    candidatos = [
        arquivo for arquivo in PASTA_FONTE_POLITICA.iterdir()
        if arquivo.is_file()
        and arquivo.suffix.casefold() in {".xlsx", ".xlsm"}
        and normalizar_texto(arquivo.stem) == nome_esperado
    ]

    if len(candidatos) == 1:
        return candidatos[0]

    if len(candidatos) > 1:
        lista = "\n".join(str(caminho) for caminho in candidatos)
        raise RuntimeError(
            "Mais de um arquivo corresponde ao nome esperado. "
            "Deixe apenas um ou ajuste a configuração:\n" + lista
        )

    arquivos_excel = sorted(
        str(arquivo.name)
        for arquivo in PASTA_FONTE_POLITICA.iterdir()
        if arquivo.is_file()
        and arquivo.suffix.casefold() in {".xlsx", ".xlsm"}
    )
    raise FileNotFoundError(
        f"Não encontrei '{NOME_ARQUIVO_POLITICA}' em {PASTA_FONTE_POLITICA}.\n"
        "Arquivos Excel encontrados:\n- "
        + ("\n- ".join(arquivos_excel) if arquivos_excel else "nenhum")
    )


def encontrar_coluna(df: pd.DataFrame, nomes_esperados: str | tuple[str, ...]) -> str:
    """Encontra coluna(s) ignorando acentos, caixa e espaços extras."""
    if isinstance(nomes_esperados, str):
        nomes_esperados = (nomes_esperados,)

    procurados = {normalizar_texto(nome) for nome in nomes_esperados}
    for coluna in df.columns:
        if normalizar_texto(coluna) in procurados:
            return coluna

    raise ValueError(
        f"Nenhuma destas colunas foi encontrada: {nomes_esperados}. "
        f"Colunas disponíveis no CSV: {list(df.columns)}"
    )


def converter_preco(valor: object) -> float:
    """Converte preço numérico ou texto brasileiro em float."""
    if pd.isna(valor):
        return float("nan")

    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor)

    texto = str(valor).strip()
    if not texto or texto in {"-", "—", "–"}:
        return float("nan")

    texto = (
        texto.replace("R$", "")
        .replace("\xa0", "")
        .replace(" ", "")
    )

    # Formato brasileiro, por exemplo 1.234,56 -> 1234.56.
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")

    convertido = pd.to_numeric(texto, errors="coerce")
    return float(convertido) if pd.notna(convertido) else float("nan")


def normalizar_uf_coluna(df: pd.DataFrame, coluna: str) -> None:
    df[coluna] = df[coluna].astype("string").str.strip().str.upper()


def normalizar_codigo_coluna(df: pd.DataFrame, coluna: str) -> None:
    df[coluna] = pd.to_numeric(df[coluna], errors="coerce").astype("Int64")


def calcular_moda_unica(valores: pd.Series) -> tuple[float | None, int, list[float]]:
    """Retorna a moda única, sua frequência e os valores empatados, se houver."""
    serie = valores.dropna().astype(float)
    if serie.empty:
        return None, 0, []

    frequencias = serie.value_counts(sort=False)
    maior_frequencia = int(frequencias.max())
    modas = sorted(
        float(preco)
        for preco, frequencia in frequencias.items()
        if int(frequencia) == maior_frequencia
    )

    if len(modas) != 1:
        return None, maior_frequencia, modas

    return modas[0], maior_frequencia, []


# =============================================================================
# 3. CARREGAR A FONTE E CALCULAR A MODA DE POLÍTICA ASR
# =============================================================================

def carregar_moda_politica() -> dict[tuple[str, int], float]:
    """
    Lê a aba Política utilizando as letras das colunas, sem depender dos
    nomes/cabeçalhos da planilha:
      - D = UF
      - H = SKU
      - Z = POLÍTICA ASR

    Calcula a moda por UF + SKU para AC e RO. Como SKU identifica o produto,
    a moda será aplicada a todas as linhas desse produto/UF no CSV final.
    """
    arquivo = localizar_arquivo_politica()
    print(f"Fonte de preços encontrada: {arquivo}")

    excel = pd.ExcelFile(arquivo)
    abas = {normalizar_texto(nome): nome for nome in excel.sheet_names}
    chave_aba = normalizar_texto(NOME_ABA_POLITICA)
    if chave_aba not in abas:
        raise ValueError(
            f"A aba '{NOME_ABA_POLITICA}' não foi encontrada. "
            f"Abas disponíveis: {excel.sheet_names}"
        )

    # Importante: header=None e usecols por letra evitam o erro 'Unnamed: ...'
    # quando o cabeçalho da planilha está em outras linhas ou células mescladas.
    politica = pd.read_excel(
        arquivo,
        sheet_name=abas[chave_aba],
        header=None,
        usecols=f"{COLUNA_UF_EXCEL},{COLUNA_SKU_EXCEL},{COLUNA_PRECO_EXCEL}",
    )

    if politica.shape[1] != 3:
        raise ValueError(
            "Não consegui ler as três colunas esperadas da aba Política. "
            f"Colunas retornadas: {politica.shape[1]}"
        )

    politica.columns = ["UF", "SKU", "POLÍTICA ASR"]

    # Linhas de título/cabeçalho ficam de fora automaticamente porque SKU não
    # é numérico; o filtro também remove linhas sem preço.
    normalizar_uf_coluna(politica, "UF")
    normalizar_codigo_coluna(politica, "SKU")
    politica["POLÍTICA ASR"] = politica["POLÍTICA ASR"].apply(converter_preco)

    politica = politica[
        politica["UF"].isin(["AC", "RO"])
        & politica["SKU"].notna()
        & politica["POLÍTICA ASR"].notna()
    ].copy()

    if politica.empty:
        raise ValueError(
            "Não encontrei linhas com UF AC/RO, SKU numérico e POLÍTICA ASR "
            "preenchido nas colunas D, H e Z da aba Política. "
            "Confira se essas letras correspondem à aba correta."
        )

    lookup: dict[tuple[str, int], float] = {}
    ambiguidades: list[tuple[tuple[str, int], list[float], int]] = []

    for (uf, sku), grupo in politica.groupby(["UF", "SKU"], sort=False):
        chave = (str(uf).strip().upper(), int(sku))
        moda, frequencia, modas_empatadas = calcular_moda_unica(
            grupo["POLÍTICA ASR"]
        )

        if modas_empatadas:
            ambiguidades.append((chave, modas_empatadas, frequencia))
            continue

        if moda is not None:
            lookup[chave] = moda

    if ambiguidades:
        print("\nATENÇÃO — MODA EMPATADA NA ABA POLÍTICA")
        for chave, modas, frequencia in ambiguidades[:50]:
            print(
                f"  UF + SKU={chave}; preços empatados={modas}; "
                f"frequência de cada preço={frequencia}"
            )
        if len(ambiguidades) > 50:
            print(f"  ... e mais {len(ambiguidades) - 50} chaves empatadas")
        raise ValueError(
            "Há SKUs com duas ou mais modas igualmente frequentes na fonte. "
            "O CSV não foi alterado; confira os casos listados acima."
        )

    print("\nMODA DE POLÍTICA ASR CALCULADA")
    print(f"Linhas de fonte utilizáveis para AC/RO: {len(politica):,}")
    print(f"Combinações UF + SKU com preço modal: {len(lookup):,}")
    print("Colunas usadas na fonte: UF = D, SKU = H, POLÍTICA ASR = Z")

    return lookup


# =============================================================================
# 4. ATUALIZAR O CSV FINAL
# =============================================================================

def atualizar_csv() -> None:
    if not ARQUIVO_TATICA_CSV.exists():
        raise FileNotFoundError(
            f"CSV final não encontrado: {ARQUIVO_TATICA_CSV}\n"
            "Execute primeiro src/tratamento_tatica.py para gerar o CSV."
        )

    df = pd.read_csv(ARQUIVO_TATICA_CSV, encoding="utf-8-sig")

    col_uf = encontrar_coluna(df, "UF")
    col_promax = encontrar_coluna(df, "Promax")
    col_preco = encontrar_coluna(df, COLUNAS_PRECO_CSV)

    normalizar_uf_coluna(df, col_uf)
    normalizar_codigo_coluna(df, col_promax)
    df[col_preco] = df[col_preco].apply(converter_preco).astype(float)

    lookup = carregar_moda_politica()

    mascara_ro_ac = df[col_uf].isin(["AC", "RO"])
    linhas_atualizadas = 0
    linhas_sem_preco = 0
    chaves_atualizadas: set[tuple[str, int]] = set()
    chaves_sem_preco: set[tuple[str, int]] = set()
    atualizacoes_por_chave: Counter = Counter()

    for idx in df.index[mascara_ro_ac]:
        uf_valor = df.at[idx, col_uf]
        promax_valor = df.at[idx, col_promax]

        if pd.isna(promax_valor):
            linhas_sem_preco += 1
            continue

        chave = (str(uf_valor).strip().upper(), int(promax_valor))

        if chave not in lookup:
            linhas_sem_preco += 1
            chaves_sem_preco.add(chave)
            continue

        # Todas as instâncias da mesma UF + Promax recebem a moda calculada.
        df.at[idx, col_preco] = lookup[chave]
        linhas_atualizadas += 1
        chaves_atualizadas.add(chave)
        atualizacoes_por_chave[chave] += 1

    if linhas_atualizadas == 0:
        raise ValueError(
            "Nenhuma linha foi atualizada. O CSV original foi preservado. "
            "Confira se SKU corresponde a Promax e se há preços para AC/RO "
            "nas colunas D, H e Z da aba Política."
        )

    # Backup único: não sobrescreve o primeiro arquivo guardado.
    backup = ARQUIVO_TATICA_CSV.with_name("tatica_arvore_antes_politica.csv")
    if not backup.exists():
        shutil.copy2(ARQUIVO_TATICA_CSV, backup)
        print(f"Backup inicial criado: {backup}")

    temporario = ARQUIVO_TATICA_CSV.with_name("tatica_arvore.tmp.csv")
    df.to_csv(temporario, index=False, encoding="utf-8-sig")
    temporario.replace(ARQUIVO_TATICA_CSV)

    print("\n" + "=" * 76)
    print("ATUALIZAÇÃO DO TTC TÁTICA CONCLUÍDA")
    print("=" * 76)
    print(f"Arquivo atualizado: {ARQUIVO_TATICA_CSV}")
    print(f"Coluna de preço atualizada: {col_preco}")
    print(f"Linhas de AC/RO no CSV: {int(mascara_ro_ac.sum()):,}")
    print(f"Linhas atualizadas com a moda de POLÍTICA ASR: {linhas_atualizadas:,}")
    print(f"Combinações UF + Promax atualizadas: {len(chaves_atualizadas):,}")
    print(f"Linhas sem correspondência de preço modal: {linhas_sem_preco:,}")
    print("UFs diferentes de AC e RO: não alteradas.")
    print(f"Backup original: {backup}")

    if chaves_sem_preco:
        exemplos = sorted(chaves_sem_preco)
        print("\nCombinações AC/RO sem preço modal correspondente (até 30):")
        for chave in exemplos[:30]:
            print(f"  {chave}")
        if len(exemplos) > 30:
            print(f"  ... e mais {len(exemplos) - 30} combinações")

    print("\nAmostra das modas aplicadas (até 20 combinações):")
    for chave in sorted(chaves_atualizadas)[:20]:
        print(f"  {chave} -> R$ {lookup[chave]:.2f} "
              f"(linhas atualizadas: {atualizacoes_por_chave[chave]})")


if __name__ == "__main__":
    atualizar_csv()
