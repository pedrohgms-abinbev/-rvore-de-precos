from __future__ import annotations

import base64
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HTML_FILE = ROOT / "site-premium" / "arvore_precos_premium.html"
REPASSE_FILE = ROOT / "data" / "processed" / "repasse.csv"
DEPARA_FILE = ROOT / "cadastro" / "de_para_repasse.xlsx"
IMAGE_DIR = ROOT / "images" / "img"

UF_OPTIONS = ["AM", "MT", "GO", "DF", "MS", "AC", "RO"]
REPASSE_ALL_UFS = ["AM", "MT", "GO", "DF", "MS"]
PACKAGES = ["Lata 269ml", "Lata 350ml", "Long Neck", "Outros"]


def norm(value: object) -> str:
    text = "" if value is None or pd.isna(value) else str(value)
    text = unicodedata.normalize("NFKD", text).upper()
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]+", "", text)


def image_uri(path: Path) -> str | None:
    if not path.is_file():
        return None
    mime = "image/png"
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
    elif suffix == ".webp":
        mime = "image/webp"
    elif suffix == ".gif":
        mime = "image/gif"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def resolve_image(filename: object) -> str | None:
    name = str(filename or "").strip()
    if not name:
        return None

    exact = IMAGE_DIR / name
    if exact.is_file():
        return image_uri(exact)

    target = norm(name)
    if not target:
        return None

    # Resolve differences such as "SKZ LN.png" vs "SKZLN.png",
    # capitalization and spaces without changing the De/Para itself.
    candidates = []
    if IMAGE_DIR.is_dir():
        for path in IMAGE_DIR.iterdir():
            if path.is_file() and norm(path.name) == target:
                candidates.append(path)
    if candidates:
        return image_uri(sorted(candidates, key=lambda p: p.name.casefold())[0])
    return None


def classify_package(promax: object, short_name: str) -> str:
    if str(promax).strip() == "18780":
        return "Long Neck"
    label = str(short_name or "").strip().upper()
    if label.endswith("LN") or " LN" in label:
        return "Long Neck"
    if "350" in label:
        return "Lata 350ml"
    if "269" in label:
        return "Lata 269ml"
    return "Outros"


def load_data() -> list[dict]:
    repasse = pd.read_csv(REPASSE_FILE, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    repasse.columns = repasse.columns.str.strip()
    depara = pd.read_excel(DEPARA_FILE, dtype=object)
    depara.columns = depara.columns.astype(str).str.strip()

    depara["Promax"] = pd.to_numeric(depara["Promax"], errors="coerce")
    for col in ["Nome", "NomeAbreviado", "NomeImg"]:
        if col not in depara.columns:
            depara[col] = ""
        depara[col] = depara[col].fillna("").astype(str).str.strip()

    # Exact normalized product-name lookup. This is important because Promax
    # 36028 exists more than once in the Repasse De/Para.
    name_lookup: dict[tuple[int, str], pd.Series] = {}
    unique_by_promax: dict[int, pd.Series] = {}
    ambiguous: set[int] = set()
    for _, row in depara.dropna(subset=["Promax"]).iterrows():
        code = int(row["Promax"])
        key = (code, norm(row["Nome"]))
        if key[1]:
            name_lookup[key] = row
        if code in unique_by_promax:
            ambiguous.add(code)
        else:
            unique_by_promax[code] = row
    for code in ambiguous:
        unique_by_promax.pop(code, None)

    output: list[dict] = []
    missing_images: set[str] = set()

    for _, row in repasse.iterrows():
        uf = str(row.get("uf", "")).strip().upper()
        if uf not in UF_OPTIONS:
            continue
        product = str(row.get("produto", "")).strip()
        try:
            promax = int(float(row.get("codigo_promax", "")))
        except (TypeError, ValueError):
            continue

        match = name_lookup.get((promax, norm(product)))
        if match is None:
            match = unique_by_promax.get(promax)

        short_name = str(match["NomeAbreviado"]) if match is not None else product
        image_name = str(match["NomeImg"]) if match is not None else ""
        uri = resolve_image(image_name)

        # Fallback para imagens cujo nome no cadastro não bate exatamente com
        # o arquivo físico (ex.: SKZ 350 / SKZ350, SKZ LN / SKZLN).
        if uri is None:
            fallback_names = [short_name, product]
            for fallback in fallback_names:
                base = norm(fallback)
                if not base or not IMAGE_DIR.is_dir():
                    continue
                found = next(
                    (path for path in IMAGE_DIR.iterdir()
                     if path.is_file() and norm(path.stem) == base),
                    None,
                )
                if found is not None:
                    uri = image_uri(found)
                    break

        if image_name and uri is None:
            missing_images.add(image_name)

        try:
            ttc = float(str(row["ttc_gondola_novo"]).replace(",", "."))
        except (TypeError, ValueError):
            ttc = None
        try:
            delta = float(str(row["diferenca_preco"]).replace(",", "."))
        except (TypeError, ValueError):
            delta = None

        output.append(
            {
                "uf": uf,
                "produto": product,
                "promax": promax,
                "nome": short_name,
                "imagem": uri,
                "embalagem": classify_package(promax, short_name),
                "classificacao": str(row.get("classificacao", "")).strip().title(),
                "mes": str(row.get("mes_repasse", "")).strip(),
                "ttc": ttc,
                "delta": delta,
            }
        )

    # Dedup identical records for safety.
    unique = {}
    for item in output:
        key = tuple(item[k] for k in ("uf", "produto", "promax", "classificacao", "mes", "ttc", "delta"))
        unique[key] = item

    if missing_images:
        print("Imagens não encontradas:")
        for name in sorted(missing_images):
            print(f"  - {name}")

    return list(unique.values())


def inject(html: str, data: list[dict]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    css = r"""
<style id="repasse-extension-css">
.view-tabs{display:flex;gap:.45rem;margin:0 0 1rem;padding:.3rem;border:1px solid var(--line);border-radius:1rem;background:var(--surface-soft);width:max-content}
.view-tab{border:1px solid transparent;border-radius:.7rem;padding:.55rem .9rem;background:transparent;color:var(--muted);font-weight:800;font-size:.78rem;cursor:pointer}
.view-tab.active{background:var(--surface-strong);border-color:var(--line);color:var(--blue);box-shadow:0 5px 18px rgba(0,0,0,.08)}
#repasse-view{margin:0 0 1rem}
.repasse-toolbar{display:flex;align-items:end;gap:.8rem;margin:0 0 1rem;padding:1rem;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface)}
.repasse-toolbar label{display:flex;flex-direction:column;gap:.35rem;color:var(--muted);font-size:.7rem;font-weight:800}
.repasse-toolbar select{min-width:120px;padding:.55rem .7rem;border:1px solid var(--line);border-radius:.65rem;background:var(--surface-strong);color:var(--text)}
.repasse-summary{display:flex;flex-wrap:wrap;gap:.65rem;margin-bottom:1rem}
.repasse-kpi{min-width:110px;padding:.75rem 1rem;border:1px solid var(--line);border-radius:1rem;background:var(--surface);box-shadow:var(--shadow)}
.repasse-kpi small{display:block;color:var(--muted);font-size:.62rem;font-weight:800;text-transform:uppercase}
.repasse-kpi strong{display:block;margin-top:.2rem;color:var(--blue);font-size:1.15rem}
.repasse-package{position:relative;margin-bottom:1rem;padding:1rem 1rem 1.05rem;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);box-shadow:var(--shadow);overflow-x:auto}
.repasse-package:before{content:"";position:absolute;left:0;top:1rem;bottom:1rem;width:4px;border-radius:4px;background:var(--blue-strong)}
.repasse-package-title{margin:0 0 .7rem .25rem;color:var(--text);font-size:.78rem;font-weight:900;letter-spacing:.06em;text-transform:uppercase}
.repasse-grid{display:grid;min-width:850px;align-items:stretch}
.repasse-label{display:flex;align-items:center;justify-content:center;padding:.2rem}
.repasse-label span{width:100%;max-width:90px;padding:.35rem .2rem;border-radius:.65rem;color:#fff;text-align:center;font-size:.57rem;font-weight:900}
.repasse-product{height:150px;padding:.15rem .2rem;display:flex;flex-direction:column;align-items:center;justify-content:end}
.repasse-name{width:100%;height:2.1rem;overflow:hidden;text-align:center;color:var(--text);font-size:.62rem;font-weight:800;line-height:1.15}
.repasse-img{height:90px;width:100%;display:flex;align-items:end;justify-content:center}
.repasse-img img{max-width:78px;max-height:88px;object-fit:contain;filter:drop-shadow(0 1px 1px rgba(0,0,0,.12))}
.repasse-no-img{width:38px;height:58px;border:1px dashed var(--line);border-radius:4px}
.repasse-rule{width:55%;max-width:42px;height:2px;margin-top:.2rem;background:var(--orange);border-radius:2px}
.repasse-cell{display:flex;align-items:center;justify-content:center;padding:.18rem}
.repasse-pill{width:100%;padding:.35rem .2rem;border-radius:.65rem;text-align:center;font-size:.62rem;font-weight:900;white-space:nowrap;overflow:hidden}
.repasse-v{background:var(--pink)} .repasse-a{background:var(--green)} .repasse-d{background:var(--orange)} .repasse-m{background:var(--surface-soft);color:var(--blue)}
.repasse-label-v span{background:var(--pink);color:#fff}.repasse-label-a span{background:var(--green);color:#fff}.repasse-label-d span{background:var(--orange);color:#fff}.repasse-label-m span{background:var(--blue-strong)}.repasse-label-uf span{background:var(--blue);color:#fff}.repasse-uf-pill{background:var(--surface-soft);color:var(--blue);border:1px solid var(--line)}
.repasse-uf-tabs{display:flex;gap:.45rem;margin:0 0 1rem;padding:.3rem;border:1px solid var(--line);border-radius:1rem;background:var(--surface-soft);width:max-content}.repasse-uf-tab{border:0;border-radius:.7rem;background:transparent;color:var(--muted);padding:.55rem 1rem;font-weight:900;cursor:pointer}.repasse-uf-tab.active{background:var(--blue);color:#fff;box-shadow:var(--shadow)}
@media(max-width:700px){.view-tabs{width:100%}.view-tab{flex:1}.repasse-toolbar{align-items:stretch}.repasse-grid{min-width:850px}}
</style>
"""

    markup = r"""
<div class="view-tabs" role="tablist" aria-label="Visualização">
  <button id="tab-tree" class="view-tab active" type="button">Árvore de Preços</button>
  <button id="tab-repasse" class="view-tab" type="button">Repasse</button>
</div>
<section id="repasse-view" hidden>
  <div class="repasse-toolbar">
    <div class="repasse-toolbar-title">Repasses</div>
    <div class="repasse-toolbar-subtitle">Selecione a UF para visualizar os repasses</div>
  </div>
  <div class="repasse-uf-tabs" role="tablist" aria-label="UF do Repasse">
    <button class="repasse-uf-tab active" data-uf="AM" type="button">AM</button>
    <button class="repasse-uf-tab" data-uf="MT" type="button">MT</button>
    <button class="repasse-uf-tab" data-uf="GO" type="button">GO</button>
    <button class="repasse-uf-tab" data-uf="DF" type="button">DF</button>
    <button class="repasse-uf-tab" data-uf="MS" type="button">MS</button>
  </div>
  <div id="repasse-content"></div>
</section>
"""

    script = f"""
<script id="repasse-extension-script">
window.REPASSE_SITE_DATA = {payload};
(function() {{
  const treeTab = document.getElementById('tab-tree');
  const repasseTab = document.getElementById('tab-repasse');
  const repasseView = document.getElementById('repasse-view');
  const repasseContent = document.getElementById('repasse-content');
  const treeToolbar = document.querySelector('.toolbar');
  const tree = document.getElementById('tree');
  const results = document.getElementById('results');
  const status = document.getElementById('status');
  const data = window.REPASSE_SITE_DATA;

  function money(value) {{
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
    return Number(value).toLocaleString('pt-BR', {{minimumFractionDigits:2, maximumFractionDigits:2}});
  }}
  function delta(value) {{
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
    const n = Number(value);
    return (n > 0 ? '+' : '') + n.toLocaleString('pt-BR', {{minimumFractionDigits:2, maximumFractionDigits:2}});
  }}
  function esc(value) {{
    return String(value ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;');
  }}
  function renderRepasse(selectedUf = 'AM') {{
    const sourceUfs = selectedUf === 'MT' ? new Set(['MT','AC','RO']) : new Set([selectedUf]);
    const rows = data.filter(row => sourceUfs.has(String(row.uf || '').toUpperCase()));
    if (!rows.length) {{
      repasseContent.innerHTML = '<section class="repasse-package"><strong>Nenhum repasse encontrado.</strong></section>';
      return;
    }}

    const products = [];
    const seen = new Set();
    for (const row of rows) {{
      const key = row.promax + '|' + row.nome;
      if (!seen.has(key)) {{ seen.add(key); products.push(row); }}
    }}

    const packages = ["Lata 269ml", "Lata 350ml", "Long Neck", "Outros"];
    const total = rows.length;
    const productCount = new Set(rows.map(x => x.promax)).size;
    const varejo = rows.filter(x => x.classificacao.toLowerCase() === 'varejo').length;
    const atacado = rows.filter(x => x.classificacao.toLowerCase() === 'atacado').length;

    let html = '<div class="repasse-summary">' +
      '<div class="repasse-kpi"><small>Repasses</small><strong>' + total + '</strong></div>' +
      '<div class="repasse-kpi"><small>Produtos</small><strong>' + productCount + '</strong></div>' +
      '<div class="repasse-kpi"><small>Varejo</small><strong>' + varejo + '</strong></div>' +
      '<div class="repasse-kpi"><small>Atacado</small><strong>' + atacado + '</strong></div>' +
      '</div>';

    for (const pkg of packages) {{
      const ps = products.filter(x => x.embalagem === pkg);
      if (!ps.length) continue;
      const cols = '76px repeat(' + ps.length + ', minmax(88px,1fr))';
      html += '<section class="repasse-package"><div class="repasse-package-title">' + esc(pkg) + '</div>';
      html += '<div class="repasse-grid" style="grid-template-columns:' + cols + '"><div class="repasse-label"></div>';
      for (const p of ps) {{
        html += '<div class="repasse-product"><div class="repasse-name" title="' + esc(p.nome) + '">' + esc(p.nome) + '</div><div class="repasse-img">' +
          (p.imagem ? '<img src="' + p.imagem + '" alt="' + esc(p.nome) + '">' : '<div class="repasse-no-img"></div>') +
          '</div><div class="repasse-rule"></div></div>';
      }}

      html += '<div class="repasse-label repasse-label-m"><span>UF</span></div>';
      for (const p of ps) {{
        html += '<div class="repasse-cell"><span class="repasse-pill repasse-m">' + esc(selectedUf) + '</span></div>';
      }}

      const rowsDef = [
        ['Varejo — TTC','Varejo','ttc','repasse-v','repasse-label-v'],
        ['Atacado — TTC','Atacado','ttc','repasse-a','repasse-label-a'],
        ['Varejo — Δ','Varejo','delta','repasse-d','repasse-label-d'],
        ['Atacado — Δ','Atacado','delta','repasse-d','repasse-label-d'],
      ];
      for (const [label, cls, field, cell, labelClass] of rowsDef) {{
        html += '<div class="repasse-label ' + labelClass + '"><span>' + label + '</span></div>';
        for (const p of ps) {{
          const candidates = rows.filter(x => x.promax === p.promax && x.classificacao === cls);
          const r = candidates[candidates.length - 1];
          const value = r ? (field === 'ttc' ? money(r.ttc) : delta(r.delta)) : '-';
          html += '<div class="repasse-cell"><span class="repasse-pill ' + cell + '">' + value + '</span></div>';
        }}
      }}

      html += '<div class="repasse-label repasse-label-m"><span>MÊS</span></div>';
      for (const p of ps) {{
        const months = [...new Set(rows.filter(x => x.promax === p.promax).map(x => x.mes).filter(Boolean))];
        html += '<div class="repasse-cell"><span class="repasse-pill repasse-m">' + esc(months.join(' / ') || '-') + '</span></div>';
      }}
      html += '</div></section>';
    }}
    repasseContent.innerHTML = html;
  }}

  function showTree() {{
    treeTab.classList.add('active'); repasseTab.classList.remove('active');
    repasseView.hidden = true;
    if (treeToolbar) treeToolbar.hidden = false;
    if (tree) tree.hidden = false;
    if (results) results.hidden = results.dataset.wasHidden === 'true';
    if (status) status.hidden = status.dataset.wasHidden === 'true';
  }}
  function showRepasse() {{
    treeTab.classList.remove('active'); repasseTab.classList.add('active');
    if (treeToolbar) treeToolbar.hidden = true;
    if (tree) {{ tree.dataset.wasHidden = tree.hidden ? 'true' : 'false'; tree.hidden = true; }}
    if (results) {{ results.dataset.wasHidden = results.hidden ? 'true' : 'false'; results.hidden = true; }}
    if (status) {{ status.dataset.wasHidden = status.hidden ? 'true' : 'false'; status.hidden = true; }}
    repasseView.hidden = false;
    const activeUf = document.querySelector('.repasse-uf-tab.active');
    renderRepasse(activeUf ? activeUf.dataset.uf : 'AM');
  }}
  treeTab.addEventListener('click', showTree);
  repasseTab.addEventListener('click', showRepasse);
  document.querySelectorAll('.repasse-uf-tab').forEach(tab => {{
    tab.addEventListener('click', () => {{
      document.querySelectorAll('.repasse-uf-tab').forEach(item => item.classList.remove('active'));
      tab.classList.add('active');
      renderRepasse(tab.dataset.uf);
    }});
  }});
}})();
</script>
"""

    # Insert the controls immediately before the existing toolbar.
    marker = '<section class="toolbar"'
    if marker not in html:
        raise ValueError("Não encontrei a toolbar do HTML premium para inserir a aba Repasse.")
    html = html.replace(marker, markup + marker, 1)
    html = html.replace('</head>', css + '</head>', 1)
    html = html.replace('</body>', script + '</body>', 1)
    return html


def main() -> None:
    if not HTML_FILE.is_file():
        raise FileNotFoundError(f"HTML premium não encontrado: {HTML_FILE}")
    if not REPASSE_FILE.is_file():
        raise FileNotFoundError(f"Repasse processado não encontrado: {REPASSE_FILE}")
    if not DEPARA_FILE.is_file():
        raise FileNotFoundError(f"De/Para do Repasse não encontrado: {DEPARA_FILE}")

    html = HTML_FILE.read_text(encoding="utf-8")
    data = load_data()
    HTML_FILE.write_text(inject(html, data), encoding="utf-8")
    print(f"Aba Repasse integrada ao HTML: {HTML_FILE}")
    print(f"Registros de repasse incorporados: {len(data):,}")


if __name__ == "__main__":
    main()
