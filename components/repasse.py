from __future__ import annotations

from base64 import b64encode
from html import escape
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image

PACKAGES = ["Lata 269ml", "Lata 350ml", "Long Neck", "Outros"]


def _parse_number(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace("R$", "").replace(" ", "")
    if text.casefold() in {"", "-", "—", "–", "nan", "none", "null"}:
        return None

    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return None


def _format_price(value: object) -> str:
    number = _parse_number(value)
    if number is None:
        return "-"
    return f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _format_delta(value: object) -> str:
    number = _parse_number(value)
    if number is None:
        return "-"
    sign = "+" if number > 0 else ""
    return f"{sign}{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _classify_package(promax: object, short_name: str) -> str:
    if pd.notna(promax) and str(promax).strip() == "18780":
        return "Long Neck"

    label = str(short_name or "").strip().upper()
    if label.endswith("LN") or " LN" in label:
        return "Long Neck"
    if "350" in label:
        return "Lata 350ml"
    if "269" in label:
        return "Lata 269ml"
    return "Outros"


@st.cache_data(show_spinner=False)
def load_repasse_csv(file_path: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns

    source = pd.read_csv(
        file_path,
        encoding="utf-8-sig",
        dtype=str,
        keep_default_na=False,
    )
    source.columns = source.columns.astype(str).str.strip()

    required = {
        "uf",
        "produto",
        "codigo_promax",
        "classificacao",
        "mes_repasse",
        "ttc_gondola_novo",
        "diferenca_preco",
    }
    missing = required - set(source.columns)
    if missing:
        raise ValueError(
            "O repasse.csv não possui as colunas esperadas: "
            + ", ".join(sorted(missing))
        )

    df = source.copy()
    df["uf"] = df["uf"].astype(str).str.strip().str.upper()
    df["produto"] = df["produto"].astype(str).str.strip()
    df["classificacao"] = (
        df["classificacao"].astype(str).str.strip().str.casefold()
        .map({"varejo": "Varejo", "atacado": "Atacado"})
        .fillna(df["classificacao"].astype(str).str.strip())
    )
    df["mes_repasse"] = df["mes_repasse"].astype(str).str.strip()
    df["codigo_promax"] = pd.to_numeric(df["codigo_promax"], errors="coerce")
    df["ttc_gondola_novo"] = df["ttc_gondola_novo"].map(_parse_number)
    df["diferenca_preco"] = df["diferenca_preco"].map(_parse_number)

    # Segurança: mesmo que o pipeline já filtre, a aba não exibe diferença zero.
    df = df.loc[
        df["uf"].ne("")
        & df["produto"].ne("")
        & df["diferenca_preco"].notna()
        & df["diferenca_preco"].ne(0)
    ].copy()

    # Remove somente linhas totalmente idênticas.
    df = df.drop_duplicates().reset_index(drop=True)
    return df


def _normalize_image_name(value: object) -> str:
    import re
    import unicodedata
    text = str(value or "").strip().upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]+", "", text)


def _resolve_image(image_dir: Path, image_name: object) -> Path | None:
    name = str(image_name or "").strip()
    if not name:
        return None
    exact = image_dir / name
    if exact.is_file():
        return exact
    target = _normalize_image_name(name)
    if not target or not image_dir.is_dir():
        return None
    matches = [
        path for path in image_dir.iterdir()
        if path.is_file() and _normalize_image_name(path.name) == target
    ]
    return sorted(matches, key=lambda path: path.name.casefold())[0] if matches else None


def _image_data_uri(file_path: Path) -> str | None:
    if not file_path.is_file():
        return None
    try:
        with Image.open(file_path) as source:
            image = source.convert("RGBA")
            image.thumbnail((100, 110), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            image.save(buffer, format="WEBP", quality=90, method=6)
        return "data:image/webp;base64," + b64encode(buffer.getvalue()).decode("ascii")
    except (OSError, ValueError):
        return None


def _prepare_repasse(repasse: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    data = repasse.copy()

    # O De/Para do Repasse pode ter o mesmo Promax em mais de uma linha
    # (ex.: 36028 aparece com nomes diferentes). Por isso, não fazemos
    # merge apenas por Promax. Primeiro tentamos casar Promax + Nome do
    # produto; depois usamos uma referência única por Promax como fallback.
    lookup = master[["Promax", "Nome", "NomeAbreviado", "NomeImg"]].copy()
    lookup["Promax"] = pd.to_numeric(lookup["Promax"], errors="coerce")
    lookup["Nome"] = lookup["Nome"].fillna("").astype(str).str.strip()
    lookup["NomeAbreviado"] = lookup["NomeAbreviado"].fillna("").astype(str).str.strip()
    lookup["NomeImg"] = lookup["NomeImg"].fillna("").astype(str).str.strip()

    data["codigo_promax"] = pd.to_numeric(data["codigo_promax"], errors="coerce")
    data["_produto_match"] = data["produto"].fillna("").astype(str).str.strip()

    # 1) Match exato pelo Promax + nome completo. Isso preserva os dois
    # cadastros quando o mesmo Promax possui nomes diferentes.
    lookup_by_name = lookup.drop_duplicates(
        subset=["Promax", "Nome"], keep="first"
    )
    data = data.merge(
        lookup_by_name,
        left_on=["codigo_promax", "_produto_match"],
        right_on=["Promax", "Nome"],
        how="left",
        suffixes=("", "_cadastro"),
        validate="many_to_one",
    )

    # 2) Para casos em que o nome do CSV não bate exatamente, usamos apenas
    # Promax, mas somente em cadastros que possuem uma única referência.
    fallback = (
        lookup.drop_duplicates(subset=["Promax"], keep=False)
        [["Promax", "NomeAbreviado", "NomeImg"]]
        .rename(columns={
            "NomeAbreviado": "NomeAbreviado_fallback",
            "NomeImg": "NomeImg_fallback",
        })
    )
    data = data.merge(
        fallback,
        left_on="codigo_promax",
        right_on="Promax",
        how="left",
        suffixes=("", "_fallback"),
        validate="many_to_one",
    )

    data["NomeAbreviado"] = data["NomeAbreviado"].where(
        data["NomeAbreviado"].fillna("").ne(""),
        data["NomeAbreviado_fallback"],
    )
    data["NomeImg"] = data["NomeImg"].where(
        data["NomeImg"].fillna("").ne(""),
        data["NomeImg_fallback"],
    )
    data["produto_exibicao"] = data["NomeAbreviado"].where(
        data["NomeAbreviado"].fillna("").ne(""),
        data["produto"],
    )
    data["Embalagem"] = data.apply(
        lambda row: _classify_package(row["codigo_promax"], row["produto_exibicao"]),
        axis=1,
    )
    return data.drop(
        columns=["_produto_match", "Promax", "Nome", "NomeAbreviado_fallback", "NomeImg_fallback"],
        errors="ignore",
    )


def _resolve_image(image_dir: Path, filename: object) -> Path | None:
    name = str(filename or "").strip()
    if not name or not image_dir.is_dir():
        return None
    exact = image_dir / name
    if exact.is_file():
        return exact
    target = "".join(ch for ch in name.upper() if ch.isalnum())
    if not target:
        return None
    for path in image_dir.iterdir():
        if path.is_file() and "".join(ch for ch in path.stem.upper() if ch.isalnum()) == target:
            return path
    return None


def _image_for_product(image_dir: Path, image_name: object, short_name: str, product: str) -> str | None:
    for candidate in (image_name, short_name, product):
        path = _resolve_image(image_dir, candidate)
        if path is not None:
            return _image_data_uri(path)
    return None


def _display_value(rows: pd.DataFrame, promax: object, classification: str, field: str) -> tuple[str, str]:
    subset = rows.loc[(rows["codigo_promax"] == promax) & (rows["classificacao"] == classification)].copy()
    if subset.empty:
        return "-", ""
    values = subset[field].dropna().tolist()
    unique_values = list(dict.fromkeys(values))
    if len(unique_values) == 1:
        value = _format_price(unique_values[0]) if field == "ttc_gondola_novo" else _format_delta(unique_values[0])
    else:
        value = "Vários"
    details = []
    for _, row in subset.iterrows():
        uf = str(row.get("uf", "-")).strip() or "-"
        raw = row.get(field)
        formatted = _format_price(raw) if field == "ttc_gondola_novo" else _format_delta(raw)
        details.append(f"{uf}: {formatted}")
    return value, " • ".join(dict.fromkeys(details))


def build_repasse_page(
    repasse: pd.DataFrame,
    master: pd.DataFrame,
    image_dir: Path,
    logo_file: Path,
    uf: str | None = None,
) -> str:
    data = _prepare_repasse(repasse, master)
    if uf:
        uf = str(uf).strip().upper()
        # AC e RO pertencem à visão MT. Não criamos abas separadas para elas.
        source_ufs = {"MT", "AC", "RO"} if uf == "MT" else {uf}
        data = data.loc[data["uf"].isin(source_ufs)].copy()
    if data.empty:
        return '<section class="repasse-empty"><h2>Nenhum repasse encontrado</h2></section>'

    data = data.sort_values(["Embalagem", "produto_exibicao", "classificacao", "mes_repasse", "uf"], kind="stable").copy()
    products = (data[["codigo_promax", "produto_exibicao", "NomeImg", "Embalagem"]]
                .drop_duplicates(subset=["codigo_promax", "produto_exibicao"], keep="first").copy())
    package_order = {name: i for i, name in enumerate(PACKAGES)}
    products["_ordem"] = products["Embalagem"].map(package_order).fillna(99)
    products = products.sort_values(["_ordem", "produto_exibicao"], kind="stable")
    logo_uri = _image_data_uri(logo_file)

    css = '''
    <style>
    .repasse-header{display:flex;align-items:center;gap:10px;margin:0 0 10px}.repasse-title{color:var(--blue);font-size:1.45rem;font-weight:900}.repasse-subtitle{margin-left:auto;color:var(--muted);font-size:.7rem;font-weight:800}
    .repasse-summary{display:flex;flex-wrap:wrap;gap:.65rem;margin:0 0 1rem}.repasse-kpi{min-width:110px;padding:.75rem 1rem;border:1px solid var(--line);border-radius:1rem;background:var(--surface);box-shadow:var(--shadow)}.repasse-kpi-label{color:var(--muted);font-size:.62rem;font-weight:800;text-transform:uppercase}.repasse-kpi-value{margin-top:.2rem;color:var(--blue);font-size:1.15rem;font-weight:900}
    .repasse-package{position:relative;margin:0 0 1rem;padding:1rem 1rem 1.05rem 1.1rem;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);box-shadow:var(--shadow);overflow-x:auto}.repasse-package:before{content:"";position:absolute;left:0;top:1rem;bottom:1rem;width:4px;border-radius:4px;background:var(--blue-strong)}.repasse-package-title{margin:0 0 .7rem .25rem;color:var(--text);font-size:.78rem;font-weight:900;letter-spacing:.06em;text-transform:uppercase}.repasse-grid{display:grid;min-width:900px;align-items:stretch}
    .repasse-label{display:flex;align-items:center;justify-content:center;padding:.2rem}.repasse-label span{width:100%;max-width:90px;padding:.35rem .2rem;border-radius:.65rem;color:#fff;text-align:center;font-size:.57rem;font-weight:900}.repasse-product{height:150px;padding:.15rem .2rem;display:flex;flex-direction:column;align-items:center;justify-content:end}.repasse-name{width:100%;height:2.1rem;overflow:hidden;text-align:center;color:var(--text);font-size:.62rem;font-weight:800;line-height:1.15}.repasse-img{height:90px;width:100%;display:flex;align-items:end;justify-content:center}.repasse-img img{max-width:78px;max-height:88px;object-fit:contain;filter:drop-shadow(0 1px 1px rgba(0,0,0,.12))}.repasse-no-img{width:38px;height:58px;border:1px dashed var(--line);border-radius:4px}.repasse-rule{width:55%;max-width:42px;height:2px;margin-top:.2rem;background:var(--orange);border-radius:2px}
    .repasse-cell{display:flex;align-items:center;justify-content:center;padding:.18rem}.repasse-pill{width:100%;padding:.35rem .2rem;border-radius:.65rem;text-align:center;font-size:.62rem;font-weight:900;white-space:nowrap;overflow:hidden}.repasse-v{background:var(--pink)}.repasse-a{background:var(--green)}.repasse-d{background:var(--orange)}.repasse-m{background:var(--surface-soft);color:var(--blue)}.repasse-uf-pill{background:var(--surface-soft);color:var(--blue);border:1px solid var(--line)}.repasse-label-v span{background:var(--pink)}.repasse-label-a span{background:var(--green)}.repasse-label-d span{background:var(--orange)}.repasse-label-m span{background:var(--blue-strong)}.repasse-label-uf span{background:var(--blue)}.repasse-empty{padding:2rem;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface-soft);text-align:center}@media(max-width:700px){.repasse-grid{min-width:900px}.repasse-subtitle{display:none}}
    </style>
    '''
    title_uf = escape(uf) if uf else "TODAS"
    html=css+f'<main><header class="repasse-header"><div class="repasse-title">REPASSES • {title_uf}</div><div class="repasse-subtitle">TTC GÔNDOLA • NOVO PREÇO</div>'
    if logo_uri: html += f'<img src="{logo_uri}" alt="Logo" style="width:140px;height:auto;object-fit:contain;margin-left:8px;">'
    html+='</header>'
    html += f'''<div class="repasse-summary"><div class="repasse-kpi"><div class="repasse-kpi-label">Repasses</div><div class="repasse-kpi-value">{len(data)}</div></div><div class="repasse-kpi"><div class="repasse-kpi-label">Produtos</div><div class="repasse-kpi-value">{data["codigo_promax"].nunique(dropna=True)}</div></div><div class="repasse-kpi"><div class="repasse-kpi-label">Varejo</div><div class="repasse-kpi-value">{int(data["classificacao"].eq("Varejo").sum())}</div></div><div class="repasse-kpi"><div class="repasse-kpi-label">Atacado</div><div class="repasse-kpi-value">{int(data["classificacao"].eq("Atacado").sum())}</div></div></div>'''
    for package in PACKAGES:
        ps=products.loc[products["Embalagem"]==package].copy()
        if ps.empty: continue
        columns=f'76px repeat({len(ps)}, minmax(88px, 1fr))'
        block=['<section class="repasse-package">',f'<div class="repasse-package-title">{escape(package)}</div>',f'<div class="repasse-grid" style="grid-template-columns:{columns};">','<div class="repasse-label"></div>']
        for product in ps.itertuples(index=False):
            name=escape(str(product.produto_exibicao),quote=True)
            image_uri=_image_for_product(image_dir,product.NomeImg,str(product.produto_exibicao),str(product.produto_exibicao))
            image_html=f'<img src="{image_uri}" alt="{name}">' if image_uri else '<div class="repasse-no-img"></div>'
            block.append(f'<div class="repasse-product"><div class="repasse-name" title="{name}">{name}</div><div class="repasse-img">{image_html}</div><div class="repasse-rule"></div></div>')
        block.append('<div class="repasse-label repasse-label-uf"><span>UF</span></div>')
        for product in ps.itertuples(index=False):
            if uf:
                uf_text = uf
            else:
                ufs=sorted(set(data.loc[data["codigo_promax"]==product.codigo_promax,"uf"].dropna().astype(str)))
                uf_text = ", ".join(ufs) if ufs else "-"
            block.append(f'<div class="repasse-cell"><span class="repasse-pill repasse-uf-pill">{escape(uf_text)}</span></div>')
        rows_def=[("Varejo — TTC","Varejo","ttc_gondola_novo","repasse-v","repasse-label-v"),("Atacado — TTC","Atacado","ttc_gondola_novo","repasse-a","repasse-label-a"),("Varejo — Δ","Varejo","diferenca_preco","repasse-d","repasse-label-d"),("Atacado — Δ","Atacado","diferenca_preco","repasse-d","repasse-label-d")]
        for label,classification,field,cell_class,label_class in rows_def:
            block.append(f'<div class="repasse-label {label_class}"><span>{escape(label)}</span></div>')
            for product in ps.itertuples(index=False):
                value,title=_display_value(data,product.codigo_promax,classification,field)
                block.append(f'<div class="repasse-cell"><span class="repasse-pill {cell_class}" title="{escape(title,quote=True)}">{escape(value)}</span></div>')
        block.append('<div class="repasse-label repasse-label-m"><span>MÊS</span></div>')
        for product in ps.itertuples(index=False):
            months=data.loc[data["codigo_promax"]==product.codigo_promax,"mes_repasse"].dropna().astype(str).drop_duplicates().tolist()
            block.append(f'<div class="repasse-cell"><span class="repasse-pill repasse-m">{escape(" / ".join(months) or "-")}</span></div>')
        block.append('</div></section>')
        html+=''.join(block)
    return html+'</main>'


def render_repasse(repasse_file: Path, repasse_master_file: Path, image_dir: Path, logo_file: Path, uf: str | None = None) -> None:
    if not repasse_file.is_file():
        raise FileNotFoundError(f"Repasse processado não encontrado: {repasse_file}. Execute o workflow para gerar o repasse.csv.")
    if not repasse_master_file.is_file():
        raise FileNotFoundError(f"De/Para do Repasse não encontrado: {repasse_master_file}.")
    repasse_stat = repasse_file.stat()
    repasse = load_repasse_csv(str(repasse_file), repasse_stat.st_mtime_ns)
    master = pd.read_excel(str(repasse_master_file))
    master.columns = master.columns.astype(str).str.strip()
    required = {"Promax", "Nome", "NomeAbreviado", "NomeImg"}
    missing = required - set(master.columns)
    if missing:
        raise ValueError("O de_para_repasse.xlsx não possui as colunas: " + ", ".join(sorted(missing)))
    master["Promax"] = pd.to_numeric(master["Promax"], errors="coerce")
    for col in ["Nome", "NomeAbreviado", "NomeImg"]:
        master[col] = master[col].fillna("").astype(str).str.strip()
    st.html(build_repasse_page(repasse, master, image_dir, logo_file, uf=uf), width="stretch")
