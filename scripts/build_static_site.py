from __future__ import annotations
import ast, re
from base64 import b64encode
from io import BytesIO
from pathlib import Path
from html import escape
import pandas as pd
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'app_repasse.py'
OUT=ROOT/'site-premium'/'arvore_precos_premium.html'
REPASSE=ROOT/'data'/'processed'/'repasse.csv'
REPASSE_MASTER=ROOT/'cadastro'/'de_para_repasse.xlsx'
TATICA_SOURCE=ROOT/'data'/'unprocessed'/'10. Tatica Cerveja.xlsx'
REPASSE_UFS=['AM','MT','GO','DF','MS']
MS_SPECIAL_PROMAX=(1898, 18860)
MS_SPECIAL_DELTA=0.10
ECOMMERCE_NETWORKS={'AMAZON','LOJAS AMERICANAS','MAGAZINE LUIZA S/A','SHOPPER'}

def load_app_renderer():
    source=APP.read_text(encoding='utf-8'); tree=ast.parse(source)
    nodes=[]
    for n in tree.body:
        if isinstance(n,(ast.Import,ast.ImportFrom)):
            t=ast.get_source_segment(source,n) or ''
            if 'streamlit' in t or 'scripts.workflow_atualizado' in t or 'components.repasse' in t: continue
            nodes.append(n)
        elif isinstance(n,(ast.Assign,ast.AnnAssign,ast.FunctionDef)):
            # O app.py também contém código de execução do Streamlit no nível
            # superior. O gerador precisa somente das funções/constantes de
            # renderização; nunca deve executar st.columns, st.tabs etc.
            if isinstance(n, ast.FunctionDef):
                n.decorator_list = []
                nodes.append(n)
                continue
            segment = ast.get_source_segment(source, n) or ""
            if "st." in segment or "streamlit" in segment.casefold():
                continue
            nodes.append(n)
    ns={'__file__':str(APP),'__name__':'__static__'}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(APP),'exec'),ns)
    return ns

ns=load_app_renderer()

# As imagens eram reduzidas a 100x110 px no renderizador original. Usamos um
# thumbnail maior em WebP para que cresçam visualmente sem ficarem pixeladas,
# evitando o peso de embutir os originais completos no HTML.
def image_data_uri_large(file_path: str, modified_ns: int, *, preserve_resolution: bool = False) -> str:
    del modified_ns
    with Image.open(file_path) as source:
        image = source.convert("RGBA")
    if preserve_resolution:
        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        mime_type = "image/png"
    else:
        image.thumbnail((220, 230), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        image.save(buffer, format="WEBP", quality=88, method=2)
        mime_type = "image/webp"
    return f"data:{mime_type};base64," + b64encode(buffer.getvalue()).decode("ascii")

ns['image_data_uri'] = image_data_uri_large

MAX_PRODUCTS_PER_ROW = 5

def render_package_wrapped(title, products, prices_by_sku, *, preserve_image_resolution=False):
    if products.empty:
        return ''
    content = [
        f'<section class="package"><div class="package-title">'
        f'<span>{escape(title)}</span></div>'
    ]
    for start in range(0, len(products), MAX_PRODUCTS_PER_ROW):
        chunk = products.iloc[start:start + MAX_PRODUCTS_PER_ROW]
        columns = f'minmax(108px,0.72fr) repeat({len(chunk)},minmax(0,1fr))'
        content.append(f'<div class="matrix" style="grid-template-columns:{columns};"><div class="row-label"></div>')
        for product in chunk.itertuples():
            name = escape(product.NomeAbreviado, quote=True)
            image_name = str(product.NomeImg).strip()
            if not image_name:
                raise ValueError(f'NomeImg ausente no De/Para para o produto {product.NomeAbreviado}.')
            image_path = IMAGE_DIR / image_name
            if not image_path.is_file():
                raise FileNotFoundError(f"A imagem '{image_name}' do De/Para não foi encontrada em {IMAGE_DIR}.")
            image_uri = ns['image_data_uri'](
                str(image_path), image_path.stat().st_mtime_ns,
                preserve_resolution=preserve_image_resolution,
            )
            lift = float(product.Elevacao) if pd.notna(product.Elevacao) else 0.0
            content.append(
                '<div class="product-slot">'
                f'<div class="product" style="bottom:{lift:.1f}px">'
                f'<div class="product-name" title="{name}">{name}</div>'
                f'<div class="product-image"><img src="{image_uri}" alt="{name}"></div>'
                '<div class="orange-rule"></div></div></div>'
            )
        for label, field, color in ns['PRICE_ROWS']:
            content.append(
                f'<div class="row-label"><span class="label-pill {color}">{escape(label)}</span></div>'
            )
            for product in chunk.itertuples():
                prices = prices_by_sku.get(product.Promax)
                value = escape(ns['price_text'](prices, field))
                content.append(
                    f'<div class="price-cell"><span class="price-pill {color}" '
                    f'title="{escape(value, quote=True)}">{value}</span></div>'
                )
        content.append('</div>')
    content.append('</section>')
    return ''.join(content)

# build_page references render_package in this same namespace, so this override also applies to its panels.
ns['render_package'] = render_package_wrapped

BASE_DIR=ns['BASE_DIR']; TREE_FILE=ns['TREE_FILE']; CTR_FILE=ns['CTR_FILE']; MASTER_FILE=ns['MASTER_FILE']; IMAGE_DIR=ns['IMAGE_DIR']; LOGO_FILE=ns['LOGO_FILE']; PACKAGES=ns['PACKAGES']; CSS=ns['CSS']

REPASSE_CSS='''<style>
*{box-sizing:border-box}
html,body{margin:0;max-width:100%;overflow-x:hidden;font-family:Arial,Helvetica,sans-serif;color:#20242a}
.site-shell{width:100%;max-width:1800px;margin:0 auto;padding:14px;font-size:16px;overflow-x:hidden}
.site-shell .site-tabs,.site-shell .subtabs{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 13px}
.site-shell .site-tabs{border-bottom:1px solid #dce1e8;padding-bottom:11px}
.site-shell .tab-btn{border:1px solid #dce1e8;background:#f5f7fa;color:#26364b;border-radius:10px;padding:11px 20px;font-size:15px;line-height:1.2;font-weight:800;cursor:pointer}
.site-shell .tab-btn.active{background:#0758d8;color:#fff;border-color:#0758d8}
.site-panel,.uf-panel{display:none;min-width:0;max-width:100%}
.site-panel.active,.uf-panel.active{display:block}
.site-shell .tree-header,.site-shell .repasse-header{display:flex;align-items:center;gap:13px;margin:0 0 14px;min-width:0}
.site-shell .tree-header .uf,.site-shell .repasse-header .uf{min-width:60px;height:40px;padding:0 8px;display:flex;align-items:center;justify-content:center;background:#0758d8;color:#fff;font-size:21px;font-weight:800;white-space:nowrap}
.site-shell .tree-title,.site-shell .repasse-title{color:#0758d8;font-size:27px;line-height:1.15;font-weight:900}
.site-shell .tree-header .brand-logo,.site-shell .repasse-header .brand-logo{width:150px;max-width:22%;height:auto;margin-left:auto;object-fit:contain}

/* Árvore: quebra a embalagem em grupos de até cinco produtos, com todos os valores alinhados */
.site-shell .package{position:relative;width:100%;max-width:100%;overflow:hidden;padding:14px 12px 15px 17px;margin:0 0 17px;background:linear-gradient(115deg,#f8f9fb,#f1f3f6);border:1px solid #dce1e8;border-radius:10px;box-shadow:0 3px 9px #1b2d4610}
.site-shell .package:before{content:"";position:absolute;left:3px;top:6px;bottom:6px;width:5px;border-radius:6px;background:#123f91}
.site-shell .package-title{font-size:19px!important;line-height:1.25;min-height:27px;margin:0 0 9px 4px;color:#26364b;font-weight:800;letter-spacing:.035em}
.site-shell .matrix{position:relative;display:grid;width:100%;max-width:100%;min-width:0;align-items:end;column-gap:3px;row-gap:5px}
.site-shell .matrix+.matrix{padding-top:12px;margin-top:12px;border-top:1px solid #d6dce5}
.site-shell .row-label{min-width:0;display:flex;align-items:center;justify-content:center}
.site-shell .label-pill{width:100%;max-width:none;padding:7px 4px;border-radius:9px;color:#fff;text-align:center;font-size:12px!important;line-height:1.15;font-weight:800;white-space:normal;overflow-wrap:anywhere}
.site-shell .product-slot{position:relative;z-index:1;min-width:0;height:248px}
.site-shell .product{position:absolute;right:0;bottom:0;left:0;height:202px;display:flex;flex-direction:column;align-items:center;justify-content:flex-end}
.site-shell .product-name{width:100%;height:40px;overflow:hidden;color:#24292f;font-size:14px!important;line-height:1.15;font-weight:800;text-align:center;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow-wrap:anywhere;white-space:normal}
.site-shell .product-image{width:100%;height:142px;display:flex;align-items:flex-end;justify-content:center}
.site-shell .product-image img{display:block;max-width:138px!important;max-height:138px!important;object-fit:contain;filter:drop-shadow(0 1px 1px #18233320)}
.site-shell .orange-rule{width:70%;max-width:58px;height:3px;margin-top:5px;background:linear-gradient(90deg,#f0a366,#df6e27);border-radius:3px}
.site-shell .price-cell{min-width:0;height:57px;padding:2px;display:flex;align-items:stretch;justify-content:center}
.site-shell .price-pill{display:flex;align-items:center;justify-content:center;width:100%;min-width:0;min-height:48px;overflow-wrap:normal;white-space:normal;word-break:normal;padding:5px 4px;border:1px solid #0000000d;border-radius:10px;color:#202020;font-size:19px!important;line-height:1.12;font-weight:900;text-align:center}
.site-shell .ttc{background:#f0d6e3}.site-shell .pp{background:#d6eccd}.site-shell .calendar{background:#f7d8c4}.site-shell .ctr{background:#dce5f8}
.site-shell .row-label .ttc{background:#cb83a2}.site-shell .row-label .pp{background:#64a957}.site-shell .row-label .calendar{background:#d7794b}.site-shell .row-label .ctr{background:#7190d0}

/* Repasse: a mesma quebra em grupos mantém os números grandes sem exigir rolagem horizontal */
.site-shell .repasse-package{position:relative;width:100%;max-width:100%;overflow:hidden;padding:14px 12px 15px 17px;margin:0 0 17px;background:linear-gradient(115deg,#f8f9fb,#f1f3f6);border:1px solid #dce1e8;border-radius:10px;box-shadow:0 3px 9px #1b2d4610}
.site-shell .repasse-package:before{content:"";position:absolute;left:3px;top:6px;bottom:6px;width:5px;border-radius:6px;background:#123f91}
.site-shell .repasse-package-title{font-size:19px;line-height:1.25;min-height:27px;margin:0 0 9px 4px;color:#26364b;font-weight:800;letter-spacing:.035em;text-transform:uppercase}
.site-shell .repasse-grid{display:grid;align-items:center;width:100%;max-width:100%;min-width:0;column-gap:3px;row-gap:5px}
.site-shell .repasse-grid+.repasse-grid{padding-top:12px;margin-top:12px;border-top:1px solid #d6dce5}
.site-shell .repasse-spacer{visibility:hidden}
.site-shell .repasse-label,.site-shell .repasse-cell{height:58px;min-width:0;padding:2px;display:flex;align-items:stretch;justify-content:center}
.site-shell .repasse-label span,.site-shell .repasse-pill{display:flex;align-items:center;justify-content:center;width:100%;max-width:none;min-width:0;min-height:48px;padding:5px 4px;border-radius:10px;text-align:center;font-size:18px;line-height:1.12;font-weight:900;white-space:normal;overflow-wrap:normal;word-break:normal}
.site-shell .repasse-label span{color:#fff;font-size:12px;line-height:1.15;overflow-wrap:anywhere}
.site-shell .repasse-label-v span{background:#cb83a2}.site-shell .repasse-label-a span{background:#64a957}.site-shell .repasse-label-d span{background:#d7794b}
.site-shell .repasse-v{background:#f0d6e3}.site-shell .repasse-a{background:#d6eccd}.site-shell .repasse-d{background:#f7d8c4}
.site-shell .repasse-down{background:#198754!important;color:#fff!important;border:1px solid #146c43;box-shadow:0 0 0 1px #19875440}
.site-shell .repasse-product{height:218px;min-width:0;display:flex;flex-direction:column;align-items:center;justify-content:flex-end}
.site-shell .repasse-name{width:100%;height:40px;overflow:hidden;font-size:14px;line-height:1.15;font-weight:800;text-align:center;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow-wrap:anywhere;white-space:normal}
.site-shell .repasse-img{width:100%;height:140px;display:flex;align-items:flex-end;justify-content:center}
.site-shell .repasse-img img{max-width:138px;max-height:136px;object-fit:contain}
.site-shell .repasse-no-img{width:36px;height:51px;border:1px dashed #c9cdd3;border-radius:4px;background:#fafafa}
.site-shell .repasse-rule{width:70%;max-width:58px;height:3px;margin-top:5px;background:linear-gradient(90deg,#f0a366,#df6e27);border-radius:3px}
.site-shell .repasse-pill{font-size:19px}
.site-shell .repasse-down{color:#fff!important}

@media(max-width:1050px){
  .site-shell{padding:9px}
  .site-shell .tree-title,.site-shell .repasse-title{font-size:23px}
  .site-shell .product-name,.site-shell .repasse-name{font-size:12px!important}
  .site-shell .product-image img,.site-shell .repasse-img img{max-width:108px!important;max-height:112px!important}
  .site-shell .price-pill,.site-shell .repasse-pill{font-size:16px!important}
  .site-shell .product-slot{height:220px}
  .site-shell .product{height:178px}
  .site-shell .product-image{height:120px}
  .site-shell .repasse-product{height:195px}
  .site-shell .repasse-img{height:125px}
}
@media(max-width:700px){
  .site-shell{padding:6px}
  .site-shell .tree-header,.site-shell .repasse-header{gap:7px}
  .site-shell .tree-header .uf,.site-shell .repasse-header .uf{min-width:42px;height:34px;font-size:16px}
  .site-shell .tree-title,.site-shell .repasse-title{font-size:18px}
  .site-shell .tree-header .brand-logo,.site-shell .repasse-header .brand-logo{width:82px}
  .site-shell .package,.site-shell .repasse-package{padding:10px 7px 11px 11px}
  .site-shell .package-title,.site-shell .repasse-package-title{font-size:16px!important}
  .site-shell .matrix,.site-shell .repasse-grid{column-gap:1px}
  .site-shell .label-pill,.site-shell .repasse-label span{font-size:10px!important;padding:3px 1px}
  .site-shell .price-pill,.site-shell .repasse-pill{font-size:13px!important;padding:3px 1px;line-height:1.05}
  .site-shell .price-cell,.site-shell .repasse-cell,.site-shell .repasse-label{height:46px;padding:1px}
  .site-shell .price-pill,.site-shell .repasse-pill{min-height:40px}
  .site-shell .product-name,.site-shell .repasse-name{font-size:10px!important}
  .site-shell .product-image img,.site-shell .repasse-img img{max-width:72px!important;max-height:88px!important}
  .site-shell .product-slot{height:185px}
  .site-shell .product{height:150px}
  .site-shell .product-name,.site-shell .repasse-name{height:30px}
  .site-shell .product-image{height:100px}
  .site-shell .repasse-product{height:165px}
  .site-shell .repasse-img{height:105px}
}
.site-shell .repasse-product-regionais .repasse-name{height:54px;display:flex;flex-direction:column;justify-content:center;gap:3px}
.site-shell .repasse-scope{display:block;color:#0758d8;font-size:11px;line-height:1.1;font-weight:900;white-space:nowrap}
.site-shell .repasse-special-package{margin-top:18px;border:2px solid #0758d8;background:linear-gradient(115deg,#f7faff,#eef4ff)}
.site-shell .repasse-special-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:0 0 10px 4px}
.site-shell .repasse-special-title{color:#0758d8;font-size:20px;font-weight:900}
.site-shell .repasse-special-badge{padding:6px 12px;border-radius:8px;background:#0758d8;color:#fff;font-size:12px;font-weight:900;letter-spacing:.06em}
.site-shell .repasse-special-note{margin:0 0 10px 4px;color:#586579;font-size:12px;font-weight:700}
.site-shell .repasse-special-package .repasse-product{height:218px}
@media(max-width:700px){.site-shell .repasse-special-title{font-size:16px}.site-shell .repasse-special-badge{font-size:10px}}
</style>'''

def rep_master():
    s=pd.read_excel(REPASSE_MASTER,dtype=object); pc=ns['find_column'](s,['Promax']); sc=ns['find_column'](s,['NomeAbreviado','Nome Abreviado'],required=False); nc=ns['find_column'](s,['Nome'],required=False); ic=ns['find_column'](s,['NomeImg'],required=False)
    m=pd.DataFrame({'Promax':pd.to_numeric(s[pc],errors='coerce'),'NomeAbreviado':s[sc].fillna('').astype(str).str.strip() if sc else '','Nome':s[nc].fillna('').astype(str).str.strip() if nc else '','NomeImg':s[ic].fillna('').astype(str).str.strip() if ic else ''})
    return m.dropna(subset=['Promax']).drop_duplicates('Promax',keep='first').reset_index(drop=True)

def rep_data():
    d=pd.read_csv(REPASSE,encoding='utf-8-sig',dtype=str,keep_default_na=False)
    d['codigo_promax']=pd.to_numeric(d['codigo_promax'],errors='coerce'); d['ttc_gondola_novo']=pd.to_numeric(d['ttc_gondola_novo'],errors='coerce'); d['diferenca_preco']=pd.to_numeric(d['diferenca_preco'],errors='coerce'); d['uf']=d['uf'].str.strip().str.upper(); d['classificacao']=d['classificacao'].str.strip().str.title(); d['aba_uf']=d['uf'].replace({'AC':'MT','RO':'MT'})
    return d.dropna(subset=['codigo_promax']).drop_duplicates().reset_index(drop=True)

def img(row):
    vals=[row.get('NomeImg',''),row.get('NomeAbreviado',''),row.get('Nome','')]
    for v in vals:
        if not str(v).strip(): continue
        stem=Path(str(v).strip()).stem; compact=re.sub(r'[^a-z0-9]','',stem.casefold())
        candidates=[str(v).strip(),stem+'.png',stem+'.webp',stem+'.jpg',stem+'.jpeg']
        if IMAGE_DIR.exists():
            candidates += [p.name for p in IMAGE_DIR.iterdir() if p.is_file() and re.sub(r'[^a-z0-9]','',p.stem.casefold())==compact]
        for c in dict.fromkeys(candidates):
            p=IMAGE_DIR/c
            if p.is_file(): return p
    return None

def money(x): return '-' if pd.isna(x) else f'{float(x):,.2f}'.replace(',','X').replace('.',',').replace('X','.')
def delta(x): return '-' if pd.isna(x) else f'{float(x):+,.2f}'.replace(',','X').replace('.',',').replace('X','.')

def calcular_moda_tatica_unica(valores: pd.Series) -> tuple[float | None, int, list[float]]:
    """Calcula a moda do TTC em centavos, mantendo empate real como erro.

    Os preços do HTML são apresentados com duas casas decimais. Por isso,
    diferenças abaixo de um centavo (por exemplo, 2.990 e 2.991) são
    normalizadas para o mesmo preço antes da contagem da frequência.
    """
    serie = pd.to_numeric(valores, errors="coerce").dropna().astype(float).round(2)
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


def load_ms_special_tatica_prices():
    """Carrega a moda do TTC Tática por MS + Promax + canal para os SKUs nacionais.

    A Tática possui uma linha por Rede. Para cada produto/canal, normaliza-se
    o TTC para duas casas decimais e calcula-se a moda entre as redes, pois o
    preço final é exibido em centavos. Se ainda houver empate entre preços
    distintos em centavos, a geração falha sem escolher arbitrariamente.
    """
    if not TATICA_SOURCE.is_file():
        raise FileNotFoundError(
            f"Planilha original da Tática não encontrada: {TATICA_SOURCE}"
        )

    source = pd.read_excel(
        TATICA_SOURCE,
        sheet_name="Tatica Final",
        header=[2, 3],
    )
    if isinstance(source.columns, pd.MultiIndex):
        source.columns = [str(column[0]).strip() for column in source.columns]
    else:
        source.columns = [str(column).strip() for column in source.columns]

    required = ["Promax", "UF", "Rede", "CLUSTER REDE", "TTC Gôndola"]
    missing = [column for column in required if column not in source.columns]
    if missing:
        raise ValueError(
            "A Tática original não possui as colunas necessárias para o Repasse especial: "
            + ", ".join(missing)
        )

    network = source["Rede"].fillna("").astype(str).str.strip().str.upper()
    source = source.loc[~network.isin(ECOMMERCE_NETWORKS)].copy()
    source["UF"] = source["UF"].astype(str).str.strip().str.upper()
    source["Promax"] = pd.to_numeric(source["Promax"], errors="coerce")
    source["CV"] = source["CLUSTER REDE"].map(ns["normalize_channel"])
    source["TTC"] = source["TTC Gôndola"].map(ns["parse_number"])

    special = source.loc[
        source["UF"].eq("MS") & source["Promax"].isin(MS_SPECIAL_PROMAX)
    ].copy()

    invalid_channels = special.loc[
        special["CV"].isna(), "CLUSTER REDE"
    ].dropna().unique().tolist()
    if invalid_channels:
        raise ValueError(
            "A Tática tem valores de CLUSTER REDE não reconhecidos para os SKUs especiais de MS: "
            + ", ".join(map(str, invalid_channels))
        )

    result = {promax: {"V": None, "C": None} for promax in MS_SPECIAL_PROMAX}
    ambiguidades = []
    for promax in MS_SPECIAL_PROMAX:
        product_rows = special.loc[special["Promax"].eq(promax)]
        for channel in ("V", "C"):
            channel_rows = product_rows.loc[product_rows["CV"].eq(channel)]
            moda, frequencia, modas_empatadas = calcular_moda_tatica_unica(
                channel_rows["TTC"]
            )
            if modas_empatadas:
                details_cols = ["UF", "Rede", "CLUSTER REDE", "Promax", "TTC Gôndola"]
                details = channel_rows[details_cols].drop_duplicates().to_string(index=False)
                channel_name = "Varejo" if channel == "V" else "Atacado"
                ambiguidades.append(
                    f"MS / Promax {promax} / {channel_name}: modas empatadas {modas_empatadas} "
                    f"(frequência {frequencia})\n{details}"
                )
            else:
                result[promax][channel] = moda

    if ambiguidades:
        raise ValueError(
            "A moda do TTC Tática ficou empatada para uma ou mais combinações "
            "de MS / Promax / canal. Não foi escolhido um preço arbitrariamente:\n\n"
            + "\n\n".join(ambiguidades)
        )

    return result


def repasse_special_national_panel(tatica_prices, master):
    """Bloco nacional de MS: TTC Tática + R$0,10 para os dois SKUs."""
    master_by_promax = master.set_index("Promax")
    products = []
    fallback = {
        1898: ("BC 269", "BC269.png"),
        18860: ("BC 269 MP", "BC269MP.png"),
    }

    for promax in MS_SPECIAL_PROMAX:
        name, image_name = fallback[promax]
        if promax in master_by_promax.index:
            row = master_by_promax.loc[promax]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            name = str(row.get("NomeAbreviado") or row.get("Nome") or name).strip()
            image_name = str(row.get("NomeImg") or image_name).strip()

        image_path = img({"NomeImg": image_name, "NomeAbreviado": name, "Nome": name})
        if image_path is None:
            image_html = '<div class="repasse-no-img"></div>'
        else:
            uri = ns["image_data_uri"](
                str(image_path), image_path.stat().st_mtime_ns, preserve_resolution=False
            )
            image_html = f'<img src="{uri}" alt="{escape(name, quote=True)}">'
        products.append({"promax": promax, "name": name, "image_html": image_html})

    columns = f'minmax(108px,0.72fr) repeat({len(products)},minmax(0,1fr))'
    h = [
        '<section class="repasse-package repasse-special-package">',
        '<div class="repasse-special-heading">',
        '<div class="repasse-special-title">MS — Vigência 14/12</div>',
        '<div class="repasse-special-badge">NACIONAIS</div>',
        '</div>',
        '<div class="repasse-special-note">TTC Tática acrescido de R$ 0,10</div>',
        f'<div class="repasse-grid" style="grid-template-columns:{columns}">',
        '<div class="repasse-label"></div>',
    ]

    for product in products:
        name = escape(product["name"], quote=True)
        h.append(
            '<div class="repasse-product">'
            f'<div class="repasse-name" title="{name}">{name}</div>'
            f'<div class="repasse-img">{product["image_html"]}</div>'
            '<div class="repasse-rule"></div></div>'
        )

    row_definitions = [
        ("Varejo — TTC", "V", "repasse-v", "repasse-label-v", "ttc"),
        ("Atacado — TTC", "C", "repasse-a", "repasse-label-a", "ttc"),
        ("Varejo — Δ", "V", "repasse-d", "repasse-label-d", "delta"),
        ("Atacado — Δ", "C", "repasse-d", "repasse-label-d", "delta"),
    ]
    for label, channel, cell_class, label_class, field in row_definitions:
        h.append(f'<div class="repasse-label {label_class}"><span>{escape(label)}</span></div>')
        for product in products:
            base_price = tatica_prices.get(product["promax"], {}).get(channel)
            if field == "ttc":
                value = money(round(base_price + MS_SPECIAL_DELTA, 2)) if base_price is not None else "-"
            else:
                value = delta(MS_SPECIAL_DELTA)
            h.append(
                f'<div class="repasse-cell"><span class="repasse-pill {cell_class}">'
                f'{escape(value)}</span></div>'
            )

    h.append('</div></section>')
    return ''.join(h)


def rep_panel(uf, d, m, tatica_prices):
    d = d[d.aba_uf == uf].copy()
    logo = ns['image_data_uri'](str(LOGO_FILE), LOGO_FILE.stat().st_mtime_ns, preserve_resolution=False)
    display_uf = 'MT/AC/RO' if uf == 'MT' else uf
    title = 'Repasse vigência 16/11'

    h = [
        f'<section class="uf-panel" id="rep-{uf}">',
        f'<header class="repasse-header"><div class="uf">{escape(display_uf)}</div>'
        f'<div class="repasse-title">{title}</div><img class="brand-logo" src="{logo}"></header>',
    ]

    if d.empty and uf != 'MS':
        h.append(
            '<section class="repasse-package">'
            '<div class="repasse-package-title">Nenhum repasse encontrado</div>'
            '</section>'
        )
    else:
        cm = m.set_index('Promax')
        ps = []
        for promax in d.codigo_promax.dropna().unique():
            if promax in cm.index:
                row = cm.loc[promax]
                row = row.iloc[0] if isinstance(row, pd.DataFrame) else row
                name = str(row.NomeAbreviado or row.Nome).strip()
                image_name = str(row.NomeImg)
            else:
                row = d[d.codigo_promax == promax].iloc[0]
                name = str(row.produto)
                image_name = ''

            # Os dois SKUs regionais de MS precisam aparecer na vigência normal
            # mesmo quando não houver linha deles no repasse.csv. O cadastro
            # visual é fixo para evitar que o De/Para trate o MP como BC 269.
            try:
                promax_int = int(float(promax))
            except (TypeError, ValueError):
                promax_int = -1
            if uf == 'MS' and promax_int in MS_SPECIAL_PROMAX:
                name, image_name = {
                    1898: ('BC 269', 'BC269.png'),
                    18860: ('BC 269 MP', 'BC269MP.png'),
                }[promax_int]

            ps.append({
                'Promax': promax,
                'NomeAbreviado': name,
                'Nome': name,
                'NomeImg': image_name,
            })

        # A lista principal da vigência 16/11 deve sempre conter BC 269 e
        # BC 269 MP como Regionais, mesmo que o CSV não traga repasse para eles.
        # Quando houver dados no CSV, as linhas serão exibidas normalmente;
        # na ausência de dados daquele SKU/canal, as células ficam como '-'.
        if uf == 'MS':
            existing_promax = {
                int(float(item['Promax'])) for item in ps
                if pd.notna(item.get('Promax'))
            }
            regional_catalog = {
                1898: ('BC 269', 'BC269.png'),
                18860: ('BC 269 MP', 'BC269MP.png'),
            }
            for promax in MS_SPECIAL_PROMAX:
                if promax not in existing_promax:
                    name, image_name = regional_catalog[promax]
                    ps.append({
                        'Promax': promax,
                        'NomeAbreviado': name,
                        'Nome': name,
                        'NomeImg': image_name,
                    })

        ps = pd.DataFrame(ps)
        ps['Embalagem'] = ps.apply(
            lambda row: ns['classify_package'](row.Promax, row.NomeAbreviado), axis=1
        )
        package_order = {package: index for index, package in enumerate(PACKAGES)}
        ps['_ordem_embalagem'] = ps.Embalagem.map(package_order).fillna(99)

        # Mantém a ordenação padrão da aba de Repasse.
        price_order = d.groupby('codigo_promax', sort=False)['ttc_gondola_novo'].mean()
        if uf == 'MS':
            for promax in MS_SPECIAL_PROMAX:
                if promax not in price_order.index or pd.isna(price_order.get(promax)):
                    regional_prices = [
                        price + MS_SPECIAL_DELTA
                        for price in tatica_prices.get(promax, {}).values()
                        if price is not None
                    ]
                    if regional_prices:
                        price_order.loc[promax] = sum(regional_prices) / len(regional_prices)
        ps['_ordem_preco'] = ps.Promax.map(price_order)
        ps = ps.sort_values(
            ['_ordem_embalagem', '_ordem_preco', 'NomeAbreviado'],
            na_position='last',
            kind='stable',
        ).reset_index(drop=True)

        for package in PACKAGES:
            products = ps[ps.Embalagem == package]
            if products.empty:
                continue

            h.append(
                f'<section class="repasse-package"><div class="repasse-package-title">{escape(package)}</div>'
            )
            for start in range(0, len(products), MAX_PRODUCTS_PER_ROW):
                chunk = products.iloc[start:start + MAX_PRODUCTS_PER_ROW]
                columns = f'minmax(108px,0.72fr) repeat({MAX_PRODUCTS_PER_ROW},minmax(0,1fr))'
                h.append(
                    f'<div class="repasse-grid" style="grid-template-columns:{columns}"><div class="repasse-label"></div>'
                )

                for product in chunk.itertuples(index=False):
                    image_path = img(product._asdict())
                    if image_path is None:
                        image_html = '<div class="repasse-no-img"></div>'
                    else:
                        uri = ns['image_data_uri'](
                            str(image_path), image_path.stat().st_mtime_ns, preserve_resolution=False
                        )
                        name = escape(product.NomeAbreviado, quote=True)
                        image_html = f'<img src="{uri}" alt="{name}">'
                    name = escape(product.NomeAbreviado, quote=True)
                    is_regional = uf == 'MS' and int(product.Promax) in MS_SPECIAL_PROMAX
                    scope_html = '<small class="repasse-scope">(Regionais)</small>' if is_regional else ''
                    product_class = 'repasse-product repasse-product-regionais' if is_regional else 'repasse-product'
                    h.append(
                        f'<div class="{product_class}">'
                        f'<div class="repasse-name" title="{name}">{name}{scope_html}</div>'
                        f'<div class="repasse-img">{image_html}</div>'
                        '<div class="repasse-rule"></div></div>'
                    )
                h.extend(
                    '<div class="repasse-product repasse-spacer"></div>'
                    for _ in range(MAX_PRODUCTS_PER_ROW - len(chunk))
                )

                row_definitions = [
                    ('Varejo — TTC', 'Varejo', 'ttc_gondola_novo', 'repasse-v', 'repasse-label-v', True),
                    ('Atacado — TTC', 'Atacado', 'ttc_gondola_novo', 'repasse-a', 'repasse-label-a', True),
                    ('Varejo — Δ', 'Varejo', 'diferenca_preco', 'repasse-d', 'repasse-label-d', False),
                    ('Atacado — Δ', 'Atacado', 'diferenca_preco', 'repasse-d', 'repasse-label-d', False),
                ]
                for label, classification, field, cell_class, label_class, price_row in row_definitions:
                    h.append(f'<div class="repasse-label {label_class}"><span>{escape(label)}</span></div>')
                    for product in chunk.itertuples(index=False):
                        subset = d[d.codigo_promax == product.Promax]
                        subset = subset[subset.classificacao == classification]
                        is_regional_ms = (
                            uf == 'MS'
                            and int(float(product.Promax)) in MS_SPECIAL_PROMAX
                        )

                        # MT/AC/RO é só o rótulo da aba. Usa MT primeiro; AC/RO ficam como fallback.
                        if uf == 'MT':
                            canonical_rows = subset.iloc[0:0].copy()
                            for source_uf in ('MT', 'AC', 'RO'):
                                candidate = subset[subset.uf == source_uf]
                                if not candidate.empty:
                                    canonical_rows = candidate.copy()
                                    break
                        else:
                            canonical_rows = subset[subset.uf == uf]
                            # Para BC 269 e BC 269 MP de MS, não reutilizar preço
                            # de outra UF; o fallback vem da vigência nacional 14/12.
                            if canonical_rows.empty and not is_regional_ms:
                                canonical_rows = subset

                        numeric_values = pd.to_numeric(canonical_rows[field], errors='coerce').dropna()
                        if numeric_values.empty:
                            number = None
                            value = '-'
                        else:
                            number = round(float(numeric_values.iloc[0]), 2)
                            value = money(number) if field == 'ttc_gondola_novo' else delta(number)

                        if number is None and is_regional_ms:
                            channel = 'V' if classification == 'Varejo' else 'C'
                            base_price = tatica_prices.get(
                                int(float(product.Promax)), {}
                            ).get(channel)
                            if field == 'ttc_gondola_novo' and base_price is not None:
                                number = round(base_price + MS_SPECIAL_DELTA, 2)
                            elif field == 'diferenca_preco':
                                number = MS_SPECIAL_DELTA
                            if number is not None:
                                value = (
                                    money(number)
                                    if field == 'ttc_gondola_novo'
                                    else delta(number)
                                )

                        delta_values = pd.to_numeric(canonical_rows['diferenca_preco'], errors='coerce').dropna()
                        delta_number = round(float(delta_values.iloc[0]), 2) if not delta_values.empty else None
                        price_is_down = delta_number is not None and delta_number < 0
                        highlight_down = (price_row and price_is_down) or (field == 'diferenca_preco' and number is not None and number < 0)
                        highlight_class = ' repasse-down' if highlight_down else ''
                        tooltip = 'Preço em queda' if highlight_down else str(value)
                        h.append(
                            f'<div class="repasse-cell"><span class="repasse-pill {cell_class}{highlight_class}" '
                            f'title="{escape(tooltip, quote=True)}">{escape(str(value))}</span></div>'
                        )
                    h.extend(
                        '<div class="repasse-cell repasse-spacer"></div>'
                        for _ in range(MAX_PRODUCTS_PER_ROW - len(chunk))
                    )
                h.append('</div>')
            h.append('</section>')

    if uf == 'MS':
        h.append(repasse_special_national_panel(tatica_prices, m))
    h.append('</section>')
    return ''.join(h)

def main():
    master = ns['load_master'](str(MASTER_FILE), MASTER_FILE.stat().st_mtime_ns)
    tree = ns['load_tree'](str(TREE_FILE), TREE_FILE.stat().st_mtime_ns)
    ctr = ns['load_ctr'](str(CTR_FILE), CTR_FILE.stat().st_mtime_ns)
    tree = tree.merge(
        ctr[['UF', 'Promax', 'CTR']],
        on=['UF', 'Promax'],
        how='left',
        validate='many_to_one',
    )

    rm = rep_master()
    rd = rep_data()
    ms_special_tatica = load_ms_special_tatica_prices()

    tree_ufs = ['AM', 'MT', 'GO', 'DF', 'MS', 'AC', 'RO']
    tree_tabs = ''.join(
        f'<button class="tab-btn tree-sub {"active" if i == 0 else ""}" data-target="tree-{uf}">{uf}</button>'
        for i, uf in enumerate(tree_ufs)
    )
    tree_panels = []
    for i, uf in enumerate(tree_ufs):
        products, prices_by_sku = ns['prepare_tree_page'](uf, master, tree)
        page_html = ns['build_page'](uf, products, prices_by_sku)
        tree_panels.append(
            f'<section class="uf-panel {"active" if i == 0 else ""}" id="tree-{uf}">{page_html}</section>'
        )

    rep_tabs = ''.join(
        f'<button class="tab-btn rep-sub {"active" if i == 0 else ""}" data-target="rep-{uf}">{"MT/AC/RO" if uf == "MT" else uf}</button>'
        for i, uf in enumerate(REPASSE_UFS)
    )
    rep_panels = [rep_panel(uf, rd, rm, ms_special_tatica) for uf in REPASSE_UFS]

    html = (
        '<!doctype html><html lang="pt-BR"><head>'
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Árvore de Preços</title>'
        + CSS + REPASSE_CSS
        + '</head><body><div class="site-shell">'
        '<div class="site-tabs">'
        '<button class="tab-btn active" data-main="tree-main">Árvore de Preços</button>'
        '<button class="tab-btn" data-main="rep-main">Repasse</button>'
        '</div>'
        '<section id="tree-main" class="site-panel active"><div class="subtabs">'
        + tree_tabs + '</div>' + ''.join(tree_panels) + '</section>'
        '<section id="rep-main" class="site-panel"><div class="subtabs">'
        + rep_tabs + '</div>' + ''.join(rep_panels) + '</section>'
        '</div><script>'
        'const mains=document.querySelectorAll("[data-main]"),mps=document.querySelectorAll(".site-panel");'
        'mains.forEach(b=>b.onclick=()=>{mps.forEach(p=>p.classList.remove("active"));'
        'document.getElementById(b.dataset.main).classList.add("active");'
        'mains.forEach(x=>x.classList.toggle("active",x===b))});'
        'function sub(a,s){document.querySelectorAll(a).forEach(b=>b.onclick=()=>{'
        'document.querySelectorAll(s).forEach(p=>p.classList.remove("active"));'
        'document.getElementById(b.dataset.target).classList.add("active");'
        'document.querySelectorAll(a).forEach(x=>x.classList.toggle("active",x===b))})}'
        'sub(".tree-sub","#tree-main .uf-panel");'
        'sub(".rep-sub","#rep-main .uf-panel");'
        '</script></body></html>'
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding='utf-8')
    print(f'HTML gerado em: {OUT}')
    print('Repasse especial de MS: TTC Tática + R$ 0,10 para BC 269 e BC 269 MP.')


if __name__=='__main__': main()
