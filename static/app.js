"use strict";

const $ = (selector) => document.querySelector(selector);

const money = (value) => {
    if (value === null || value === undefined || value === "") return "—";

    const amount = Number(value);
    if (!Number.isFinite(amount)) return "—";

    return new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        maximumFractionDigits: 0
    }).format(amount);
};

const number = (value) => {
    if (value === null || value === undefined || value === "") return "—";

    const amount = Number(value);
    if (!Number.isFinite(amount)) return "—";

    return new Intl.NumberFormat("en-IN", {
        maximumFractionDigits: 1
    }).format(amount);
};

const escapeHTML = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (character) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    })[character]);

let products = [];
let recommendations = [];
let salesChart = null;
let productChart = null;
let editingProductId = null;

async function api(url, options = {}) {
    const response = await fetch(url, {
        ...options,
        headers: {
            ...(options.body ? {
                "Content-Type": "application/json"
            } : {}),
            ...(options.headers || {})
        }
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new Error(
            data.error || `Request failed (${response.status})`
        );
    }

    return data;
}

function setStatus(message, isError = false) {
    const element = $("#status-message");
    if (!element) return;

    element.textContent = message;
    element.classList.toggle("negative", isError);
}

function renderProducts() {
    $("#product-count").textContent = products.length;

    const average = products.length
        ? products.reduce(
            (sum, product) => sum + Number(product.current_price || 0),
            0
        ) / products.length
        : 0;

    $("#average-price").textContent = money(average);

    $("#products-body").innerHTML = products.map((product) => `
        <tr>
            <td>
                <strong>${escapeHTML(product.product_name)}</strong>
                <br><small>${escapeHTML(product.product_id)}</small>
            </td>
            <td>${money(product.current_price)}</td>
            <td>${money(product.cost_price)}</td>
            <td>${number(product.inventory)}</td>
            <td>${money(product.competitor_price)}</td>
            <td>
                <button class="small-action"
                    data-edit="${escapeHTML(product.product_id)}">
                    Edit
                </button>
                <button class="small-action delete"
                    data-delete="${escapeHTML(product.product_id)}">
                    Delete
                </button>
            </td>
        </tr>
    `).join("");

    const previousSelection = $("#sim-product").value;

    $("#sim-product").innerHTML = products.map((product) => `
        <option value="${escapeHTML(product.product_id)}">
            ${escapeHTML(product.product_name)}
        </option>
    `).join("");

    const selectedProduct =
        products.find((product) => product.product_id === previousSelection)
        || products[0];

    if (selectedProduct) {
        $("#sim-product").value = selectedProduct.product_id;
        $("#sim-price").value = selectedProduct.current_price;
        $("#sim-price").min = selectedProduct.min_price;
        $("#sim-price").max = selectedProduct.max_price;
    }
}

function renderRecommendations() {
    const valid = recommendations.filter((item) =>
        item.recommended_price !== null &&
        item.recommended_price !== undefined &&
        item.recommended_price !== "" &&
        Number.isFinite(Number(item.recommended_price))
    );

    const average = valid.length
        ? valid.reduce(
            (sum, item) => sum + Number(item.recommended_price),
            0
        ) / valid.length
        : 0;

    $("#average-recommended").textContent = money(average);

    const uplift = valid.reduce(
        (sum, item) => sum + Number(item.estimated_profit_change ?? 0),
        0
    );

    $("#estimated-profit").textContent = money(uplift);
    $("#estimated-profit").classList.toggle("negative", uplift < 0);
    $("#estimated-profit").classList.toggle("positive", uplift >= 0);

    $("#recommendations-body").innerHTML = valid.map((item) => {
        const change = Number(item.estimated_profit_change ?? 0);

        const demand =
            item.estimated_demand ??
            item.predicted_demand ??
            item.estimated_units_sold ??
            item.predicted_units;

        return `
            <tr>
                <td>
                    <strong>${escapeHTML(
                        item.product_name || item.product_id
                    )}</strong>
                    <br><small>${escapeHTML(item.product_id)}</small>
                </td>
                <td>${money(item.current_price)}</td>
                <td><strong>${money(item.recommended_price)}</strong></td>
                <td>${number(demand)}</td>
                <td class="${change >= 0 ? "positive" : "negative"}">
                    ${change >= 0 ? "+" : ""}${money(change)}
                </td>
            </tr>
        `;
    }).join("") || `
        <tr>
            <td colspan="5">No recommendations available.</td>
        </tr>
    `;
}

function renderInsights(insights) {
    $("#insights").innerHTML = (insights || []).map((item) => `
        <div class="insight ${escapeHTML(item.type || "")}">
            <strong>${escapeHTML(item.title)}</strong>
            <p>${escapeHTML(item.message)}</p>
        </div>
    `).join("") || "<p>No insights available.</p>";
}

function renderCompetitors(rows) {
    $("#competitors-body").innerHTML = (rows || []).map((row) => {
        const gap = Number(row.price_gap ?? row.gap ?? 0);
        const gapPercent = Number(
            row.price_gap_percent ?? row.gap_percent ?? 0
        );

        return `
            <tr>
                <td>${escapeHTML(row.product_name)}</td>
                <td>${money(row.current_price)}</td>
                <td>${money(row.competitor_price)}</td>
                <td class="${
                    gap > 0 ? "negative" : gap < 0 ? "positive" : ""
                }">
                    ${gap > 0 ? "+" : ""}${money(gap)}
                    <br>
                    <small>
                        ${gapPercent > 0 ? "+" : ""}${number(gapPercent)}%
                    </small>
                </td>
                <td>
                    <span class="pill">${escapeHTML(row.position)}</span>
                </td>
            </tr>
        `;
    }).join("") || `
        <tr>
            <td colspan="5">No competitor data.</td>
        </tr>
    `;
}

function renderComparison(rows) {
    $("#comparison-body").innerHTML = (rows || []).map((row) => {
        const change = Number(row.profit_change ?? 0);

        return `
            <tr>
                <td>${escapeHTML(row.product_name)}</td>
                <td>${money(row.fixed_profit)}</td>
                <td>${money(row.dynamic_profit)}</td>
                <td class="${change >= 0 ? "positive" : "negative"}">
                    ${change >= 0 ? "+" : ""}${money(change)}
                </td>
            </tr>
        `;
    }).join("") || `
        <tr>
            <td colspan="4">No comparison data.</td>
        </tr>
    `;
}

function renderHistory(rows) {
    $("#history-body").innerHTML = (rows || []).map((row) => `
        <tr>
            <td>${escapeHTML(
                String(row.created_at || "")
                    .replace("T", " ")
                    .slice(0, 19)
            )}</td>
            <td>${escapeHTML(row.product_name)}</td>
            <td>${money(row.current_price)}</td>
            <td>${money(row.recommended_price)}</td>
            <td>${money(row.expected_profit)}</td>
        </tr>
    `).join("") || `
        <tr>
            <td colspan="5">
                No saved snapshots yet. Click "Save snapshot".
            </td>
        </tr>
    `;
}

function renderSalesCharts(data) {
    if (typeof Chart === "undefined") {
        setStatus(
            "Charts could not load. Check your internet connection.",
            true
        );
        return;
    }

    const daily = data.daily || {};
    const product = data.products || {};

    if (salesChart) salesChart.destroy();

    salesChart = new Chart($("#sales-chart"), {
        type: "line",
        data: {
            labels: daily.labels || [],
            datasets: [{
                label: "Revenue (₹)",
                data: daily.revenue || [],
                borderColor: "#5756e8",
                backgroundColor: "rgba(87,86,232,.12)",
                fill: true,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: true }
            },
            scales: {
                y: { beginAtZero: true }
            }
        }
    });

    if (productChart) productChart.destroy();

    productChart = new Chart($("#product-chart"), {
        type: "bar",
        data: {
            labels: product.labels || [],
            datasets: [{
                label: "Revenue (₹)",
                data: product.revenue || [],
                backgroundColor: "#7372ed",
                borderRadius: 5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: { beginAtZero: true }
            }
        }
    });
}

async function loadDashboard() {
    setStatus("Loading products…");

    // Load and display prices first.
    try {
        const productData = await api("/api/products");

        products = Array.isArray(productData)
            ? productData
            : productData.products || [];

        renderProducts();
        setStatus("Products loaded. Loading recommendations and analytics…");
    } catch (error) {
        console.error("Product loading failed:", error);
        setStatus(`Could not load products: ${error.message}`, true);
        return;
    }

    // Load other dashboard sections concurrently.
    const tasks = [
        {
            name: "Recommendations",
            request: () => api("/api/recommendations"),
            render: (data) => {
                recommendations = Array.isArray(data)
                    ? data
                    : data.recommendations || [];

                renderRecommendations();
            }
        },
        {
            name: "Sales charts",
            request: () => api("/api/analytics"),
            render: renderSalesCharts
        },
        {
            name: "Competitor analysis",
            request: () => api("/api/competitors"),
            render: renderCompetitors
        },
        {
            name: "Business insights",
            request: () => api("/api/insights"),
            render: renderInsights
        },
        {
            name: "Pricing comparison",
            request: () => api("/api/pricing-comparison"),
            render: renderComparison
        },
        {
            name: "Recommendation history",
            request: () => api("/api/recommendation-history"),
            render: renderHistory
        }
    ];

    const results = await Promise.allSettled(
        tasks.map(async (task) => {
            const data = await task.request();
            task.render(data);
        })
    );

    const failed = results
        .map((result, index) =>
            result.status === "rejected" ? tasks[index].name : null
        )
        .filter(Boolean);

    if (failed.length) {
        console.error("Dashboard sections failed:", failed);
        setStatus(
            `Products loaded. Failed sections: ${failed.join(", ")}`,
            true
        );
    } else {
        setStatus("Dashboard updated.");
    }
}

function openProductForm(product = null) {
    const form = $("#product-form");
    form.reset();

    editingProductId = product ? product.product_id : null;

    form.elements.product_id.readOnly = Boolean(product);

    if (product) {
        for (const field of form.elements) {
            if (field.name && product[field.name] !== undefined) {
                field.value = product[field.name];
            }
        }
    }

    $("#product-form-message").textContent = "";
    form.classList.remove("hidden");
    form.scrollIntoView({
        behavior: "smooth",
        block: "center"
    });
}

function closeProductForm() {
    $("#product-form").classList.add("hidden");
    $("#product-form").reset();
    editingProductId = null;
}

$("#new-product-button").addEventListener("click", () => {
    openProductForm();
});

$("#cancel-product-button").addEventListener("click", closeProductForm);
$("#refresh-button").addEventListener("click", loadDashboard);

$("#products-body").addEventListener("click", async (event) => {
    const editId = event.target.dataset.edit;
    const deleteId = event.target.dataset.delete;

    if (editId) {
        const product = products.find(
            (item) => item.product_id === editId
        );

        if (product) openProductForm(product);
    }

    if (deleteId) {
        const product = products.find(
            (item) => item.product_id === deleteId
        );

        if (!product) return;

        if (!confirm(
            `Delete "${product.product_name}"? This cannot be undone.`
        )) return;

        try {
            await api(
                `/api/products/${encodeURIComponent(deleteId)}`,
                { method: "DELETE" }
            );

            setStatus("Product deleted.");
            await loadDashboard();
        } catch (error) {
            setStatus(error.message, true);
        }
    }
});

$("#product-form").addEventListener("submit", async (event) => {
    event.preventDefault();

    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form).entries());

    for (const key of [
        "current_price",
        "cost_price",
        "inventory",
        "competitor_price",
        "min_price",
        "max_price"
    ]) {
        data[key] = Number(data[key]);
    }

    if (data.min_price > data.max_price) {
        $("#product-form-message").textContent =
            "Minimum price cannot exceed maximum price.";
        return;
    }

    if (
        data.current_price < data.min_price ||
        data.current_price > data.max_price
    ) {
        $("#product-form-message").textContent =
            "Current price must be within the minimum and maximum.";
        return;
    }

    if (data.cost_price < 0 || data.inventory < 0) {
        $("#product-form-message").textContent =
            "Cost and inventory cannot be negative.";
        return;
    }

    try {
        if (editingProductId) {
            await api(
                `/api/products/${encodeURIComponent(editingProductId)}`,
                {
                    method: "PUT",
                    body: JSON.stringify(data)
                }
            );

            setStatus("Product updated.");
        } else {
            await api("/api/products", {
                method: "POST",
                body: JSON.stringify(data)
            });

            setStatus("Product created.");
        }

        closeProductForm();
        await loadDashboard();
    } catch (error) {
        $("#product-form-message").textContent = error.message;
    }
});

$("#sim-product").addEventListener("change", () => {
    const product = products.find(
        (item) => item.product_id === $("#sim-product").value
    );

    if (!product) return;

    $("#sim-price").value = product.current_price;
    $("#sim-price").min = product.min_price;
    $("#sim-price").max = product.max_price;
});

$("#simulator-form").addEventListener("submit", async (event) => {
    event.preventDefault();

    const productId = $("#sim-product").value;
    const price = Number($("#sim-price").value);
    const result = $("#simulation-result");

    result.textContent = "Calculating forecast…";

    try {
        const data = await api("/api/simulate", {
            method: "POST",
            body: JSON.stringify({
                product_id: productId,
                price: price
            })
        });

        const demand =
            data.estimated_demand ??
            data.predicted_demand ??
            data.estimated_units_sold ??
            data.predicted_units;

        const revenue =
            data.estimated_revenue ??
            data.expected_revenue ??
            data.revenue;

        const profit =
            data.estimated_profit ??
            data.expected_profit ??
            data.profit;

        result.innerHTML = `
            <strong>Simulation result</strong><br>
            Test price: ${money(data.price ?? price)}<br>
            Estimated demand: ${number(demand)} units<br>
            Estimated revenue: ${money(revenue)}<br>
            Estimated profit: ${money(profit)}
        `;
    } catch (error) {
        console.error("Simulation failed:", error);
        result.textContent = error.message;
    }
});

$("#save-history-button").addEventListener("click", async () => {
    const button = $("#save-history-button");
    button.disabled = true;

    try {
        const result = await api("/api/recommendation-history", {
            method: "POST",
            body: JSON.stringify({})
        });

        setStatus(result.message || "Recommendation snapshot saved.");

        const history = await api("/api/recommendation-history");
        renderHistory(history);
    } catch (error) {
        setStatus(error.message, true);
    } finally {
        button.disabled = false;
    }
});

loadDashboard();
