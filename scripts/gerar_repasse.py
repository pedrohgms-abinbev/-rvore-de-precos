from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from numbers import Number
from pathlib import Path

import pandas as pd


# ============================================================
# CONFIGURAÇÕES
# ============================================================
# Considera que este script está dentro da pasta scripts/ do projeto.
# Estrutura esperada:
#   projeto/
#     scripts/gerar_repasse.py
#     data/unprocessed/Repasse.xlsb
#     data/processed/repasse.csv
#     cadastro/de_para_repasse.xlsx
ROOT = Path(__file__).resolve().parents[1]
ARQUIVO_EXCEL = ROOT / "data" / "unprocessed" / "Repasse.xlsb"
ARQUIVO_DEPARA = ROOT / "cadastro" / "de_para_repasse.xlsx"
ARQUIVO_SAIDA = ROOT / "data" / "processed" / "repasse.csv"
# Lista de produtos cujos códigos não foram encontrados ou ficaram ambíguos no de/para.
ARQUIVO_PENDENCIAS_PROMAX = ROOT / "data" / "processed" / "repasse_promax_pendencias.csv"

ABA_EXCEL: str | int = "TÁTICA POS"
ABA_DEPARA: str | int = 0  # primeira aba de cadastro/de_para_repasse.xlsx

# Posições físicas das colunas no Excel, com índices pandas começando em zero.
# Y=25, Z=26, BP=68, BR=70, BW=75 e CC=81.
COLUNAS = {
    "ttc_gondola_novo": {"letra": "Y", "indice": 24},
    "diferenca_preco": {"letra": "Z", "indice": 25},
    "mes_repasse": {"letra": "BP", "indice": 67},
    "uf": {"letra": "BR", "indice": 69},
    "produto": {"letra": "CC", "indice": 80},
    "classificacao": {"letra": "BW", "indice": 74},
}

COLUNAS_SAIDA = [
    "uf",
    "produto",
    "codigo_promax",
    "classificacao",
    "mes_repasse",
    "ttc_gondola_novo",
    "diferenca_preco",
]


# ============================================================
# FUNÇÕES DE LIMPEZA
# ============================================================
def limpar_texto(valor):
    if pd.isna(valor):
        return pd.NA
    texto = str(valor).strip()
    if not texto or texto.lower() in {"nan", "none", "null", "nat", "<na>"}:
        return pd.NA
    return texto


def limpar_uf(valor):
    texto = limpar_texto(valor)
    if pd.isna(texto):
        return pd.NA
    return texto.upper()


def limpar_mes(valor):
    if pd.isna(valor):
        return pd.NA

    if isinstance(valor, (pd.Timestamp, datetime, date)):
        return valor.strftime("%m/%Y")

    texto = str(valor).strip()
    if not texto or texto.lower() in {"nan", "none", "null", "nat", "<na>"}:
        return pd.NA
    return texto


def limpar_numero(valor):
    """Converte números e formatos comuns como 4,99 ou R$ 1.234,56."""
    if pd.isna(valor):
        return float("nan")

    if isinstance(valor, Number) and not isinstance(valor, bool):
        return float(valor)

    texto = str(valor).strip()
    if not texto or texto.lower() in {"nan", "none", "null", "n/a", "na", "-", "--", "<na>"}:
        return float("nan")

    texto = texto.replace("R$", "").replace("\u00a0", "").replace(" ", "")

    # Trata tanto formato brasileiro (1.234,56) quanto formato americano (1,234.56).
    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        return float(texto)
    except ValueError:
        return float("nan")


def normalizar_cabecalho(valor) -> str:
    """Normaliza nomes de colunas para reconhecer variações de acentuação/pontuação."""
    texto = str(valor).strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", texto)


def normalizar_chave_produto(valor) -> str:
    """Gera uma chave para comparação exata de nomes, ignorando caixa e pontuação."""
    texto = limpar_texto(valor)
    if pd.isna(texto):
        return ""
    texto = unicodedata.normalize("NFKD", str(texto)).upper()
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]+", " ", texto).strip()


def limpar_codigo(valor):
    """Preserva códigos como texto e remove o sufixo .0 criado por leitura numérica."""
    texto = limpar_texto(valor)
    if pd.isna(texto):
        return pd.NA

    if isinstance(valor, Number) and not isinstance(valor, bool):
        numero = float(valor)
        if numero.is_integer():
            return str(int(numero))
        return str(valor).strip()

    texto = str(texto).strip()
    if re.fullmatch(r"\d+\.0+", texto):
        texto = texto.split(".", 1)[0]
    return texto


# ============================================================
# LEITURA E VALIDAÇÃO DO EXCEL DE REPASSE
# ============================================================
def carregar_excel() -> tuple[pd.DataFrame, str]:
    print("=" * 76)
    print("LEITURA DO ARQUIVO DE REPASSE")
    print("=" * 76)
    print(f"Arquivo: {ARQUIVO_EXCEL}")

    if not ARQUIVO_EXCEL.exists():
        raise FileNotFoundError(
            f"Não encontrei o arquivo: {ARQUIVO_EXCEL}\n"
            "Confira se Repasse.xlsb está em data/unprocessed."
        )

    try:
        with pd.ExcelFile(ARQUIVO_EXCEL, engine="pyxlsb") as excel:
            abas = excel.sheet_names
            print(f"Abas disponíveis: {abas}")

            if isinstance(ABA_EXCEL, int):
                if ABA_EXCEL < 0 or ABA_EXCEL >= len(abas):
                    raise ValueError(
                        f"ABA_EXCEL={ABA_EXCEL}, mas o arquivo tem {len(abas)} aba(s)."
                    )
                nome_aba = abas[ABA_EXCEL]
            else:
                if ABA_EXCEL not in abas:
                    raise ValueError(
                        f"A aba '{ABA_EXCEL}' não existe. Abas disponíveis: {abas}"
                    )
                nome_aba = ABA_EXCEL

            df = pd.read_excel(excel, sheet_name=nome_aba, header=None)
    except ImportError as exc:
        raise ImportError(
            "Para ler arquivos .xlsb, instale a dependência com: pip install pyxlsb"
        ) from exc

    print(f"Aba usada: {nome_aba}")
    print(f"Dimensão lida: {df.shape[0]:,} linhas x {df.shape[1]:,} colunas")
    return df, nome_aba


def validar_colunas(df: pd.DataFrame) -> None:
    maior_indice = max(item["indice"] for item in COLUNAS.values())
    if df.shape[1] <= maior_indice:
        raise ValueError(
            "O arquivo tem menos colunas do que o esperado para o mapeamento informado.\n"
            f"Maior coluna necessária: {COLUNAS['produto']['letra']} (índice pandas {maior_indice}).\n"
            f"Total de colunas lidas: {df.shape[1]}. Confira a aba selecionada."
        )

    print("\nColunas utilizadas e exemplos encontrados:")
    for nome, config in COLUNAS.items():
        indice = config["indice"]
        amostra = df.iloc[:, indice].dropna().head(3).tolist()
        print(
            f"  {config['letra']:>2} (posição Excel {indice + 1:>2})"
            f" -> {nome:<22} | exemplos: {amostra}"
        )


# ============================================================
# DE/PARA: BUSCAR O CÓDIGO PROMAX
# ============================================================
# O nome completo e o nome abreviado podem ser diferentes. O script procura
# correspondência exata normalizada em colunas de nome/produto/descrição do
# de/para. Não usa correspondência aproximada para evitar associar um Promax
# incorreto ao produto.
ALIASES_COLUNAS_NOME = {
    "nome",
    "produto",
    "nomeproduto",
    "nomepgv",
    "descricaoproduto",
    "descricao",
    "nomecompleto",
    "nomesku",
    "nomeabreviado",
    "nomeabrev",
    "nomereduzido",
    "nomecurto",
    "abreviado",
    "abrev",
    "abreviacao",
    "descricaoabreviada",
    "productname",
    "shortname",
}


def localizar_coluna_promax(colunas: list[object]):
    normalizadas = {coluna: normalizar_cabecalho(coluna) for coluna in colunas}
    prioridades = ["codigopromax", "codpromax", "promax", "skuid"]
    for candidato in prioridades:
        for coluna, normalizada in normalizadas.items():
            if normalizada == candidato:
                return coluna

    # Fallback conservador: só aceita uma coluna cujo título mencione Promax.
    candidatas = [
        coluna for coluna, normalizada in normalizadas.items()
        if "promax" in normalizada
    ]
    return candidatas[0] if len(candidatas) == 1 else None


def localizar_colunas_nome(colunas: list[object], coluna_promax) -> list[object]:
    resultado = []
    normalizadas = {coluna: normalizar_cabecalho(coluna) for coluna in colunas}

    for coluna, normalizada in normalizadas.items():
        if coluna == coluna_promax:
            continue
        if normalizada in ALIASES_COLUNAS_NOME:
            resultado.append(coluna)

    # Fallback para cadastros com títulos como "Descrição Comercial" ou
    # "Nome Abreviado do Produto".
    if not resultado:
        for coluna, normalizada in normalizadas.items():
            if coluna == coluna_promax:
                continue
            if any(token in normalizada for token in ("nome", "produto", "descricao", "abrev", "reduzido")):
                resultado.append(coluna)

    return resultado


def carregar_depara() -> dict[str, set[str]]:
    """Retorna mapa de nome normalizado -> conjunto de códigos Promax possíveis."""
    print("\n" + "=" * 76)
    print("LEITURA DO CADASTRO DE/PARA")
    print("=" * 76)
    print(f"Arquivo: {ARQUIVO_DEPARA}")

    if not ARQUIVO_DEPARA.exists():
        print("AVISO: cadastro/de_para_repasse.xlsx não encontrado. O CSV será gerado sem códigos Promax.")
        return {}

    try:
        depara = pd.read_excel(
            ARQUIVO_DEPARA,
            sheet_name=ABA_DEPARA,
            dtype=object,
        )
    except Exception as exc:
        print(f"AVISO: não foi possível ler o de/para ({exc}). CSV seguirá sem códigos Promax.")
        return {}

    print(f"Colunas encontradas no de/para: {list(depara.columns)}")
    coluna_promax = localizar_coluna_promax(list(depara.columns))
    if coluna_promax is None:
        print(
            "AVISO: não identifiquei uma coluna de Código Promax. "
            "Confira se existe uma coluna chamada 'Promax', 'Código Promax' ou 'SKU_ID'."
        )
        return {}

    colunas_nome = localizar_colunas_nome(list(depara.columns), coluna_promax)
    if not colunas_nome:
        print("AVISO: não identifiquei colunas com nomes/descrições de produto no de/para.")
        return {}

    print(f"Coluna Promax identificada: {coluna_promax}")
    print(f"Colunas usadas para localizar produto: {colunas_nome}")

    mapa: dict[str, set[str]] = {}
    pares_adicionados = 0

    for _, linha in depara.iterrows():
        codigo = limpar_codigo(linha.get(coluna_promax))
        if pd.isna(codigo):
            continue

        for coluna_nome in colunas_nome:
            chave = normalizar_chave_produto(linha.get(coluna_nome))
            if not chave:
                continue
            mapa.setdefault(chave, set()).add(str(codigo))
            pares_adicionados += 1

    chaves_ambiguas = sum(1 for codigos in mapa.values() if len(codigos) > 1)
    print(f"Pares nome/código carregados: {pares_adicionados:,}")
    print(f"Chaves de nome distintas: {len(mapa):,}")
    if chaves_ambiguas:
        print(
            f"AVISO: {chaves_ambiguas:,} nomes aparecem ligados a mais de um Promax. "
            "Essas correspondências não serão atribuídas automaticamente."
        )

    return mapa


def aplicar_codigo_promax(dados: pd.DataFrame, mapa: dict[str, set[str]]) -> pd.DataFrame:
    """Adiciona o Código Promax e mantém diagnóstico interno do vínculo."""
    codigos = []
    status = []
    candidatos_por_linha = []

    for produto in dados["produto"]:
        chave = normalizar_chave_produto(produto)
        opcoes = mapa.get(chave, set()) if chave else set()

        if len(opcoes) == 1:
            codigos.append(next(iter(opcoes)))
            status.append("OK")
            candidatos_por_linha.append(next(iter(opcoes)))
        elif len(opcoes) > 1:
            codigos.append(pd.NA)
            status.append("AMBIGUO")
            candidatos_por_linha.append(" | ".join(sorted(opcoes)))
        else:
            codigos.append(pd.NA)
            status.append("NAO_ENCONTRADO")
            candidatos_por_linha.append("")

    resultado = dados.copy()
    resultado["codigo_promax"] = codigos
    resultado["_status_promax"] = status
    resultado["_codigos_promax_candidatos"] = candidatos_por_linha

    com_codigo = resultado["codigo_promax"].notna().sum()
    sem_correspondencia = (resultado["_status_promax"] == "NAO_ENCONTRADO").sum()
    ambiguos = (resultado["_status_promax"] == "AMBIGUO").sum()
    print("\nResultado do vínculo com o de/para:")
    print(f"  Linhas com Código Promax localizado: {com_codigo:,} de {len(resultado):,}")
    print(f"  Linhas sem correspondência (NA): {sem_correspondencia:,}")
    print(f"  Linhas com correspondência ambígua: {ambiguos:,}")

    return resultado


# ============================================================
# TRATAMENTO DO DATASET
# ============================================================
def montar_pendencias_promax(dados: pd.DataFrame) -> pd.DataFrame:
    """Gera uma lista deduplicada de nomes que precisam de ajuste no de/para."""
    colunas_saida = [
        "produto",
        "chave_normalizada_depara",
        "situacao_depara",
        "codigos_promax_candidatos",
        "ufs",
        "classificacoes",
        "meses_repasse",
        "quantidade_repasses",
    ]

    if dados.empty:
        return pd.DataFrame(columns=colunas_saida)

    pendencias = dados.loc[dados["_status_promax"] != "OK"].copy()
    if pendencias.empty:
        return pd.DataFrame(columns=colunas_saida)

    pendencias["chave_normalizada_depara"] = pendencias["produto"].map(
        normalizar_chave_produto
    )
    pendencias["codigos_promax_candidatos"] = pendencias[
        "_codigos_promax_candidatos"
    ].fillna("")

    def valores_unicos_texto(serie: pd.Series) -> str:
        valores = {
            str(valor).strip()
            for valor in serie.dropna()
            if str(valor).strip()
        }
        return " | ".join(sorted(valores))

    pendencias = (
        pendencias.groupby(
            [
                "produto",
                "chave_normalizada_depara",
                "_status_promax",
                "codigos_promax_candidatos",
            ],
            dropna=False,
            as_index=False,
        )
        .agg(
            ufs=("uf", valores_unicos_texto),
            classificacoes=("classificacao", valores_unicos_texto),
            meses_repasse=("mes_repasse", valores_unicos_texto),
            quantidade_repasses=("produto", "size"),
        )
        .rename(columns={"_status_promax": "situacao_depara"})
    )

    pendencias = pendencias[colunas_saida].sort_values(
        by=["situacao_depara", "produto"], kind="stable"
    ).reset_index(drop=True)
    return pendencias


def preparar_repasse(
    df_origem: pd.DataFrame,
    mapa_promax: dict[str, set[str]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    dados = pd.DataFrame(
        {
            nome: df_origem.iloc[:, config["indice"]]
            for nome, config in COLUNAS.items()
        }
    )

    dados["ttc_gondola_novo"] = dados["ttc_gondola_novo"].apply(limpar_numero)
    dados["diferenca_preco"] = dados["diferenca_preco"].apply(limpar_numero)
    dados["mes_repasse"] = dados["mes_repasse"].apply(limpar_mes)
    dados["uf"] = dados["uf"].apply(limpar_uf)
    dados["produto"] = dados["produto"].apply(limpar_texto)
    dados["classificacao"] = dados["classificacao"].apply(limpar_texto)

    linhas_lidas = len(dados)

    # Z identifica o repasse: diferença preenchida e diferente de zero.
    # Inclui aumentos e reduções de preço.
    mask_repasse = (
        dados["diferenca_preco"].notna()
        & dados["diferenca_preco"].abs().gt(1e-12)
    )
    dados = dados.loc[mask_repasse].copy()
    linhas_com_diferenca = len(dados)

    # Não restringe a lista de UFs. Remove apenas registros sem UF ou produto.
    dados = dados.loc[dados["uf"].notna() & dados["produto"].notna()].copy()
    linhas_com_uf_produto = len(dados)

    dados = aplicar_codigo_promax(dados, mapa_promax)

    # Remove linhas duplicadas considerando todas as colunas que irão para
    # o repasse.csv. Mantém somente a primeira ocorrência de cada linha igual.
    # Assim, a deduplicação também considera UF, produto, Promax, classificação,
    # mês, novo TTC e diferença de preço.
    antes_deduplicacao = len(dados)
    dados = dados.drop_duplicates(
        subset=COLUNAS_SAIDA,
        keep="first",
    ).copy()
    duplicatas_removidas = antes_deduplicacao - len(dados)

    # Pendências são calculadas depois da deduplicação para não contar o mesmo
    # repasse mais de uma vez no arquivo repasse_promax_pendencias.csv.
    pendencias = montar_pendencias_promax(dados)

    dados = dados[COLUNAS_SAIDA].copy()
    dados = dados.sort_values(
        by=["uf", "mes_repasse", "produto", "classificacao"],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)

    print("\nResumo do tratamento:")
    print(f"  Linhas lidas: {linhas_lidas:,}")
    print(f"  Linhas com diferença Z diferente de zero: {linhas_com_diferenca:,}")
    print(f"  Repasses após remover UF/produto vazios: {linhas_com_uf_produto:,}")
    print(f"  Duplicatas idênticas removidas: {duplicatas_removidas:,}")
    print(f"  Registros finais: {len(dados):,}")
    print(f"  Nomes/situações pendentes no de/para: {len(pendencias):,}")

    return dados, pendencias


def salvar_csv(df: pd.DataFrame) -> None:
    ARQUIVO_SAIDA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ARQUIVO_SAIDA, index=False, encoding="utf-8-sig")
    print(f"\nCSV salvo em: {ARQUIVO_SAIDA}")


def salvar_pendencias_promax(df: pd.DataFrame) -> None:
    """Salva nomes sem código ou com vínculo ambíguo para corrigir o de/para."""
    ARQUIVO_PENDENCIAS_PROMAX.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ARQUIVO_PENDENCIAS_PROMAX, index=False, encoding="utf-8-sig")
    print(f"Lista de pendências Promax salva em: {ARQUIVO_PENDENCIAS_PROMAX}")
    print(f"  Nomes pendentes: {len(df):,}")
    if not df.empty:
        print("  Situações:")
        print(df["situacao_depara"].value_counts().to_string())


def main() -> None:
    df_origem, _ = carregar_excel()
    validar_colunas(df_origem)
    mapa_promax = carregar_depara()
    df_repasse, df_pendencias = preparar_repasse(df_origem, mapa_promax)

    print("\nQuantidade de repasses por UF:")
    if df_repasse.empty:
        print("  Nenhum repasse encontrado. Confira os exemplos das colunas acima.")
    else:
        print(df_repasse.groupby("uf", dropna=False).size().to_string())
        print("\nAmostra das primeiras 10 linhas:")
        print(df_repasse.head(10).to_string(index=False))

    salvar_csv(df_repasse)
    salvar_pendencias_promax(df_pendencias)
    print("\nTratamento de repasse concluído.")


if __name__ == "__main__":
    main()
