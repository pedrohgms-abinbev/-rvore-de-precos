const state = { data: null, uf: "AM", search: "" };
const PRICE_FIELDS = [
  ["TTC Tática", "TTC", "ttc"],
  ["PP", "PP", "pp"],
  ["Calendário", "CAL", "calendar"],
  ["CTR L3M", "CTR", "ctr"],
];

const app = document.querySelector("#app");
const ufFilter = document.querySelector("#uf-filter");
const searchInput = document.querySelector("#search");
const refreshButton = document.querySelector("#refresh");
const statusElement = document.querySelector("#status");
const treeElement = document.querySelector("#tree");
const resultsElement = document.querySelector("#results");
const packageTemplate = document.querySelector("#package-template");

function showStatus(message, type = "") {
  statusElement.hidden = false;
  statusElement.className = `status ${type}`.trim();
  statusElement.textContent = message;
}

function clearStatus() {
  statusElement.hidden = true;
  statusElement.textContent = "";
}

function setLoading(isLoading) {
  refreshButton.disabled = isLoading;
  refreshButton.textContent = isLoading ? "Atualizando…" : "Atualizar";
}

function formatPrice(value) {
  if (value == null || Number.isNaN(value)) return "-";
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatRatio(value) {
  if (value == null || Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(1).replace(".", ",")}%`;
}

function commercialPriceText(record, field) {
  const channelPrices = record?.ChannelPrices?.[field];
  if (!channelPrices) return null;
  const availableChannels = ["C", "V"].filter((channel) => Number.isFinite(channelPrices[channel]));
  if (!availableChannels.length) return "-";

  if (availableChannels.length === 2 &&
      formatPrice(channelPrices.C) === formatPrice(channelPrices.V)) {
    return `R$ ${formatPrice(channelPrices.C)}`;
  }

  return availableChannels
    .map((channel) => `R$ ${formatPrice(channelPrices[channel])} ${channel}`)
    .join("/");
}

function priceLabel(record, field) {
  if (field !== "CTR" && record?.ChannelPrices?.[field]) {
    return commercialPriceText(record, field);
  }
  const price = record?.Prices?.[field] ??
    (field === "TTC" && Number.isFinite(record?.TTC_Referencia) ? record.TTC_Referencia : null);
  if (field === "CTR") return formatRatio(price);
  if (price == null) return "-";
  return `R$ ${formatPrice(price)}`;
}

function priceSummary(record, field) {
  if (field !== "CTR" && record?.ChannelPrices?.[field]) {
    return commercialPriceText(record, field);
  }
  const price = record?.Prices?.[field] ??
    (field === "TTC" && Number.isFinite(record?.TTC_Referencia) ? record.TTC_Referencia : null);
  if (field === "CTR") return formatRatio(price);
  if (price == null) return "-";
  return `R$ ${formatPrice(price)}`;
}

function imagePath(product) {
  return `images/${encodeURIComponent(product.NomeImg)}`;
}

function referencePrice(product) {
  if (Number.isFinite(product.TTC_Referencia)) return product.TTC_Referencia;
  return Number.isFinite(product.Prices?.TTC) ? product.Prices.TTC : null;
}

function buildTreePage(products, uf) {
  const packages = new Map();
  for (const product of products) {
    if (!packages.has(product.Embalagem)) packages.set(product.Embalagem, []);
    packages.get(product.Embalagem).push(product);
  }

  const packageOrder = new Map(state.data.packages.map((name, index) => [name, index]));
  const sections = [...packages.entries()]
    .sort(([a], [b]) => (packageOrder.get(a) ?? 99) - (packageOrder.get(b) ?? 99))
    .map(([packageName, packageProducts]) => {
      packageProducts.sort((a, b) => {
        const priceA = referencePrice(a);
        const priceB = referencePrice(b);
        if (priceA == null && priceB != null) return 1;
        if (priceA != null && priceB == null) return -1;
        return (priceA ?? 0) - (priceB ?? 0) || Number(a.Promax) - Number(b.Promax);
      });
      const fragment = packageTemplate.content.cloneNode(true);
      fragment.querySelector(".package-name").textContent = packageName;
      fragment.querySelector(".package-count").textContent = `${packageProducts.length} produtos`;
      const matrix = fragment.querySelector(".matrix");
      const gridColumns = `66px repeat(${packageProducts.length}, minmax(0, 1fr))`;
      matrix.style.gridTemplateColumns = gridColumns;
      matrix.appendChild(createCell("", "row-label"));

      for (const product of packageProducts) {
        const slot = document.createElement("div");
        slot.className = "product-slot";
        slot.innerHTML = `
          <div class="product" style="bottom:${product.Elevacao.toFixed(1)}px">
            <div class="product-name" title="${escapeHtml(product.NomeAbreviado)}">${escapeHtml(product.NomeAbreviado)}</div>
            <div class="product-image"><img src="${imagePath(product)}" alt="${escapeHtml(product.NomeAbreviado)}"></div>
            <div class="orange-rule"></div>
          </div>`;
        matrix.appendChild(slot);
      }

      const mobileProducts = fragment.querySelector(".mobile-products");
      for (const product of packageProducts) {
        mobileProducts.appendChild(createMobileProductCard(product));
      }

      for (const [label, field, color] of PRICE_FIELDS) {
        const labelCell = createCell(label, "row-label");
        labelCell.firstElementChild.classList.add(color);
        matrix.appendChild(labelCell);
        for (const product of packageProducts) {
          const cell = createCell(priceLabel(product, field), "price-cell");
          cell.firstElementChild.classList.add(color);
          matrix.appendChild(cell);
        }
      }
      return fragment;
    });

  treeElement.replaceChildren(...sections);
  document.querySelector("#uf-chip").textContent = uf;
}

function createCell(content, className) {
  const cell = document.createElement("div");
  cell.className = className;
  const contentElement = document.createElement(className === "row-label" ? "span" : "span");
  contentElement.classList.add(className === "row-label" ? "label-pill" : "price-pill");
  contentElement.textContent = content;
  cell.appendChild(contentElement);
  return cell;
}

function createMobileProductCard(product) {
  const card = document.createElement("article");
  card.className = "mobile-product-card";

  const header = document.createElement("header");
  header.className = "mobile-product-header";
  const image = document.createElement("img");
  image.src = imagePath(product);
  image.alt = product.NomeAbreviado;
  const identity = document.createElement("div");
  identity.className = "mobile-product-identity";
  const name = document.createElement("h3");
  name.textContent = product.NomeAbreviado;
  const code = document.createElement("span");
  code.textContent = `Promax ${product.Promax}`;
  identity.append(name, code);
  header.append(image, identity);

  const prices = document.createElement("dl");
  prices.className = "mobile-prices";
  for (const [label, field, color] of PRICE_FIELDS) {
    const item = document.createElement("div");
    item.className = "mobile-price-item";
    const term = document.createElement("dt");
    term.textContent = label;
    const value = document.createElement("dd");
    value.className = `mobile-price-value ${color}`;
    value.textContent = priceLabel(product, field);
    item.append(term, value);
    prices.appendChild(item);
  }

  card.append(header, prices);
  return card;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function splitSearchTerms(search) {
  return [...new Set(search.split(/[;,]/).map((term) => term.trim().toLowerCase()).filter(Boolean))];
}

function renderResults(products) {
  const table = document.createElement("table");
  table.className = "search-table";
  table.innerHTML = `
    <thead>
      <tr><th>Produto</th><th colspan="5">Preço por UF</th></tr>
      <tr><th></th><th>UF</th><th>TTC Tática</th><th>PP</th><th>TTC Calendário</th><th>CTR L3M</th></tr>
    </thead>
    <tbody></tbody>`;

  const tbody = table.querySelector("tbody");
  const productsByPromaxAndUf = new Map(
    state.data.products.map((product) => [`${product.Promax}:${product.UF}`, product]),
  );
  const mobileResults = document.createElement("div");
  mobileResults.className = "mobile-search-results";
  for (const product of products) {
    const mobileCard = document.createElement("article");
    mobileCard.className = "mobile-product-card mobile-search-card";
    const mobileHeader = document.createElement("header");
    mobileHeader.className = "mobile-product-header";
    const mobileImage = document.createElement("img");
    mobileImage.src = imagePath(product);
    mobileImage.alt = product.NomeAbreviado;
    const mobileIdentity = document.createElement("div");
    mobileIdentity.className = "mobile-product-identity";
    const mobileName = document.createElement("h3");
    mobileName.textContent = product.NomeAbreviado;
    const mobileCode = document.createElement("span");
    mobileCode.textContent = `Promax ${product.Promax}`;
    mobileIdentity.append(mobileName, mobileCode);
    mobileHeader.append(mobileImage, mobileIdentity);
    mobileCard.appendChild(mobileHeader);

    const ufList = document.createElement("div");
    ufList.className = "mobile-uf-list";
    for (const [index, uf] of state.data.ufs.entries()) {
      const row = document.createElement("tr");
      if (index === 0) {
        const productCell = document.createElement("td");
        productCell.rowSpan = state.data.ufs.length;
        productCell.innerHTML = `
          <div class="search-product">
            <img src="${imagePath(product)}" alt="${escapeHtml(product.NomeAbreviado)}">
            <span>${escapeHtml(product.NomeAbreviado)}<br><small>Promax ${product.Promax}</small></span>
          </div>`;
        row.appendChild(productCell);
      }
      const priceRecord = productsByPromaxAndUf.get(`${product.Promax}:${uf}`) ?? null;
      row.insertAdjacentHTML("beforeend", `
        <td class="search-uf">${uf}</td>
        <td>${priceSummary(priceRecord, "TTC")}</td>
        <td>${priceSummary(priceRecord, "PP")}</td>
        <td>${priceSummary(priceRecord, "CAL")}</td>
        <td>${priceSummary(priceRecord, "CTR")}</td>`);
      tbody.appendChild(row);

      const ufSection = document.createElement("section");
      ufSection.className = "mobile-search-uf";
      const ufTitle = document.createElement("h4");
      ufTitle.textContent = uf;
      const prices = document.createElement("dl");
      prices.className = "mobile-prices";
      for (const [label, field, color] of PRICE_FIELDS) {
        const item = document.createElement("div");
        item.className = "mobile-price-item";
        const term = document.createElement("dt");
        term.textContent = label;
        const value = document.createElement("dd");
        value.className = `mobile-price-value ${color}`;
        value.textContent = priceSummary(priceRecord, field);
        item.append(term, value);
        prices.appendChild(item);
      }
      ufSection.append(ufTitle, prices);
      ufList.appendChild(ufSection);
    }
    mobileCard.appendChild(ufList);
    mobileResults.appendChild(mobileCard);
  }
  const results = document.createElement("div");
  results.append(table, mobileResults);
  return results;
}

function renderTree() {
  const ufProducts = state.data.products.filter((product) => product.UF === state.uf);
  const matches = state.search.trim();
  if (matches) {
    const terms = splitSearchTerms(matches);
    const filtered = ufProducts.filter((product) => {
      const searchable = [product.Nome, product.NomeAbreviado, String(product.Promax)].join(" ").toLowerCase();
      return terms.some((term) => searchable.includes(term));
    });
    resultsElement.hidden = false;
    treeElement.innerHTML = "";
    resultsElement.innerHTML = "";
    const header = document.createElement("div");
    header.className = "results-header";
    header.innerHTML = `<h2>${filtered.length} produto(s) encontrado(s)</h2><img class="brand-logo" src="images/logo.png" alt="Logo">`;
    resultsElement.appendChild(header);
    resultsElement.appendChild(renderResults(filtered));
    return;
  }

  treeElement.innerHTML = "";
  resultsElement.hidden = true;
  resultsElement.innerHTML = "";
  buildTreePage(ufProducts, state.uf);
}

async function loadData() {
  setLoading(true);
  clearStatus();
  try {
    const response = await fetch("data.json", { cache: "no-store" });
    if (!response.ok) throw new Error("Não foi possível carregar os dados.");
    state.data = await response.json();
    state.uf = state.data.ufs.includes(state.uf) ? state.uf : state.data.ufs[0];
    fillUfOptions();
    renderTree();
  } catch (error) {
    showStatus(error.message, "error");
  } finally {
    setLoading(false);
  }
}

function fillUfOptions() {
  ufFilter.innerHTML = state.data.ufs.map((uf) => `<option value="${uf}">${uf}</option>`).join("");
  ufFilter.value = state.uf;
}

ufFilter.addEventListener("change", () => {
  state.uf = ufFilter.value;
  renderTree();
});

searchInput.addEventListener("input", () => {
  state.search = searchInput.value;
  renderTree();
});

refreshButton.addEventListener("click", () => {
  loadData();
});

loadData();
