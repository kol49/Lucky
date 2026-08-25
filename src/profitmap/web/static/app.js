const money = new Intl.NumberFormat("uk-UA", { style: "currency", currency: "UAH" });
let state = {};
let selectedProduct = null;
let productSort = { key: "sku", direction: "asc" };
let editingKitId = null;
let editingSaleId = null;

const salesSortDefaults = {
  date: "desc",
  markup: "desc",
  price: "desc",
  product: "asc",
  profit: "desc",
  purchase: "desc",
  quantity: "desc",
  sku: "asc",
};

const fields = [
  ["name", "Название", "text"],
  ["sku", "Артикул", "text"],
  ["category", "Категория", "text"],
  ["stock", "Остаток", "number"],
  ["purchase_price", "Входная цена", "number"],
  ["sale_price", "Цена продажи", "number"],
  ["supplier_name", "Поставщик", "text"],
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
  });
}

function bindActions() {
  document.getElementById("search").addEventListener("input", renderProducts);
  document.querySelectorAll(".products-grid th[data-sort]").forEach((header) => {
    header.addEventListener("click", () => sortProducts(header.dataset.sort));
  });
  document.querySelectorAll("[data-sales-sort]").forEach((header) => {
    header.addEventListener("click", () => sortSalesBy(header.dataset.salesSort));
  });
  document.getElementById("saveProduct").addEventListener("click", saveProduct);
  document.getElementById("deleteProduct").addEventListener("click", deleteProduct);
  document.getElementById("newProduct").addEventListener("click", createProduct);
  document.getElementById("runAi").addEventListener("click", runAi);
  document.getElementById("allocateExpenses").addEventListener("click", allocateExpenses);
  document.getElementById("exportMonthReport").addEventListener("click", () => downloadMonthReport(document.getElementById("exportMonth").value));
  document.getElementById("expenseForm").addEventListener("submit", addExpense);
  document.getElementById("variableExpenseForm").addEventListener("submit", addVariableExpense);
  document.getElementById("supplyForm").addEventListener("submit", addSupply);
  document.getElementById("kitForm").addEventListener("submit", addKit);
  document.getElementById("cancelKitEdit").addEventListener("click", cancelKitEdit);
  document.getElementById("saleForm").addEventListener("submit", addSale);
  document.getElementById("quickSaleForm").addEventListener("submit", addQuickSale);
  document.getElementById("quickSaleProduct").addEventListener("change", fillQuickSalePrice);
  document.getElementById("cancelSaleEdit").addEventListener("click", cancelSaleEdit);
  document.getElementById("salesSearch").addEventListener("input", renderSalesPage);
  document.getElementById("salesProductFilter").addEventListener("change", renderSalesPage);
  document.getElementById("salesDateFrom").addEventListener("change", () => {
    document.getElementById("salesPeriodFilter").value = "";
    renderSalesPage();
  });
  document.getElementById("salesDateTo").addEventListener("change", () => {
    document.getElementById("salesPeriodFilter").value = "";
    renderSalesPage();
  });
  document.getElementById("salesPeriodFilter").addEventListener("change", applySalesPeriodFilter);
  document.getElementById("salesSort").addEventListener("change", renderSalesPage);
  document.getElementById("salesResetFilters").addEventListener("click", resetSalesFilters);
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
  const rows = sortProductRows((state.products || []).filter((product) => {
    const haystack = `${product.sku} ${product.name} ${product.category} ${product.supplier_name}`.toLowerCase();
    return !query || haystack.includes(query);
  }));
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
    document.getElementById("productForm").innerHTML = `<div class="empty-form">Добавьте товар, чтобы вести остатки, поставки и продажи.</div>`;
    document.getElementById("supplySummary").textContent = "Добавьте товар, чтобы учитывать поставки.";
    document.getElementById("suppliesTable").innerHTML = `<tr><td colspan="7" class="empty">Поставок пока нет</td></tr>`;
    document.getElementById("kitSummary").textContent = "Добавьте товар, чтобы создавать комплекты.";
    document.getElementById("kitsTable").innerHTML = `<tr><td colspan="6" class="empty">Комплектов пока нет</td></tr>`;
    document.getElementById("salesSummary").textContent = "Добавьте товар, чтобы учитывать продажи.";
    document.getElementById("salesTable").innerHTML = `<tr><td colspan="10" class="empty">Продаж пока нет</td></tr>`;
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
  renderSupplies();
  renderKits();
  renderSales();
}

function readProductForm() {
  const data = { ...selectedProduct };
  new FormData(document.getElementById("productForm")).forEach((value, key) => {
    const field = fields.find(([name]) => name === key);
    data[key] = field && field[2] === "number" ? Number(value || 0) : value;
  });
  return data;
}

function renderSupplies() {
  if (!selectedProduct) return;
  const summary = selectedProduct.supply_summary || {};
  document.getElementById("supplySummary").textContent =
    `Всего поставлено: ${summary.total_quantity || 0} шт. · Остаток: ${summary.remaining_quantity || 0} шт. · Средняя закупка остатка: ${money.format(summary.average_purchase_price || selectedProduct.purchase_price || 0)} · Рекомендуемая цена: ${money.format(summary.recommended_price || 0)}`;

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

function renderKits() {
  if (!selectedProduct) return;
  const kits = selectedProduct.kits || [];
  const secondProductSelect = document.getElementById("kitSecondProduct");
  secondProductSelect.innerHTML = `<option value="">Без второго товара</option>` + (state.products || [])
    .filter((product) => Number(product.id) !== Number(selectedProduct.id))
    .map((product) => `<option value="${product.id}">${escapeHtml(product.name)} · ${escapeHtml(product.sku)}</option>`)
    .join("");
  document.getElementById("kitSummary").textContent =
    kits.length
      ? `Комплектов: ${kits.length}. Остаток основного товара: ${selectedProduct.stock || 0} шт.`
      : "Создайте комплект под SKU вариации WooCommerce, чтобы при продаже списывался основной товар.";

  document.getElementById("kitsTable").innerHTML = kits.length ? kits
    .map(
      (kit) => `
        <tr>
          <td>${escapeHtml(kit.kit_sku)}</td>
          <td>${escapeHtml(kit.kit_name || "")}</td>
          <td>${escapeHtml(selectedProduct.sku)} · ${kit.units_per_kit} шт.</td>
          <td>${kit.secondary_product_id ? `${escapeHtml(kit.secondary_product_sku)} · ${kit.secondary_units_per_kit} шт.` : "—"}</td>
          <td class="numeric">${kit.available_kits} компл.</td>
          <td class="action-cell">
            <button class="icon-button" data-edit-kit-id="${kit.id}" title="Редактировать комплект">Изменить</button>
            <button class="danger icon-button" data-kit-id="${kit.id}" title="Удалить комплект">Удалить</button>
          </td>
        </tr>`,
    )
    .join("") : `<tr><td colspan="6" class="empty">Комплектов пока нет</td></tr>`;

  document.querySelectorAll("[data-edit-kit-id]").forEach((button) => {
    button.addEventListener("click", startKitEdit);
  });
  document.querySelectorAll("[data-kit-id]").forEach((button) => {
    button.addEventListener("click", deleteKit);
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
          <td>${escapeHtml(sale.sale_channel_label || "")}</td>
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
    .join("") : `<tr><td colspan="10" class="empty">Продаж пока нет</td></tr>`;

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
  const dateFrom = document.getElementById("salesDateFrom").value;
  const dateTo = document.getElementById("salesDateTo").value;
  const sortMode = document.getElementById("salesSort").value;
  updateSalesSortHeaders(sortMode);
  const filteredSales = sales.filter((sale) => {
    const matchesProduct = !filterProductId || String(sale.product_id) === String(filterProductId);
    const haystack = [
      sale.product_name,
      sale.product_sku,
      sale.sale_channel_label,
      sale.sale_channel,
      sale.comment,
      sale.unit_price,
      sale.purchase_total,
      sale.profit,
      sale.markup_percent,
    ].join(" ").toLowerCase();
    const matchesDateFrom = !dateFrom || sale.sale_date >= dateFrom;
    const matchesDateTo = !dateTo || sale.sale_date <= dateTo;
    return matchesProduct && matchesDateFrom && matchesDateTo && (!query || haystack.includes(query));
  }).sort((left, right) => {
    return compareSales(left, right, sortMode);
  });

  const totalQuantity = filteredSales.reduce((sum, sale) => sum + Number(sale.quantity || 0), 0);
  const totalRevenue = filteredSales.reduce((sum, sale) => sum + Number(sale.revenue || 0), 0);
  const totalPurchase = filteredSales.reduce((sum, sale) => sum + Number(sale.purchase_total || 0), 0);
  const totalProfit = filteredSales.reduce((sum, sale) => sum + Number(sale.profit || 0), 0);
  const totalMarkup = totalPurchase ? (totalProfit / totalPurchase) * 100 : 0;
  document.getElementById("salesPageSummary").innerHTML = [
    ["Продаж", filteredSales.length],
    ["Количество", `${totalQuantity} шт.`],
    ["Закупка", money.format(totalPurchase)],
    ["Выручка", money.format(totalRevenue)],
    ["Разница", money.format(totalProfit)],
    ["Наценка", `${totalMarkup.toFixed(1)}%`],
  ].map(metric).join("");

  document.getElementById("salesPageTable").innerHTML = filteredSales.length ? filteredSales
    .map(
      (sale) => `
        <tr>
          <td>${sale.sale_date}</td>
          <td>${escapeHtml(sale.sale_channel_label || "")}</td>
          <td>${escapeHtml(sale.product_name)}</td>
          <td>${escapeHtml(sale.product_sku || "")}</td>
          <td class="numeric">${sale.quantity}</td>
          <td class="numeric">${money.format(sale.purchase_total || 0)}</td>
          <td class="numeric">${money.format(sale.unit_price)}</td>
          <td class="numeric ${Number(sale.profit || 0) >= 0 ? "positive" : "negative"}">${money.format(sale.profit || 0)}</td>
          <td class="numeric ${Number(sale.markup_percent || 0) >= 0 ? "positive" : "negative"}">${Number(sale.markup_percent || 0).toFixed(1)}%</td>
          <td>${escapeHtml(sale.comment || "")}</td>
          <td class="action-cell">
            <button class="icon-button" data-edit-sale-id="${sale.id}" title="Редактировать продажу">Изменить</button>
            <button class="danger icon-button" data-global-sale-id="${sale.id}" title="Удалить продажу">Удалить</button>
          </td>
        </tr>`,
    )
    .join("") : `<tr><td colspan="11" class="empty">Продаж пока нет</td></tr>`;

  document.querySelectorAll("[data-edit-sale-id]").forEach((button) => {
    button.addEventListener("click", startSaleEdit);
  });
  document.querySelectorAll("[data-global-sale-id]").forEach((button) => {
    button.addEventListener("click", deleteGlobalSale);
  });
}

function sortSalesBy(key) {
  const select = document.getElementById("salesSort");
  const [currentKey, currentDirection] = String(select.value || "date_desc").split("_");
  const defaultDirection = salesSortDefaults[key] || "desc";
  const nextDirection = currentKey === key
    ? (currentDirection === "asc" ? "desc" : "asc")
    : defaultDirection;
  select.value = `${key}_${nextDirection}`;
  renderSalesPage();
}

function compareSales(left, right, sortMode) {
  const [key, direction = "desc"] = String(sortMode || "date_desc").split("_");
  const factor = direction === "asc" ? 1 : -1;
  const byNewest = right.sale_date.localeCompare(left.sale_date) || Number(right.id || 0) - Number(left.id || 0);

  if (key === "date") return factor * left.sale_date.localeCompare(right.sale_date) || Number(right.id || 0) - Number(left.id || 0);
  if (key === "product") return factor * String(left.product_name || "").localeCompare(String(right.product_name || ""), "uk") || byNewest;
  if (key === "sku") return factor * String(left.product_sku || "").localeCompare(String(right.product_sku || ""), "uk", { numeric: true }) || byNewest;
  if (key === "quantity") return factor * (Number(left.quantity || 0) - Number(right.quantity || 0)) || byNewest;
  if (key === "purchase") return factor * (Number(left.purchase_total || 0) - Number(right.purchase_total || 0)) || byNewest;
  if (key === "price") return factor * (Number(left.unit_price || 0) - Number(right.unit_price || 0)) || byNewest;
  if (key === "profit") return factor * (Number(left.profit || 0) - Number(right.profit || 0)) || byNewest;
  if (key === "markup") return factor * (Number(left.markup_percent || 0) - Number(right.markup_percent || 0)) || byNewest;
  return byNewest;
}

function updateSalesSortHeaders(sortMode) {
  const [key, direction = "desc"] = String(sortMode || "date_desc").split("_");
  document.querySelectorAll("[data-sales-sort]").forEach((header) => {
    const isActive = header.dataset.salesSort === key;
    header.classList.toggle("active", isActive);
    header.dataset.direction = isActive ? direction : "";
    header.setAttribute("aria-sort", isActive ? (direction === "asc" ? "ascending" : "descending") : "none");
  });
}

function fillQuickSalePrice() {
  const select = document.getElementById("quickSaleProduct");
  const option = select.selectedOptions[0];
  const priceInput = document.querySelector("#quickSaleForm [name='unit_price']");
  priceInput.value = option?.dataset.price || "";
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

async function addKit(event) {
  event.preventDefault();
  if (!selectedProduct) return;
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.units_per_kit = Number(payload.units_per_kit || 0);
  payload.secondary_product_id = payload.secondary_product_id ? Number(payload.secondary_product_id) : null;
  payload.secondary_units_per_kit = Number(payload.secondary_units_per_kit || 0);
  const url = editingKitId
    ? `/api/products/${selectedProduct.id}/kits/${editingKitId}`
    : `/api/products/${selectedProduct.id}/kits`;
  try {
    selectedProduct = await fetchJson(url, {
      method: editingKitId ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    resetKitForm();
    await loadState(selectedProduct.id);
  } catch (error) {
    window.alert(`Не удалось сохранить комплект: ${error.message}`);
  }
}

function startKitEdit(event) {
  if (!selectedProduct) return;
  const kitId = Number(event.currentTarget.dataset.editKitId);
  const kit = (selectedProduct.kits || []).find((item) => Number(item.id) === kitId);
  if (!kit) return;
  editingKitId = kitId;
  const form = document.getElementById("kitForm");
  form.querySelector("[name='kit_sku']").value = kit.kit_sku || "";
  form.querySelector("[name='kit_name']").value = kit.kit_name || "";
  form.querySelector("[name='units_per_kit']").value = kit.units_per_kit || 1;
  form.querySelector("[name='secondary_product_id']").value = kit.secondary_product_id ? String(kit.secondary_product_id) : "";
  form.querySelector("[name='secondary_units_per_kit']").value = kit.secondary_units_per_kit || 0;
  document.getElementById("kitSubmit").textContent = "Сохранить комплект";
  document.getElementById("cancelKitEdit").classList.remove("hidden");
  form.scrollIntoView({ behavior: "smooth", block: "center" });
}

function cancelKitEdit() {
  resetKitForm();
}

function resetKitForm() {
  editingKitId = null;
  const form = document.getElementById("kitForm");
  form.reset();
  form.querySelector("[name='units_per_kit']").value = 1;
  form.querySelector("[name='secondary_units_per_kit']").value = 0;
  document.getElementById("kitSubmit").textContent = "Добавить комплект";
  document.getElementById("cancelKitEdit").classList.add("hidden");
}

async function deleteKit(event) {
  if (!selectedProduct) return;
  const kitId = event.currentTarget.dataset.kitId;
  const confirmed = window.confirm("Удалить этот комплект? Остаток этой вариации на сайте будет обнулен.");
  if (!confirmed) return;
  if (Number(kitId) === editingKitId) resetKitForm();
  selectedProduct = await fetchJson(`/api/products/${selectedProduct.id}/kits/${kitId}`, { method: "DELETE" });
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
  form.querySelector("[name='sale_channel']").value = "olx";
  await loadState(selectedProduct.id);
}

async function addQuickSale(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.product_id = Number(payload.product_id || 0);
  payload.quantity = Number(payload.quantity || 0);
  payload.unit_price = Number(payload.unit_price || 0);
  await fetchJson(editingSaleId ? `/api/sales/${editingSaleId}` : "/api/sales", {
    method: editingSaleId ? "PUT" : "POST",
    body: JSON.stringify(payload),
  });

  const productId = payload.product_id;
  const saleChannel = payload.sale_channel || "olx";
  editingSaleId = null;
  form.reset();
  form.querySelector("[name='sale_date']").valueAsDate = new Date();
  form.querySelector("[name='quantity']").value = 1;
  form.querySelector("[name='sale_channel']").value = saleChannel;
  document.getElementById("quickSaleProduct").value = String(productId);
  document.getElementById("quickSaleSubmit").textContent = "Добавить продажу";
  document.getElementById("cancelSaleEdit").classList.add("hidden");
  fillQuickSalePrice();
  await loadState(selectedProduct?.id);
}

function startSaleEdit(event) {
  const saleId = Number(event.currentTarget.dataset.editSaleId);
  const sale = (state.sales || []).find((item) => Number(item.id) === saleId);
  if (!sale) return;
  editingSaleId = saleId;
  const form = document.getElementById("quickSaleForm");
  form.querySelector("[name='product_id']").value = String(sale.product_id);
  form.querySelector("[name='sale_date']").value = sale.sale_date;
  form.querySelector("[name='quantity']").value = sale.quantity;
  form.querySelector("[name='unit_price']").value = sale.unit_price;
  form.querySelector("[name='sale_channel']").value = sale.sale_channel || "olx";
  form.querySelector("[name='comment']").value = sale.comment || "";
  document.getElementById("quickSaleSubmit").textContent = "Сохранить продажу";
  document.getElementById("cancelSaleEdit").classList.remove("hidden");
  form.scrollIntoView({ behavior: "smooth", block: "center" });
}

function cancelSaleEdit() {
  editingSaleId = null;
  const form = document.getElementById("quickSaleForm");
  const productId = document.getElementById("quickSaleProduct").value;
  form.reset();
  form.querySelector("[name='sale_date']").valueAsDate = new Date();
  form.querySelector("[name='quantity']").value = 1;
  form.querySelector("[name='sale_channel']").value = "olx";
  document.getElementById("quickSaleProduct").value = productId;
  document.getElementById("quickSaleSubmit").textContent = "Добавить продажу";
  document.getElementById("cancelSaleEdit").classList.add("hidden");
  fillQuickSalePrice();
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
  if (Number(saleId) === editingSaleId) cancelSaleEdit();
  await loadState(selectedProduct?.id);
}

function isoDate(value) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function applySalesPeriodFilter() {
  const value = document.getElementById("salesPeriodFilter").value;
  const from = document.getElementById("salesDateFrom");
  const to = document.getElementById("salesDateTo");
  const today = new Date();
  const start = new Date(today);

  if (!value) {
    from.value = "";
    to.value = "";
  } else if (value === "today") {
    from.value = isoDate(today);
    to.value = isoDate(today);
  } else if (value === "month") {
    start.setDate(1);
    from.value = isoDate(start);
    to.value = isoDate(today);
  } else {
    start.setDate(today.getDate() - Number(value) + 1);
    from.value = isoDate(start);
    to.value = isoDate(today);
  }
  renderSalesPage();
}

function resetSalesFilters() {
  document.getElementById("salesSearch").value = "";
  document.getElementById("salesProductFilter").value = "";
  document.getElementById("salesPeriodFilter").value = "";
  document.getElementById("salesDateFrom").value = "";
  document.getElementById("salesDateTo").value = "";
  document.getElementById("salesSort").value = "date_desc";
  renderSalesPage();
}

function renderAnalytics() {
  const analytics = state.analytics || {};
  const exportMonth = document.getElementById("exportMonth");
  if (exportMonth && !exportMonth.value) {
    exportMonth.value = (state.monthly_stats || [])[0]?.month || isoDate(new Date()).slice(0, 7);
  }
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
          <td><button class="icon-button" data-export-month="${row.month}" title="Скачать отчет за месяц">Скачать</button></td>
        </tr>`,
    )
    .join("") || `<tr><td colspan="10" class="empty">Месячной статистики пока нет</td></tr>`;

  document.querySelectorAll("[data-export-month]").forEach((button) => {
    button.addEventListener("click", () => downloadMonthReport(button.dataset.exportMonth));
  });
}

function downloadMonthReport(month) {
  if (!month) {
    window.alert("Выберите месяц для выгрузки.");
    return;
  }
  window.location.href = `/api/monthly-export?month=${encodeURIComponent(month)}`;
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
  if (!response.ok) {
    const text = await response.text();
    try {
      const payload = JSON.parse(text);
      throw new Error(payload.detail || text);
    } catch (error) {
      if (error instanceof SyntaxError) throw new Error(text);
      throw error;
    }
  }
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
