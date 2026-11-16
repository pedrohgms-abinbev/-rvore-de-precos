import pandas as pd


def verificar_codigos_promax_com_ttc(arvores_precos):
    """Confere se os 31 códigos Promax têm ao menos um preço TTC preenchido."""

    def localizar_coluna(opcoes, obrigatoria=True):
        colunas = {
            str(coluna).strip().casefold(): coluna
            for coluna in arvores_precos.columns
        }
        for opcao in opcoes:
            coluna = colunas.get(opcao.casefold())
            if coluna is not None:
                return coluna

        if obrigatoria:
            raise KeyError(
                f"Nenhuma destas colunas foi encontrada: {opcoes}"
            )
        return None

    coluna_codigo = localizar_coluna(
        ["Promax", "codigo_promax", "Código Promax", "Codigo Promax", "cod_promax"]
    )
    colunas_ttc = [
        coluna
        for coluna in (
            localizar_coluna(
                [
                    "TTC",
                    "Preço TTC",
                    "Preco TTC",
                    "preco_ttc",
                    "preço_ttc",
                    "TTC_Tatica_Final",
                    "TTC Tática",
                    "TTC_Tatica",
                    "TTC_Calendario",
                    "TTC Calendário",
                ],
                obrigatoria=False,
            ),
            localizar_coluna(
                ["TTC_Tatica_Final", "TTC Tática", "TTC_Tatica"],
                obrigatoria=False,
            ),
            localizar_coluna(
                ["TTC_Calendario", "TTC Calendário"],
                obrigatoria=False,
            ),
        )
        if coluna is not None
    ]
    colunas_ttc = list(dict.fromkeys(colunas_ttc))
    if not colunas_ttc:
        raise KeyError(
            "Não foi encontrada nenhuma coluna de preço TTC "
            "(por exemplo, 'TTC_Tatica_Final' ou 'TTC_Calendario')."
        )

    dados = arvores_precos[[coluna_codigo, *colunas_ttc]].copy()
    dados[coluna_codigo] = (
        dados[coluna_codigo]
        .astype("string")
        .str.strip()
        .replace("", pd.NA)
    )
    dados = dados.dropna(subset=[coluna_codigo])

    preco_preenchido = pd.Series(False, index=dados.index)
    for coluna in colunas_ttc:
        valores = (
            dados[coluna]
            .astype("string")
            .str.strip()
            .str.replace("R$", "", regex=False)
            .str.replace(" ", "", regex=False)
            .replace({"": pd.NA, "-": pd.NA, "—": pd.NA})
        )
        tem_virgula = valores.str.contains(",", na=False)
        tem_ponto = valores.str.contains(".", regex=False, na=False)
        separadores = tem_virgula & tem_ponto
        valores.loc[separadores] = (
            valores.loc[separadores]
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False)
        )
        valores.loc[tem_virgula & ~tem_ponto] = valores.loc[
            tem_virgula & ~tem_ponto
        ].str.replace(",", ".", regex=False)
        preco_preenchido |= pd.to_numeric(valores, errors="coerce").notna()

    dados["_tem_ttc"] = preco_preenchido
    tem_ttc = dados.groupby(coluna_codigo)["_tem_ttc"].any()
    codigos_sem_ttc = tem_ttc.index[~tem_ttc].tolist()
    resultado = {
        "todos_validos": len(tem_ttc) == 31 and not codigos_sem_ttc,
        "total_codigos": len(tem_ttc),
        "codigos_sem_ttc": codigos_sem_ttc,
    }

    if resultado["todos_validos"]:
        print("OK: os 31 códigos Promax possuem ao menos um preço TTC.")
    else:
        print(
            f"Verificação falhou: {len(tem_ttc)} códigos encontrados; "
            f"sem preço TTC: {codigos_sem_ttc}."
        )
    return resultado
