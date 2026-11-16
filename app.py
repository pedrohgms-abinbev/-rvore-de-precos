from __future__ import annotations

from base64 import b64encode
from collections.abc import Iterator
from contextlib import contextmanager
from html import escape
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image
from pypdf import PdfWriter
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

from scripts.workflow_atualizado import (
    INPUT_FILES,
    WorkflowStepError,
    run_workflow,
)


BASE_DIR = Path(__file__).resolve().parent
TREE_FILE = BASE_DIR / "data" / "processed" / "arvore_precos.csv"
CTR_FILE = BASE_DIR / "data" / "processed" / "ctr_arvore.csv"
MASTER_FILE = BASE_DIR / "cadastro" / "de_para.xlsx"
IMAGE_DIR = BASE_DIR / "images" / "img"
LOGO_FILE = BASE_DIR / "images" / "logo.png"
UF_OPTIONS = ["AM", "MT", "GO", "DF", "MS", "AC", "RO"]
COR_210_PROMAX = 18780

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

PRICE_ROWS = [
    ("TTC TÁTICA", "TTC", "ttc"),
    ("PP", "PP", "pp"),
    ("TTC CALENDÁRIO", "CAL", "calendar"),
    ("CTR L3M", "CTR", "ctr"),
]
PACKAGES = ["Lata 269ml", "Lata 350ml", "Long Neck", "Outros"]
EXPORT_VIEWPORT_WIDTH = 1400
EXPORT_VIEWPORT_HEIGHT = 1980
EXPORT_SCALE = 6
EXPORT_DPI = 170 * EXPORT_SCALE


st.set_page_config(
    page_title="Árvore de Preços",
    layout="wide",
    initial_sidebar_state="collapsed",
)


with st.expander("Enviar arquivos e gerar o HTML", expanded=False):
    st.caption(
        "Envie as planilhas de Tática, CTR e Calendário. "
        "O cadastro De/Para e as imagens existentes serão reutilizados."
    )
    with st.form("price_tree_workflow"):
        tatica_upload = st.file_uploader(
            f"Tática — {INPUT_FILES['tatica']}",
            type=["xlsx"],
            key="workflow_tatica",
        )
        ctr_upload = st.file_uploader(
            f"CTR — {INPUT_FILES['ctr']}",
            type=["xlsx"],
            key="workflow_ctr",
        )
        calendario_upload = st.file_uploader(
            f"Calendário — {INPUT_FILES['calendario']}",
            type=["xlsx"],
            key="workflow_calendario",
        )
        submitted = st.form_submit_button(
            "Processar arquivos e gerar HTML",
            use_container_width=True,
        )

    if submitted:
        uploaded_files = {
            "tatica": tatica_upload,
            "ctr": ctr_upload,
            "calendario": calendario_upload,
        }
        if any(file is None for file in uploaded_files.values()):
            st.error("Selecione as três planilhas antes de iniciar o processamento.")
        else:
            with st.spinner(
                "Processando planilhas, consolidando a árvore e gerando o HTML..."
            ):
                try:
                    result = run_workflow(
                        BASE_DIR,
                        {
                            key: file.getvalue()
                            for key, file in uploaded_files.items()
                            if file is not None
                        },
                    )
                except WorkflowStepError as error:
                    st.error(str(error))
                    if error.output:
                        st.code(error.output)
                except (OSError, ValueError) as error:
                    st.error(f"Não foi possível concluir o workflow: {error}")
                else:
                    st.cache_data.clear()
                    st.success(
                        "Arquivos processados, árvore consolidada e HTML gerado."
                    )
                    st.download_button(
                        "Baixar arvore_precos_premium.html",
                        data=result.html_path.read_bytes(),
                        file_name=result.html_path.name,
                        mime="text/html",
                        use_container_width=True,
                    )
                    with st.expander("Detalhes do processamento"):
                        st.code(result.logs)


def find_column(
    frame: pd.DataFrame,
    candidates: list[str],
    *,
    required: bool = True,
) -> str | None:
    columns = {
        str(column).strip().casefold(): str(column)
        for column in frame.columns
    }
    for candidate in candidates:
        if candidate.strip().casefold() in columns:
            return columns[candidate.strip().casefold()]
    if required:
        raise ValueError(
            f"Coluna ausente. Esperava uma destas: {', '.join(candidates)}"
        )
    return None


def parse_number(value: object) -> float | None:
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


def format_price(value: object) -> str:
    number = parse_number(value)
    if number is None:
        return "-"
    return f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def normalize_channel(value: object) -> str | None:
    text = str(value).strip().casefold()
    if text == "atacado":
        return "C"
    if text == "varejo":
        return "V"
    return None


@st.cache_data(show_spinner=False)
def load_master(file_path: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    source = pd.read_excel(file_path)
    promax_col = find_column(source, ["Promax"])
    name_col = find_column(source, ["Nome"], required=False)
    short_name_col = find_column(
        source, ["NomeAbreviado", "Nome Abreviado"], required=False
    )
    image_col = find_column(source, ["NomeImg"], required=False)

    master = pd.DataFrame()
    master["Promax"] = pd.to_numeric(source[promax_col], errors="coerce")
    master["Nome"] = (
        source[name_col].fillna("").astype(str).str.strip()
        if name_col
        else ""
    )
    master["NomeAbreviado"] = (
        source[short_name_col].fillna("").astype(str).str.strip()
        if short_name_col
        else ""
    )
    master["NomeImg"] = (
        source[image_col].fillna("").astype(str).str.strip()
        if image_col
        else ""
    )
    master = master.dropna(subset=["Promax"]).copy()

    duplicate_codes = master.loc[
        master["Promax"].duplicated(keep=False), "Promax"
    ].unique()
    if len(duplicate_codes):
        raise ValueError(
            "O De/Para deve ter um único cadastro por Promax. "
            f"Códigos duplicados: {', '.join(map(str, duplicate_codes))}"
        )
    if master["NomeAbreviado"].eq("").any():
        codes = master.loc[master["NomeAbreviado"].eq(""), "Promax"].tolist()
        raise ValueError(
            f"Nome abreviado ausente no De/Para para os Promax: {codes}"
        )

    master["Ordem"] = range(len(master))
    return master.reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_tree(file_path: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    source = pd.read_csv(
        file_path,
        encoding="utf-8-sig",
        dtype=str,
        keep_default_na=False,
    )
    source.columns = source.columns.astype(str).str.strip()

    uf_col = find_column(source, ["UF"])
    promax_col = find_column(source, ["Promax"])
    channel_col = find_column(source, ["CLUSTER REDE"])
    ttc_col = find_column(
        source, ["TTC_Tatica_Final", "TTC_Tatica", "TTC Tática", "TTC Gôndola"]
    )
    ttc_min_col = find_column(
        source, ["TTC_Minimo", "TTC Mínimo", "TTC mínimo ativação (un.)"]
    )
    calendar_col = find_column(
        source, ["TTC_Calendario", "TTC Calendário", "TTC Calendário"]
    )

    tree = pd.DataFrame(index=source.index)
    tree["UF"] = source[uf_col].astype(str).str.strip().str.upper()
    tree["Promax"] = pd.to_numeric(source[promax_col], errors="coerce")
    tree["CV"] = source[channel_col].map(normalize_channel)
    tree["TTC"] = source[ttc_col].map(parse_number)
    tree["TTC_MIN"] = source[ttc_min_col].map(parse_number)
    tree["PP"] = tree["TTC_MIN"].where(tree["TTC_MIN"] > 0)
    tree["CAL"] = source[calendar_col].map(parse_number)
    tree = tree.dropna(subset=["Promax"]).copy()
    tree = tree.loc[tree["Promax"].isin(PROMAX_ARVORE)].copy()

    invalid_channels = source.loc[
        tree.index[tree["CV"].isna()], channel_col
    ].drop_duplicates().tolist()
    if invalid_channels:
        raise ValueError(
            "Valores inesperados em 'CLUSTER REDE': "
            + ", ".join(map(str, invalid_channels))
        )

    duplicate_keys = tree.duplicated(
        subset=["UF", "Promax", "CV"], keep=False
    )
    if duplicate_keys.any():
        examples = tree.loc[
            duplicate_keys, ["UF", "Promax", "CV"]
        ].drop_duplicates().head(10)
        raise ValueError(
            "A árvore deve ter no máximo um registro por UF, Promax e canal. "
            f"Duplicidades: {examples.to_dict('records')}"
        )
    return tree.reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_ctr(file_path: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    source = pd.read_csv(
        file_path,
        encoding="utf-8-sig",
        dtype=str,
        keep_default_na=False,
    )
    source.columns = source.columns.astype(str).str.strip()

    uf_col = find_column(source, ["UF"])
    promax_col = find_column(source, ["Promax"])
    ctr_col = find_column(source, ["CTR L3M"])

    ctr = pd.DataFrame()
    ctr["UF"] = source[uf_col].astype(str).str.strip().str.upper()
    ctr["Promax"] = pd.to_numeric(source[promax_col], errors="coerce")
    ctr["CTR"] = source[ctr_col].map(parse_number)
    ctr = ctr.dropna(subset=["Promax"]).copy()
    ctr = ctr.loc[ctr["Promax"].isin(PROMAX_ARVORE)].copy()

    duplicate_keys = ctr.duplicated(subset=["UF", "Promax"], keep=False)
    if duplicate_keys.any():
        examples = ctr.loc[
            duplicate_keys, ["UF", "Promax"]
        ].drop_duplicates().head(10)
        raise ValueError(
            "O CTR deve ter no máximo um registro por UF e Promax. "
            f"Duplicidades: {examples.to_dict('records')}"
        )
    return ctr.reset_index(drop=True)


@st.cache_data(show_spinner=False, max_entries=100)
def image_data_uri(
    file_path: str,
    modified_ns: int,
    *,
    preserve_resolution: bool = False,
) -> str:
    del modified_ns
    with Image.open(file_path) as source:
        image = source.convert("RGBA")
    if not preserve_resolution:
        image.thumbnail((100, 110), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    if preserve_resolution:
        image.save(buffer, format="PNG", optimize=True)
        mime_type = "image/png"
    else:
        image.save(buffer, format="WEBP", quality=90, method=6)
        mime_type = "image/webp"
    return f"data:{mime_type};base64," + b64encode(buffer.getvalue()).decode("ascii")


def classify_package(promax: object, short_name: str) -> str:
    if pd.notna(promax) and int(promax) == COR_210_PROMAX:
        return "Long Neck"
    label = short_name.strip().upper()
    if label.endswith("LN") or " LN" in label:
        return "Long Neck"
    if "350" in label:
        return "Lata 350ml"
    if "269" in label:
        return "Lata 269ml"
    return "Outros"


def price_for_channel(
    prices: pd.DataFrame | None, field: str, channel: str
) -> float | None:
    if prices is None or prices.empty:
        return None
    if field not in prices.columns:
        return None
    if field == "CTR":
        values = prices[field].dropna()
    else:
        values = prices.loc[prices["CV"] == channel, field].dropna()
    if values.empty:
        return None
    value = float(values.iloc[0])
    if field == "PP" and value <= 0:
        return None
    return value


def price_text(prices: pd.DataFrame | None, field: str) -> str:
    if field == "CTR":
        value = price_for_channel(prices, field, "C")
        if value is None:
            return "-"
        return f"{value:.1%}".replace(".", ",")

    c_price = price_for_channel(prices, field, "C")
    v_price = price_for_channel(prices, field, "V")
    if c_price is None and v_price is None:
        return "-"
    if c_price is None:
        return f"{format_price(v_price)} V"
    if v_price is None:
        return f"{format_price(c_price)} C"
    c_display = format_price(c_price)
    v_display = format_price(v_price)
    if c_display == v_display:
        return c_display
    return f"{format_price(v_price)} V / {format_price(c_price)} C"


def price_elevations(references: pd.Series) -> pd.Series:
    prices = references.dropna()
    if prices.empty:
        return pd.Series(0.0, index=references.index)
    low = float(prices.min())
    price_range = float(prices.max()) - low
    if price_range < 0.000001:
        return pd.Series(0.0, index=references.index)
    return (70.0 * (references - low) / price_range).fillna(0.0)


CSS = """
<style>
* { box-sizing: border-box; }
body { margin: 0; color: #20242a; font-family: Arial, Helvetica, sans-serif; }
.tree-header { display: flex; align-items: center; gap: 10px; margin: 0 0 9px; }
.tree-header .brand-logo { width: 140px; height: auto; margin-left: auto; object-fit: contain; }
.uf { min-width: 48px; height: 30px; display: flex; align-items: center; justify-content: center; background: #0758d8; color: white; font-size: 16px; font-weight: 800; }
.tree-title { color: #0758d8; font-size: 23px; font-weight: 900; }
.package { position: relative; margin: 0 0 11px; padding: 9px 8px 9px 14px; background: linear-gradient(115deg, #f8f9fb 0%, #f1f3f6 100%); border: 1px solid #dce1e8; border-radius: 9px; box-shadow: 0 3px 9px #1b2d4610; }
.package:before { content: ""; position: absolute; left: 3px; top: 6px; bottom: 6px; width: 5px; border-radius: 6px; background: #123f91; }
.package-title { min-height: 18px; margin: 0 0 5px 4px; color: #26364b; display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 11px; font-weight: 800; letter-spacing: .045em; text-transform: uppercase; }
.matrix { position: relative; display: grid; align-items: end; column-gap: 0; row-gap: 1px; }
.row-label { min-width: 0; display: flex; align-items: center; justify-content: center; }
.label-pill { width: 100%; max-width: 68px; padding: 3px 1px; border-radius: 9px; color: white; text-align: center; font-size: 7px; font-weight: 800; }
.product-slot { position: relative; z-index: 1; min-width: 0; height: 168px; }
.product { position: absolute; right: 0; bottom: 0; left: 0; height: 110px; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; }
.product-name { width: 100%; height: 17px; overflow: hidden; color: #24292f; font-size: 9px; font-weight: 800; text-align: center; text-overflow: ellipsis; white-space: nowrap; }
.product-image { width: 100%; height: 86px; display: flex; align-items: flex-end; justify-content: center; }
.product-image img { display: block; max-width: 84px; max-height: 86px; object-fit: contain; filter: drop-shadow(0 1px 1px #18233320); }
.orange-rule { width: 70%; max-width: 44px; height: 2px; margin-top: 3px; background: linear-gradient(90deg, #f0a366, #df6e27); border-radius: 2px; }
.price-cell { min-width: 0; height: 23px; padding: 0 1.5px; display: flex; align-items: center; justify-content: center; }
.price-pill { width: 100%; min-height: 18px; overflow: hidden; padding: 3px 1px; border: 1px solid #0000000d; border-radius: 9px; color: #202020; font-size: 8px; font-weight: 800; line-height: 1; text-align: center; white-space: nowrap; }
.ttc { background: #f0d6e3; }
.pp { background: #d6eccd; }
.calendar { background: #f7d8c4; }
.ctr { background: #dce5f8; }
.row-label .ttc { background: #cb83a2; }
.row-label .pp { background: #64a957; }
.row-label .calendar { background: #d7794b; }
.row-label .ctr { background: #7190d0; }
.empty-image { width: 23px; height: 33px; border: 1px dashed #c9cdd3; border-radius: 3px; background: #fafafa; }
.search-results { overflow-x: auto; margin: 0 0 12px; padding: 12px; background: #f8f9fb; border: 1px solid #dce1e8; border-radius: 9px; }
.search-results h2 { margin: 0 0 10px; color: #0758d8; font-size: 17px; }
.search-results .search-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.search-results .brand-logo { width: 140px; height: auto; object-fit: contain; }
.search-table { width: 100%; min-width: 760px; border-collapse: collapse; table-layout: fixed; background: white; }
.search-table th { padding: 8px 6px; background: #123f91; color: white; font-size: 11px; text-align: center; }
.search-table td { padding: 5px; border-bottom: 1px solid #e3e7ed; color: #24292f; font-size: 11px; font-weight: 700; text-align: center; }
.search-table tbody tr:nth-child(even) { background: #f5f7fa; }
.search-table .search-product { display: flex; align-items: center; gap: 8px; text-align: left; vertical-align: middle; }
.search-table .search-product img { width: 36px; height: 52px; object-fit: contain; }
.search-table .search-uf { width: 52px; color: #0758d8; font-size: 13px; }
@media (max-width: 700px) { .tree-title { font-size: 19px; } .package { overflow-x: auto; } .matrix { min-width: 720px; } }
</style>
"""


def render_package(
    title: str,
    products: pd.DataFrame,
    prices_by_sku: dict[float, pd.DataFrame],
    *,
    preserve_image_resolution: bool = False,
) -> str:
    if products.empty:
        return ""

    count = len(products)
    content = [
        f'<section class="package"><div class="package-title">'
        f'<span>{escape(title)}</span>'
        "</div>",
        '<div class="matrix" style="grid-template-columns: 66px '
        f'repeat({count}, minmax(0, 1fr));">',
        '<div class="row-label"></div>',
    ]

    for product in products.itertuples():
        name = escape(product.NomeAbreviado, quote=True)
        image_name = str(product.NomeImg).strip()
        if not image_name:
            raise ValueError(
                f"NomeImg ausente no De/Para para o produto {product.NomeAbreviado}."
            )
        image_path = IMAGE_DIR / image_name
        if not image_path.is_file():
            raise FileNotFoundError(
                f"A imagem '{image_name}' do De/Para não foi encontrada em {IMAGE_DIR}."
            )
        stat = image_path.stat()
        image_uri = image_data_uri(
            str(image_path),
            stat.st_mtime_ns,
            preserve_resolution=preserve_image_resolution,
        )
        lift = product.Elevacao
        content.append(
            '<div class="product-slot">'
            f'<div class="product" style="bottom:{lift:.1f}px">'
            f'<div class="product-name" title="{name}">{name}</div>'
            f'<div class="product-image"><img src="{image_uri}" alt="{name}"></div>'
            '<div class="orange-rule"></div></div></div>'
        )

    for label, field, color in PRICE_ROWS:
        content.append(
            f'<div class="row-label"><span class="label-pill {color}">'
            f'{escape(label)}</span></div>'
        )
        for product in products.itertuples():
            prices = prices_by_sku.get(product.Promax)
            value = escape(price_text(prices, field))
            content.append(
                f'<div class="price-cell"><span class="price-pill {color}" '
                f'title="{escape(value, quote=True)}">{value}</span></div>'
            )

    content.append("</div></section>")
    return "".join(content)


@contextmanager
def export_browser_page(
    *,
    device_scale_factor: int = EXPORT_SCALE,
) -> Iterator[Page]:
    """Abre uma sessão isolada do Chromium para cada exportação."""
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(
                args=["--disable-dev-shm-usage"],
            )
        except PlaywrightError as error:
            raise RuntimeError(
                "Não foi possível iniciar o Chromium para exportar. "
                "Instale o navegador e os requisitos do sistema com "
                "`python -m playwright install --with-deps chromium`."
            ) from error

        try:
            context = browser.new_context(
                viewport={
                    "width": EXPORT_VIEWPORT_WIDTH,
                    "height": EXPORT_VIEWPORT_HEIGHT,
                },
                device_scale_factor=device_scale_factor,
                color_scheme="light",
            )
            try:
                page = context.new_page()
                yield page
            finally:
                context.close()
        finally:
            browser.close()


def prepare_tree_page(
    uf: str,
    master: pd.DataFrame,
    tree: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[float, pd.DataFrame]]:
    uf_prices = tree.loc[tree["UF"] == uf].copy()
    prices_by_sku = {
        promax: rows.reset_index(drop=True)
        for promax, rows in uf_prices.groupby("Promax", sort=False)
    }
    products = master.copy()
    products["Embalagem"] = products.apply(
        lambda row: classify_package(row["Promax"], row["NomeAbreviado"]),
        axis=1,
    )
    ttc_references = uf_prices.groupby("Promax", sort=False)["TTC"].mean()
    products["TTC_Referencia"] = products["Promax"].map(ttc_references)
    package_order = {package: index for index, package in enumerate(PACKAGES)}
    products["OrdemEmbalagem"] = products["Embalagem"].map(package_order)
    products = products.sort_values(
        ["OrdemEmbalagem", "TTC_Referencia", "Ordem"],
        na_position="last",
        kind="stable",
    ).reset_index(drop=True)
    products["Elevacao"] = products.groupby(
        "Embalagem", sort=False
    )["TTC_Referencia"].transform(price_elevations)
    return products, prices_by_sku


def wait_for_page_assets(page: Page) -> None:
    """Espera as fontes e imagens incorporadas terminarem de carregar."""
    page.evaluate("() => document.fonts.ready.then(() => true)")
    page.evaluate(
        """() => Promise.all(
            Array.from(document.images, image => {
                if (image.complete) {
                    return image.decode().catch(() => {});
                }
                return new Promise(resolve => {
                    image.addEventListener("load", resolve, {once: true});
                    image.addEventListener("error", resolve, {once: true});
                });
            })
        )"""
    )


def capture_export_page(
    page: Page,
    uf: str,
    master: pd.DataFrame,
    tree: pd.DataFrame,
) -> bytes:
    products, prices_by_sku = prepare_tree_page(uf, master, tree)
    page.set_content(
        build_page(
            uf,
            products,
            prices_by_sku,
            preserve_image_resolution=True,
        ),
        wait_until="domcontentloaded",
        timeout=60000,
    )
    wait_for_page_assets(page)
    return page.locator("main").screenshot(
        type="png",
        animations="disabled",
        scale="device",
        timeout=60000,
    )


def build_export_image(
    master: pd.DataFrame,
    tree: pd.DataFrame,
    uf: str,
) -> bytes:
    with export_browser_page(device_scale_factor=EXPORT_SCALE) as page:
        screenshot = capture_export_page(page, uf, master, tree)
    image_output = BytesIO()
    with Image.open(BytesIO(screenshot)) as image:
        image.save(
            image_output,
            format="PNG",
            optimize=True,
            dpi=(EXPORT_DPI, EXPORT_DPI),
        )
    return image_output.getvalue()


def build_export_pdf(
    master: pd.DataFrame,
    tree: pd.DataFrame,
    *,
    ufs: tuple[str, ...] = tuple(UF_OPTIONS),
) -> bytes:
    """Gera o PDF com uma sessão do Chromium por UF e imagens otimizadas."""
    writer = PdfWriter()
    page_pdfs: list[BytesIO] = []

    try:
        for uf in ufs:
            products, prices_by_sku = prepare_tree_page(uf, master, tree)
            # Para PDF, miniaturas são suficientes e reduzem muito o HTML/memória.
            # O PNG individual continua usando imagens em alta resolução.
            html = build_page(
                uf,
                products,
                prices_by_sku,
                preserve_image_resolution=False,
            )

            # Cada UF usa um navegador novo em escala 1 para limitar memória.
            with export_browser_page(device_scale_factor=1) as page:
                page.emulate_media(media="screen")
                page.set_content(
                    html,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                wait_for_page_assets(page)
                dimensions = page.locator("main").evaluate(
                    """element => {
                        const {width, height} = element.getBoundingClientRect();
                        return {
                            width: Math.ceil(width),
                            height: Math.ceil(height)
                        };
                    }"""
                )
                pdf_bytes = page.pdf(
                    width=f'{dimensions["width"]}px',
                    height=f'{dimensions["height"]}px',
                    print_background=True,
                    margin={
                        "top": "0",
                        "right": "0",
                        "bottom": "0",
                        "left": "0",
                    },
                    prefer_css_page_size=False,
                    scale=1,
                )

            page_pdf = BytesIO(pdf_bytes)
            page_pdfs.append(page_pdf)
            writer.append(page_pdf)

        output = BytesIO()
        writer.add_metadata({"/Title": "Árvore de Preços — todas as UFs"})
        writer.write(output)
        return output.getvalue()
    finally:
        writer.close()
        for page_pdf in page_pdfs:
            page_pdf.close()


def split_search_terms(search: str) -> list[str]:
    return [
        term.strip().casefold()
        for term in search.replace(";", ",").split(",")
        if term.strip()
    ]


def build_search_results(products: pd.DataFrame, tree: pd.DataFrame) -> str:
    rows_by_key = {
        key: rows.reset_index(drop=True)
        for key, rows in tree.groupby(["Promax", "UF"], sort=False)
    }
    logo_uri = image_data_uri(
        str(LOGO_FILE),
        LOGO_FILE.stat().st_mtime_ns,
        preserve_resolution=False,
    )
    content = [
        CSS,
        '<section class="search-results"><header class="search-header">'
        '<h2>Resultados em todas as UFs</h2>'
        f'<img class="brand-logo" src="{logo_uri}" alt="Logo">'
        "</header>",
        '<table class="search-table"><thead><tr>',
        "<th>Produto</th><th>UF</th><th>TTC Tática</th>",
        "<th>PP</th><th>TTC Calendário</th><th>CTR L3M</th>",
        "</tr></thead><tbody>",
    ]

    for product in products.itertuples():
        image_name = str(product.NomeImg).strip()
        if not image_name:
            raise ValueError(
                f"NomeImg ausente no De/Para para o produto {product.NomeAbreviado}."
            )
        image_path = IMAGE_DIR / image_name
        if not image_path.is_file():
            raise FileNotFoundError(
                f"A imagem '{image_name}' do De/Para não foi encontrada em {IMAGE_DIR}."
            )
        image_uri = image_data_uri(
            str(image_path), image_path.stat().st_mtime_ns
        )
        name = escape(product.NomeAbreviado, quote=True)
        content.append(
            f'<tr><td rowspan="{len(UF_OPTIONS)}">'
            '<div class="search-product">'
            f'<img src="{image_uri}" alt="{name}">'
            f'<span>{name}<br><small>Promax {int(product.Promax)}</small></span>'
            "</div></td>"
        )
        for index, uf in enumerate(UF_OPTIONS):
            prices = rows_by_key.get((product.Promax, uf))
            if index:
                content.append("<tr>")
            content.append(f'<td class="search-uf">{escape(uf)}</td>')
            for field in ("TTC", "PP", "CAL", "CTR"):
                value = price_text(prices, field)
                content.append(f"<td>{escape(value)}</td>")
            content.append("</tr>")

    content.append("</tbody></table></section>")
    return "".join(content)


def build_page(
    uf: str,
    products: pd.DataFrame,
    prices_by_sku: dict[float, pd.DataFrame],
    *,
    preserve_image_resolution: bool = False,
) -> str:
    sections = [
        render_package(
            title,
            products.loc[products["Embalagem"] == title],
            prices_by_sku,
            preserve_image_resolution=preserve_image_resolution,
        )
        for title in PACKAGES
    ]
    logo_uri = image_data_uri(
        str(LOGO_FILE),
        LOGO_FILE.stat().st_mtime_ns,
        preserve_resolution=preserve_image_resolution,
    )
    return (
        CSS
        + '<main><header class="tree-header">'
        + f'<div class="uf">{escape(uf)}</div>'
        + '<div class="tree-title">ÁRVORE DE PREÇOS</div>'
        + f'<img class="brand-logo" src="{logo_uri}" alt="Logo">'
        + "</header>"
        + "".join(sections)
        + "</main>"
    )


st.markdown(
    """
    <style>
    .block-container {max-width: 100%; padding: 1.6rem .6rem .6rem;}
    [data-testid="stHorizontalBlock"] {gap: .5rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

control_uf, control_search, control_refresh = st.columns([1, 2, 1])
with control_uf:
    uf = st.selectbox("UF", UF_OPTIONS, key="filter_uf")
with control_search:
    search = st.text_input(
        "Produto",
        placeholder="Nome, nome abreviado ou Promax (separe por vírgula ou ;)",
        key="filter_product",
    )
with control_refresh:
    st.write("")
    if st.button("Atualizar", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

try:
    if not TREE_FILE.is_file():
        raise FileNotFoundError(f"Árvore consolidada não encontrada: {TREE_FILE}")
    if not CTR_FILE.is_file():
        raise FileNotFoundError(
            f"CTR processado não encontrado: {CTR_FILE}. "
            "Execute `python src/tratamento_ctr.py` para gerá-lo."
        )
    if not MASTER_FILE.is_file():
        raise FileNotFoundError(f"De/Para não encontrado: {MASTER_FILE}")

    master_stat = MASTER_FILE.stat()
    tree_stat = TREE_FILE.stat()
    ctr_stat = CTR_FILE.stat()
    master = load_master(str(MASTER_FILE), master_stat.st_mtime_ns)
    tree = load_tree(str(TREE_FILE), tree_stat.st_mtime_ns)
    ctr = load_ctr(str(CTR_FILE), ctr_stat.st_mtime_ns)
    tree = tree.merge(
        ctr[["UF", "Promax", "CTR"]],
        on=["UF", "Promax"],
        how="left",
        validate="many_to_one",
    )
    export_stamp = (
        master_stat.st_mtime_ns,
        tree_stat.st_mtime_ns,
        ctr_stat.st_mtime_ns,
        uf,
        EXPORT_SCALE,
        EXPORT_DPI,
    )

    unknown_skus = set(tree["Promax"]) - set(master["Promax"])
    if unknown_skus:
        raise ValueError(
            "Há códigos Promax na árvore sem cadastro no De/Para: "
            + ", ".join(map(str, sorted(unknown_skus)))
        )
    catalog = master.copy()
    catalog["Embalagem"] = catalog.apply(
        lambda row: classify_package(row["Promax"], row["NomeAbreviado"]),
        axis=1,
    )
    package_order = {package: index for index, package in enumerate(PACKAGES)}
    catalog["OrdemEmbalagem"] = catalog["Embalagem"].map(package_order)
    pdf_stamp = (
        master_stat.st_mtime_ns,
        tree_stat.st_mtime_ns,
        ctr_stat.st_mtime_ns,
        EXPORT_VIEWPORT_WIDTH,
    )
    if st.button(
        "Gerar PDF em alta resolução — todas as UFs",
        use_container_width=True,
        disabled=bool(search.strip()),
    ):
        with st.spinner("Gerando PDF para todas as UFs..."):
            st.session_state["price_tree_all_ufs_pdf"] = (
                pdf_stamp,
                build_export_pdf(master, tree),
            )
    pdf_export = st.session_state.get("price_tree_all_ufs_pdf")
    if pdf_export and pdf_export[0] == pdf_stamp and not search.strip():
        st.download_button(
            "Baixar PDF — todas as UFs",
            data=pdf_export[1],
            file_name="arvore_precos_todas_ufs.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    if search.strip():
        st.caption("Limpe a busca para exportar o PDF completo das UFs.")

    if st.button(
        f"Gerar PNG de {uf}",
        use_container_width=True,
        disabled=bool(search.strip()),
    ):
        with st.spinner(f"Gerando PNG de {uf} em alta resolução..."):
            st.session_state["price_tree_png"] = (
                export_stamp,
                build_export_image(master, tree, uf),
            )
    png_export = st.session_state.get("price_tree_png")
    if png_export and png_export[0] == export_stamp and not search.strip():
        st.download_button(
            f"Baixar árvore — {uf} (PNG alta resolução)",
            data=png_export[1],
            file_name=f"arvore_precos_{uf}.png",
            mime="image/png",
            use_container_width=True,
        )
    if search.strip():
        st.caption("Limpe a busca para exportar a árvore da UF selecionada.")

    if search.strip():
        terms = split_search_terms(search)
        products = catalog.copy()
        if not terms:
            st.info("Informe ao menos um termo de busca válido.")
        else:
            masks = []
            for term in terms:
                masks.append(
                    products["Nome"].str.casefold().str.contains(term, na=False)
                    | products["NomeAbreviado"].str.casefold().str.contains(
                        term, na=False
                    )
                    | products["Promax"]
                    .astype("Int64")
                    .astype(str)
                    .str.contains(term, na=False)
                )
            matches = pd.concat(masks, axis=1).any(axis=1)
            products = products.loc[matches].copy()
            if products.empty:
                st.info("Nenhum produto encontrado para essa pesquisa.")
            else:
                st.html(build_search_results(products, tree), width="stretch")
    else:
        products, prices_by_sku = prepare_tree_page(uf, master, tree)
        st.html(build_page(uf, products, prices_by_sku), width="stretch")
except (
    OSError,
    pd.errors.ParserError,
    ValueError,
    KeyError,
    RuntimeError,
    PlaywrightError,
) as error:
    st.error(f"Não foi possível montar a árvore de preços: {error}")
