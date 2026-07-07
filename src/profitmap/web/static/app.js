const money = new Intl.NumberFormat("uk-UA", { style: "currency", currency: "UAH" });
let state = {};
let selectedProduct = null;
let productSort = { key: "sku", direction: "asc" };

const fields = [
  ["name", "Название", "text"],
  ["sku", "Артикул", "text"],
  ["category", "Категория", "text"],
  ["product_class", "Класс товара", "text"],
  ["subcategory", "Подкатегория", "text"],
  ["brand", "Бренд", "text"],
  ["stock", "Остаток", "number"],
  ["expected_monthly_sales", "Продажи/мес.", "number"],
  ["purchase_price", "Средняя закупочная", "number"],
  ["sale_price", "Цена продажи", "number"],
  ["logistics", "Логистика", "number"],
  ["marketplace_fee", "Комиссия", "number"],
  ["advertising", "Реклама", "number"],
  ["packaging", "Упаковка", "number"],
  ["taxes", "Налоги", "number"],
  ["other_costs", "Прочие расходы", "number"],
  ["fixed_cost_allocation", "Постоянные расходы", "number"],
  ["supplier_name", "Поставщик", "text"],
  ["supplier_contact", "Контакт", "text"],
  ["supplier_phone", "Телефон", "text"],
  ["supplier_email", "Email", "text"],
  ["supplier_site", "Сайт", "text"],
  ["product_url", "Ссылка на товар", "text"],
  ["lead_time_days", "Срок поставки", "number"],
  ["minimum_order_quantity", "Мин. партия", "number"],
];

document.addEventListener("DOMContentLoaded", async () => {
  bindNavigation();
  bindActions();
  await loadState();
});

function bindNavigation() {
  document.querySelectorAll(".nav").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".nav").forEach((item) => item.classList.remove("active"));
      document.querySelectorAll(".view").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      document.getElementById(button.dataset.view).classList.add("active");
      if (button.dataset.view === "sales") renderSalesPage();
      if (button.dataset.view === "analytics") renderAnalytics();
    });
  });

  document.getElementById("themeToggle").addEventListener("click", () => {
    document.body.classList.toggle("dark");
    document.getElementById("themeToggle").textContent = document.body.classList.contains("dark") ? "Светлая тема" : "Темная тема";
    if (selectedProduct) renderChart(selectedProduct);
  });
}

function bindActions() {
  document.getElementById("search").addEventListener("input", renderProducts);
  document.querySelectorAll(".products-grid th[data-sort]").forEach((header) => {
    header.addEventListener("click", () => sortProducts(header.dataset.sort));
  });
  document.getElementById("targetProfit").addEventListener("change", () => selectedProduct && renderChart(readProductForm()));
  document.getElementById("saveProduct").addEventListener("click", saveProduct);
  document.getElementById("deleteProduct").addEventListener("click", deleteProduct);
  document.getElementById("newProduct").addEventListener("click", createProduct);
  document.getElementById("runAi").addEventListener("click", runAi);
  document.getElementById("allocateExpenses").addEventListener("click", allocateExpenses);
  document.getElementById("expenseForm").addEventListener("submit", addExpense);
  document.getElementById("variableExpenseForm").addEventListener("submit", addVariableExpense);
  document.getElementById("supplyForm").addEventListener("submit", addSupply);
  document.getElementById("saleForm").addEventListener("submit", addSale);
  document.getElementById("quickSaleForm").addEventListener("submit", addQuickSale);
  document.getElementById("quickSaleProduct").addEventListener("change", fillQuickSalePrice);
  document.getElementById("salesSearch").addEventListener("input", renderSalesPage);
  document.getElementById("salesProductFilter").addEventListener("change", renderSalesPage);
  document.querySelector("[name='expense_date']").valueAsDate = new Date();
  document.querySelector("#variableExpenseForm [name='expense_date']").valueAsDate = new Date();
  document.querySelector("[name='supply_date']").valueAsDate = new Date();
  document.querySelector("#saleForm [name='sale_date']").valueAsDate = new Date();
  document.querySelector("#quickSaleForm [name='sale_date']").valueAsDate = new Date();
}

async function loadState(preferredProductId = null) {
  state = await fetchJson("/api/state");
  const targetId = preferredProductId ?? selectedProduct?.id;
  if (targetId && (state.products || []).some((product) => product.id === targetId)) {
    selectedProduct = await fetchJson(`/api/products/${targetId}`);
  } else {
    selectedProduct = state.selectedProduct;
  }
  renderProducts();
  renderSelectedProduct();
  renderSalesPage();
  renderExpenses();
  renderVariableExpenses();
  renderAnalytics();
}

function renderProducts() {
  const query = document.getElementById("search").value.toLowerCase();
  const rows = sortProductRows((state.products || []).filter((product) =>
    `${product.sku} ${product.name} ${product.category} ${product.supplier_name}`.toLowerCase().includes(query),
  ));
  renderProductSortHeaders();
  document.getElementById("productsTable").innerHTML = rows.length ? rows
    .map(
      (product) => `
        <tr class="${selectedProduct && selectedProduct.id === product.id ? "selected" : ""}" data-id="${product.id}">
          <td>${escapeHtml(product.sku)}</td>
          <td>${escapeHtml(product.name)}</td>
          <td>${escapeHtml(product.category || "")}</td>
          <td class="numeric">${product.stock}</td>
          <td class="numeric">${product.supplied_quantity || 0}</td>
          <td class="numeric">${product.sold_quantity || 0}</td>
          <td class="numeric">${money.format(product.purchase_price || 0)}</td>
          <td class="numeric">${money.format(product.sale_price)}</td>
          <td>${escapeHtml(product.supplier_name || "")}</td>
        </tr>`,
    )
    .join("") : `<tr><td colspan="9" class="empty">Товаров пока нет</td></tr>`;

  document.querySelectorAll("#productsTable tr").forEach((row) => {
    row.addEventListener("click", async () => {
      if (!row.dataset.id) return;
      selectedProduct = await fetchJson(`/api/products/${row.dataset.id}`);
      renderProducts();
      renderSelectedProduct();
    });
  });
}

function sortProducts(key) {
  if (productSort.key === key) {
    productSort.direction = productSort.direction === "asc" ? "desc" : "asc";
  } else {
    productSort = { key, direction: "asc" };
  }
  renderProducts();
}

function sortProductRows(rows) {
  const numericKeys = new Set(["stock", "supplied_quantity", "sold_quantity", "purchase_price", "sale_price"]);
  const direction = productSort.direction === "asc" ? 1 : -1;
  return [...rows].sort((left, right) => {
    const leftValue = left[productSort.key] ?? "";
    const rightValue = right[productSort.key] ?? "";
    if (productSort.key === "sku") {
      return compareArticles(leftValue, rightValue) * direction;
    }
    if (numericKeys.has(productSort.key)) {
      return (Number(leftValue || 0) - Number(rightValue || 0)) * direction;
    }
    return String(leftValue).localeCompare(String(rightValue), "ru", { numeric: true, sensitivity: "base" }) * direction;
  });
}

function compareArticles(leftValue, rightValue) {
  const left = parseArticle(leftValue);
  const right = parseArticle(rightValue);
  const prefixCompare = left.prefix.localeCompare(right.prefix, "ru", { sensitivity: "base" });
  if (prefixCompare !== 0) return prefixCompare;
  if (left.number !== null && right.number !== null && left.number !== right.number) {
    return left.number - right.number;
  }
  if (left.number !== null && right.number === null) return -1;
  if (left.number === null && right.number !== null) return 1;
  return left.raw.localeCompare(right.raw, "ru", { numeric: true, sensitivity: "base" });
}

function parseArticle(value) {
  const raw = String(value || "").trim();
  const match = raw.match(/^([^0-9]*)(\d+)?(.*)$/);
  return {
    raw,
    prefix: (match?.[1] || raw).trim().toLowerCase(),
    number: match?.[2] ? Number(match[2]) : null,
  };
}

function renderProductSortHeaders() {
  document.querySelectorAll(".products-grid th[data-sort]").forEach((header) => {
    const active = header.dataset.sort === productSort.key;
    header.classList.toggle("sorted", active);
    header.dataset.direction = active ? productSort.direction : "";
  });
}

function renderSelectedProduct() {
  if (!selectedProduct) {
    document.getElementById("detailTitle").textContent = "Карточка товара";
    document.getElementById("productForm").innerHTML = `<div class="empty-form">Добавьте товар, чтобы рассчитать юнит-экономику и построить график.</div>`;
    document.getElementById("productMetrics").innerHTML = "";
    document.getElementById("pricing").innerHTML = "";
    document.getElementById("supplySummary").textContent = "Добавьте товар, чтобы учитывать поставки.";
    document.getElementById("suppliesTable").innerHTML = `<tr><td colspan="7" class="empty">Поставок пока нет</td></tr>`;
    document.getElementById("salesSummary").textContent = "Добавьте товар, чтобы учитывать продажи.";
    document.getElementById("salesTable").innerHTML = `<tr><td colspan="7" class="empty">Продаж пока нет</td></tr>`;
    Plotly.purge("breakEvenChart");
    return;
  }
  document.getElementById("detailTitle").textContent = selectedProduct.name;
  const form = document.getElementById("productForm");
  form.innerHTML = fields
    .map(([name, label, type]) => {
      const value = selectedProduct[name] ?? "";
      const step = type === "number" ? ' step="0.01"' : "";
      const readonly = name === "purchase_price" ? " readonly" : "";
      return `<div class="field"><label>${label}</label><input name="${name}" type="${type}"${step}${readonly} value="${escapeAttribute(value)}" /></div>`;
    })
    .join("");
  form.querySelectorAll("input").forEach((input) => input.addEventListener("input", handleLiveRecalculate));
  renderProductEconomics(selectedProduct);
  renderSupplies();
  renderSales();
  renderChart(selectedProduct);
}

function handleLiveRecalculate() {
  const product = readProductForm();
  renderProductEconomics(product);
  renderChart(product);
}

function readProductForm() {
  const data = { ...selectedProduct };
  new FormData(document.getElementById("productForm")).forEach((value, key) => {
    const field = fields.find(([name]) => name === key);
    data[key] = field && field[2] === "number" ? Number(value || 0) : value;
  });
  data.economics = calculateEconomics(data, Number(document.getElementById("targetProfit").value));
  return data;
}

function calculateEconomics(product, targetProfit) {
  const variableCost =
    Number(product.purchase_price) +
    Number(product.logistics) +
    Number(product.marketplace_fee) +
    Number(product.advertising) +
    Number(product.packaging) +
    Number(product.taxes) +
    Number(product.other_costs);
  const expectedSales = Math.max(Number(product.expected_monthly_sales || 1), 1);
  const fullCost = variableCost + Number(product.fixed_cost_allocation || 0) / expectedSales;
  const gross = Number(product.sale_price) - variableCost;
  const net = Number(product.sale_price) - fullCost;
  const contribution = Number(product.sale_price) - variableCost;
  return {
    variable_cost: variableCost,
    full_cost_per_unit: fullCost,
    gross_profit: gross,
    net_profit_per_unit: net,
    margin_percent: product.sale_price ? (net / Number(product.sale_price)) * 100 : 0,
    markup_percent: fullCost ? (net / fullCost) * 100 : 0,
    roi_percent: variableCost ? (net / variableCost) * 100 : 0,
    break_even_units: contribution > 0 ? Math.ceil(Number(product.fixed_cost_allocation || 0) / contribution) : null,
    target_units: contribution > 0 ? Math.ceil((Number(product.fixed_cost_allocation || 0) + targetProfit) / contribution) : null,
    minimum_price: fullCost,
    recommended_price: fullCost * 1.25,
    aggressive_price: Math.max(variableCost * 1.08, fullCost * 1.08),
    premium_price: fullCost * 1.65,
  };
}

function renderProductEconomics(product) {
  const economics = product.economics || calculateEconomics(product, 1000);
  document.getElementById("productMetrics").innerHTML = [
    ["Полная себестоимость", money.format(economics.full_cost_per_unit)],
    ["Валовая прибыль", money.format(economics.gross_profit)],
    ["Чистая прибыль", money.format(economics.net_profit_per_unit)],
    ["Маржа", `${Number(economics.margin_percent).toFixed(1)}%`],
    ["Наценка", `${Number(economics.markup_percent).toFixed(1)}%`],
    ["ROI", `${Number(economics.roi_percent).toFixed(1)}%`],
    ["Безубыточность", `${economics.break_even_units || 0} шт.`],
    ["Целевой объем", `${economics.target_units || 0} шт.`],
  ]
    .map(metric)
    .join("");

  document.getElementById("pricing").innerHTML = [
    ["Минимальная цена", money.format(economics.minimum_price)],
    ["Рекомендуемая", money.format(economics.recommended_price)],
    ["Агрессивная", money.format(economics.aggressive_price)],
    ["Премиальная", money.format(economics.premium_price)],
  ]
    .map(metric)
    .join("");
}

function renderSupplies() {
  if (!selectedProduct) return;
  const summary = selectedProduct.supply_summary || {};
  document.getElementById("supplySummary").textContent =
    `Всего поставлено: ${summary.total_quantity || 0} шт. · Средняя закупка: ${money.format(summary.average_purchase_price || selectedProduct.purchase_price || 0)} · Рекомендуемая цена: ${money.format(summary.recommended_price || 0)}`;

  const supplies = selectedProduct.supplies || [];
  document.getElementById("suppliesTable").innerHTML = supplies.length ? supplies
    .map(
      (supply) => `
        <tr>
          <td>${supply.supply_date}</td>
          <td class="numeric">${supply.quantity}</td>
          <td class="numeric">${money.format(supply.unit_purchase_price)}</td>
          <td class="numeric">${money.format(supply.total_cost)}</td>
          <td>${escapeHtml(supply.supplier_name || "")}</td>
          <td>${escapeHtml(supply.comment || "")}</td>
          <td class="action-cell"><button class="danger icon-button" data-supply-id="${supply.id}" title="Удалить поставку">Удалить</button></td>
        </tr>`,
    )
    .join("") : `<tr><td colspan="7" class="empty">Поставок пока нет</td></tr>`;

  document.querySelectorAll("[data-supply-id]").forEach((button) => {
    button.addEventListener("click", deleteSupply);
  });
}

function renderSales() {
  if (!selectedProduct) return;
  const summary = selectedProduct.sales_summary || {};
  const purchaseTotal = Number(selectedProduct.purchase_price || 0) * Number(summary.total_quantity || 0);
  const profitTotal = Number(summary.total_revenue || 0) - purchaseTotal;
  document.getElementById("salesSummary").textContent =
    `Продано: ${summary.total_quantity || 0} шт. · Закупка: ${money.format(purchaseTotal)} · Выручка: ${money.format(summary.total_revenue || 0)} · Разница: ${money.format(profitTotal)}`;

  const sales = selectedProduct.sales || [];
  document.getElementById("salesTable").innerHTML = sales.length ? sales
    .map(
      (sale) => `
        <tr>
          <td>${sale.sale_date}</td>
          <td class="numeric">${sale.quantity}</td>
          <td class="numeric">${money.format(sale.unit_price)}</td>
          <td class="numeric">${money.format(sale.purchase_total || 0)}</td>
          <td class="numeric">${money.format(sale.revenue)}</td>
          <td class="numeric ${Number(sale.profit || 0) >= 0 ? "positive" : "negative"}">${money.format(sale.profit || 0)}</td>
          <td class="numeric">${Number(sale.discount_percent || 0).toFixed(1)}%</td>
          <td>${escapeHtml(sale.comment || "")}</td>
          <td class="action-cell"><button class="danger icon-button" data-sale-id="${sale.id}" title="Удалить продажу">Удалить</button></td>
        </tr>`,
    )
    .join("") : `<tr><td colspan="9" class="empty">Продаж пока нет</td></tr>`;

  document.querySelectorAll("[data-sale-id]").forEach((button) => {
    button.addEventListener("click", deleteSale);
  });
}

function renderSalesPage() {
  const products = state.products || [];
  const sales = state.sales || [];
  const quickProduct = document.getElementById("quickSaleProduct");
  const productFilter = document.getElementById("salesProductFilter");
  const previousQuickProduct = quickProduct.value || selectedProduct?.id || products[0]?.id || "";
  const previousFilter = productFilter.value;

  quickProduct.innerHTML = products.length
    ? products
      .map((product) => `<option value="${product.id}" data-price="${product.sale_price}">${escapeHtml(product.name)} · ${escapeHtml(product.sku)}</option>`)
      .join("")
    : `<option value="">Добавьте товар</option>`;
  quickProduct.value = products.some((product) => String(product.id) === String(previousQuickProduct))
    ? String(previousQuickProduct)
    : String(products[0]?.id || "");

  productFilter.innerHTML = `<option value="">Все товары</option>` + products
    .map((product) => `<option value="${product.id}">${escapeHtml(product.name)} · ${escapeHtml(product.sku)}</option>`)
    .join("");
  productFilter.value = products.some((product) => String(product.id) === String(previousFilter)) ? previousFilter : "";

  const priceInput = document.querySelector("#quickSaleForm [name='unit_price']");
  if (!priceInput.value) fillQuickSalePrice();

  const query = document.getElementById("salesSearch").value.trim().toLowerCase();
  const filterProductId = productFilter.value;
  const filteredSales = sales.filter((sale) => {
    const matchesProduct = !filterProductId || String(sale.product_id) === String(filterProductId);
    const haystack = `${sale.sale_date} ${sale.product_name} ${sale.product_sku} ${sale.unit_price} ${sale.comment}`.toLowerCase();
    return matchesProduct && (!query || haystack.includes(query));
  });

  const totalQuantity = filteredSales.reduce((sum, sale) => sum + Number(sale.quantity || 0), 0);
  const totalRevenue = filteredSales.reduce((sum, sale) => sum + Number(sale.revenue || 0), 0);
  const totalPurchase = filteredSales.reduce((sum, sale) => sum + Number(sale.purchase_total || 0), 0);
  const totalProfit = filteredSales.reduce((sum, sale) => sum + Number(sale.profit || 0), 0);
  document.getElementById("salesPageSummary").innerHTML = [
    ["Продаж", filteredSales.length],
    ["Количество", `${totalQuantity} шт.`],
    ["Закупка", money.format(totalPurchase)],
    ["Выручка", money.format(totalRevenue)],
    ["Разница", money.format(totalProfit)],
  ].map(metric).join("");

  document.getElementById("salesPageTable").innerHTML = filteredSales.length ? filteredSales
    .map(
      (sale) => `
        <tr>
          <td>${sale.sale_date}</td>
          <td>${escapeHtml(sale.product_name)}</td>
          <td>${escapeHtml(sale.product_sku || "")}</td>
          <td class="numeric">${sale.quantity}</td>
          <td class="numeric">${money.format(sale.purchase_total || 0)}</td>
          <td class="numeric">${money.format(sale.unit_price)}</td>
          <td class="numeric">${money.format(sale.revenue)}</td>
          <td class="numeric ${Number(sale.profit || 0) >= 0 ? "positive" : "negative"}">${money.format(sale.profit || 0)}</td>
          <td>${escapeHtml(sale.comment || "")}</td>
          <td class="action-cell"><button class="danger icon-button" data-global-sale-id="${sale.id}" title="Удалить продажу">Удалить</button></td>
        </tr>`,
    )
    .join("") : `<tr><td colspan="10" class="empty">Продаж пока нет</td></tr>`;

  document.querySelectorAll("[data-global-sale-id]").forEach((button) => {
    button.addEventListener("click", deleteGlobalSale);
  });
}

function fillQuickSalePrice() {
  const select = document.getElementById("quickSaleProduct");
  const option = select.selectedOptions[0];
  const priceInput = document.querySelector("#quickSaleForm [name='unit_price']");
  priceInput.value = option?.dataset.price || "";
}

function renderChart(product) {
  const economics = product.economics || calculateEconomics(product, Number(document.getElementById("targetProfit").value));
  const salePrice = Number(product.sale_price || 0);
  const fixed = Number(product.fixed_cost_allocation || 0);
  const variable = Number(economics.variable_cost || 0);
  const maxUnits = Math.max(100, Math.ceil((economics.target_units || economics.break_even_units || 100) * 1.35));
  const x = Array.from({ length: 160 }, (_, index) => (index / 159) * maxUnits);
  const revenue = x.map((units) => salePrice * units);
  const costs = x.map((units) => variable * units + fixed);
  const fixedLine = x.map(() => fixed);
  const dark = document.body.classList.contains("dark");

  const traces = [
    { x, y: revenue, mode: "lines", name: "Валовые поступления", line: { color: dark ? "#f9fafb" : "#111827", width: 4 } },
    { x, y: costs, mode: "lines", name: "Валовые издержки", line: { color: "#2563eb", width: 4 } },
    { x, y: fixedLine, mode: "lines", name: "Постоянные издержки", line: { color: "#8b5cf6", width: 3 } },
  ];
  if (economics.break_even_units) {
    traces.push({
      x: [economics.break_even_units],
      y: [salePrice * economics.break_even_units],
      mode: "markers+text",
      name: "Точка безубыточности",
      text: [`${economics.break_even_units} шт.`],
      textposition: "top center",
      marker: { color: "#ef4444", size: 12 },
    });
  }
  if (economics.target_units) {
    traces.push({
      x: [economics.target_units],
      y: [salePrice * economics.target_units],
      mode: "markers+text",
      name: "Целевая прибыль",
      text: [`${economics.target_units} шт.`],
      textposition: "bottom center",
      marker: { color: "#22c55e", size: 12 },
    });
  }

  Plotly.react("breakEvenChart", traces, {
    autosize: true,
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { color: dark ? "#e5e7eb" : "#111827" },
    margin: { t: 24, r: 22, b: 128, l: 68 },
    xaxis: {
      title: { text: "Объем продаж, шт.", standoff: 32 },
      automargin: true,
      gridcolor: dark ? "#263142" : "#e5e7eb",
      zerolinecolor: dark ? "#3b4558" : "#d1d5db",
    },
    yaxis: {
      title: { text: "Деньги, грн", standoff: 16 },
      automargin: true,
      gridcolor: dark ? "#263142" : "#e5e7eb",
      zerolinecolor: dark ? "#3b4558" : "#d1d5db",
    },
    legend: {
      orientation: "h",
      x: 0,
      y: -0.28,
      xanchor: "left",
      yanchor: "top",
      itemwidth: 30,
    },
  }, { responsive: true, displayModeBar: false });
}

async function saveProduct() {
  if (!selectedProduct) return;
  const payload = readProductForm();
  selectedProduct = await fetchJson(`/api/products/${selectedProduct.id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  await loadState(selectedProduct.id);
}

async function deleteProduct() {
  if (!selectedProduct) return;
  const confirmed = window.confirm(`Удалить товар "${selectedProduct.name}"? История продаж этого товара тоже будет удалена.`);
  if (!confirmed) return;
  await fetchJson(`/api/products/${selectedProduct.id}`, { method: "DELETE" });
  selectedProduct = null;
  await loadState();
}

async function createProduct() {
  selectedProduct = await fetchJson("/api/products", {
    method: "POST",
    body: JSON.stringify({ name: "Новый товар", sku: "", category: "Без категории", expected_monthly_sales: 100 }),
  });
  await loadState(selectedProduct.id);
}

async function addSupply(event) {
  event.preventDefault();
  if (!selectedProduct) return;
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.quantity = Number(payload.quantity || 0);
  payload.unit_purchase_price = Number(payload.unit_purchase_price || 0);
  selectedProduct = await fetchJson(`/api/products/${selectedProduct.id}/supplies`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  form.reset();
  form.querySelector("[name='supply_date']").valueAsDate = new Date();
  await loadState(selectedProduct.id);
}

async function deleteSupply(event) {
  if (!selectedProduct) return;
  const supplyId = event.currentTarget.dataset.supplyId;
  const confirmed = window.confirm("Удалить эту поставку? Средняя закупочная цена и остаток товара будут пересчитаны.");
  if (!confirmed) return;
  selectedProduct = await fetchJson(`/api/products/${selectedProduct.id}/supplies/${supplyId}`, { method: "DELETE" });
  await loadState(selectedProduct.id);
}

async function addSale(event) {
  event.preventDefault();
  if (!selectedProduct) return;
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.quantity = Number(payload.quantity || 0);
  payload.unit_price = Number(payload.unit_price || 0);
  selectedProduct = await fetchJson(`/api/products/${selectedProduct.id}/sales`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  form.reset();
  form.querySelector("[name='sale_date']").valueAsDate = new Date();
  await loadState(selectedProduct.id);
}

async function addQuickSale(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.product_id = Number(payload.product_id || 0);
  payload.quantity = Number(payload.quantity || 0);
  payload.unit_price = Number(payload.unit_price || 0);
  await fetchJson("/api/sales", {
    method: "POST",
    body: JSON.stringify(payload),
  });

  const productId = payload.product_id;
  form.reset();
  form.querySelector("[name='sale_date']").valueAsDate = new Date();
  form.querySelector("[name='quantity']").value = 1;
  document.getElementById("quickSaleProduct").value = String(productId);
  fillQuickSalePrice();
  await loadState(selectedProduct?.id);
}

async function deleteSale(event) {
  if (!selectedProduct) return;
  const saleId = event.currentTarget.dataset.saleId;
  const confirmed = window.confirm("Удалить эту продажу?");
  if (!confirmed) return;
  selectedProduct = await fetchJson(`/api/products/${selectedProduct.id}/sales/${saleId}`, { method: "DELETE" });
  await loadState(selectedProduct.id);
}

async function deleteGlobalSale(event) {
  const saleId = event.currentTarget.dataset.globalSaleId;
  const confirmed = window.confirm("Удалить эту продажу из журнала?");
  if (!confirmed) return;
  await fetchJson(`/api/sales/${saleId}`, { method: "DELETE" });
  await loadState(selectedProduct?.id);
}

function renderAnalytics() {
  const analytics = state.analytics || {};
  document.getElementById("analyticsMetrics").innerHTML = [
    ["Выручка", money.format(analytics.total_revenue || 0)],
    ["Вложено", money.format(analytics.total_invested || 0)],
    ["Прибыль", money.format(analytics.total_profit || 0)],
    ["Непостоянные расходы", money.format(analytics.total_variable_expenses || 0)],
    ["Cash Flow", money.format(analytics.cash_flow || 0)],
    ["Маржа", `${Number(analytics.margin_percent || 0).toFixed(1)}%`],
    ["Топ товаров", analytics.profitable_count || 0],
    ["Убыточные", analytics.loss_count || 0],
    ["ABC-анализ", "A/B/C"],
    ["Pareto 80/20", "активен"],
  ]
    .map(metric)
    .join("");

  document.getElementById("coefficientsTable").innerHTML = (analytics.coefficients || [])
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.name)}</td>
          <td>${escapeHtml(row.formula)}</td>
          <td>${escapeHtml(row.calculation)}</td>
          <td class="numeric">${Number(row.percent).toFixed(1)}%</td>
        </tr>`,
    )
    .join("");

  document.getElementById("analyticsTable").innerHTML = (analytics.rows || [])
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.product)}</td>
          <td>${escapeHtml(row.sku || "")}</td>
          <td class="numeric">${money.format(row.invested || 0)}</td>
          <td class="numeric">${money.format(row.revenue)}</td>
          <td class="numeric ${row.profit >= 0 ? "positive" : "negative"}">${money.format(row.profit)}</td>
          <td>${row.abc}</td>
          <td class="numeric">${Number(row.forecast_30_days).toFixed(0)} шт.</td>
        </tr>`,
    )
    .join("");

  document.getElementById("monthlyStatsTable").innerHTML = (state.monthly_stats || [])
    .map(
      (row) => `
        <tr>
          <td>${row.month}</td>
          <td class="numeric">${row.sales_count}</td>
          <td class="numeric">${row.quantity}</td>
          <td class="numeric">${money.format(row.revenue)}</td>
          <td class="numeric">${money.format(row.purchase_cost)}</td>
          <td class="numeric ${row.gross_profit >= 0 ? "positive" : "negative"}">${money.format(row.gross_profit)}</td>
          <td class="numeric">${money.format(row.variable_expenses)}</td>
          <td class="numeric">${money.format(row.fixed_expenses)}</td>
          <td class="numeric ${row.net_profit >= 0 ? "positive" : "negative"}">${money.format(row.net_profit)}</td>
        </tr>`,
    )
    .join("") || `<tr><td colspan="9" class="empty">Месячной статистики пока нет</td></tr>`;
}

function renderExpenses() {
  const expenses = state.expenses || [];
  document.getElementById("expensesTable").innerHTML = expenses.length ? expenses
    .map(
      (expense) => `
        <tr data-id="${expense.id}">
          <td>${expense.expense_date}</td>
          <td>${escapeHtml(expense.category)}</td>
          <td class="numeric">${money.format(expense.amount)}</td>
          <td>${escapeHtml(expense.reason || "")}</td>
          <td>${escapeHtml(expense.comment || "")}</td>
          <td class="action-cell"><button class="danger icon-button" data-expense-id="${expense.id}" title="Удалить расход">Удалить</button></td>
        </tr>`,
    )
    .join("") : `<tr><td colspan="6" class="empty">Расходов пока нет</td></tr>`;

  document.querySelectorAll("[data-expense-id]").forEach((button) => {
    button.addEventListener("click", deleteExpense);
  });
}

async function addExpense(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.amount = Number(payload.amount || 0);
  await fetchJson("/api/expenses", { method: "POST", body: JSON.stringify(payload) });
  form.reset();
  form.querySelector("[name='expense_date']").valueAsDate = new Date();
  await loadState();
}

async function deleteExpense(event) {
  const expenseId = event.currentTarget.dataset.expenseId;
  const confirmed = window.confirm("Удалить этот расход?");
  if (!confirmed) return;
  await fetchJson(`/api/expenses/${expenseId}`, { method: "DELETE" });
  await loadState();
}

function renderVariableExpenses() {
  const expenses = state.variable_expenses || [];
  document.getElementById("variableExpensesTable").innerHTML = expenses.length ? expenses
    .map(
      (expense) => `
        <tr data-id="${expense.id}">
          <td>${expense.expense_date}</td>
          <td>${escapeHtml(expense.category)}</td>
          <td class="numeric">${money.format(expense.amount)}</td>
          <td>${escapeHtml(expense.reason || "")}</td>
          <td>${escapeHtml(expense.comment || "")}</td>
          <td class="action-cell"><button class="danger icon-button" data-variable-expense-id="${expense.id}" title="Удалить расход">Удалить</button></td>
        </tr>`,
    )
    .join("") : `<tr><td colspan="6" class="empty">Непостоянных расходов пока нет</td></tr>`;

  document.querySelectorAll("[data-variable-expense-id]").forEach((button) => {
    button.addEventListener("click", deleteVariableExpense);
  });
}

async function addVariableExpense(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.amount = Number(payload.amount || 0);
  await fetchJson("/api/variable-expenses", { method: "POST", body: JSON.stringify(payload) });
  form.reset();
  form.querySelector("[name='expense_date']").valueAsDate = new Date();
  await loadState();
}

async function deleteVariableExpense(event) {
  const expenseId = event.currentTarget.dataset.variableExpenseId;
  const confirmed = window.confirm("Удалить этот непостоянный расход?");
  if (!confirmed) return;
  await fetchJson(`/api/variable-expenses/${expenseId}`, { method: "DELETE" });
  await loadState();
}

async function allocateExpenses() {
  const method = document.getElementById("allocationMethod").value;
  await fetchJson("/api/allocate-expenses", { method: "POST", body: JSON.stringify({ method }) });
  await loadState();
}

async function runAi() {
  const output = document.getElementById("aiOutput");
  output.textContent = "Анализирую бизнес...";
  const result = await fetchJson("/api/analyze", { method: "POST" });
  output.textContent = result.text;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function metric([label, value]) {
  return `<div class="metric"><span>${label}</span><strong>${value}</strong></div>`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}

function escapeAttribute(value) {
  return escapeHtml(value).replace(/"/g, "&quot;");
}
