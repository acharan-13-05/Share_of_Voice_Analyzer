let sovChartInstance = null;

document.getElementById("analyzeForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  await analyze();
});

async function analyze() {
  const query = document.getElementById("query").value.trim();
  const brands = document.getElementById("brands").value.split(",").map(b => b.trim()).filter(Boolean);
  const per_platform = parseInt(document.getElementById("per_platform").value, 10) || 10;

  const button = document.getElementById("analyzeBtn");
  button.disabled = true;
  button.innerText = "Analyzing...";

  try {
    const response = await fetch("/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, brands, per_platform }),
    });

    if (!response.ok) throw new Error(await response.text());

    const data = await response.json();
    renderMeta(data.meta);
    renderResults(data.summary);
    renderPieChart(data.summary);
  } catch (error) {
    alert("Error: " + error.message);
    console.error(error);
  } finally {
    button.disabled = false;
    button.innerText = "Analyze";
  }
}

function renderMeta(meta) {
  document.getElementById("meta").innerHTML = meta
    ? `<strong>Query:</strong> ${escapeHtml(meta.query)} &nbsp;|&nbsp;
       <strong>N (per platform):</strong> ${meta.per_platform} &nbsp;|&nbsp;
       <strong>Brands:</strong> ${escapeHtml((meta.brands || []).join(", "))}`
    : "";
}

function renderResults(summary) {
  const resultsDiv = document.getElementById("results");
  if (!summary || summary.length === 0) {
    resultsDiv.innerHTML = `<div class="empty">No results found.</div>`;
    return;
  }

  let table = `<table>
    <thead>
      <tr>
        <th>Brand</th><th>Mentions</th><th>Engagement</th>
        <th>Positive Mentions</th><th>Positive Rate</th><th>SoV Score</th>
      </tr></thead><tbody>`;

  summary.forEach(r => {
    table += `<tr>
      <td>${escapeHtml(r.brand)}</td>
      <td>${r.mentions}</td>
      <td>${r.engagement}</td>
      <td>${r.positive_mentions}</td>
      <td>${(r.positive_rate * 100).toFixed(1)}%</td>
      <td>${r.SoV_score.toFixed(6)}</td>
    </tr>`;
  });

  table += "</tbody></table>";
  resultsDiv.innerHTML = table;
}

function renderPieChart(summary) {
  const ctx = document.getElementById("sovChart");
  if (!summary || summary.length === 0) {
    if (sovChartInstance) sovChartInstance.destroy();
    sovChartInstance = null;
    return;
  }

  const labels = summary.map(r => r.brand);
  const data = summary.map(r => r.SoV_score);

  if (sovChartInstance) sovChartInstance.destroy();

  sovChartInstance = new Chart(ctx, {
    type: "pie",
    data: {
      labels,
      datasets: [{
        label: "Share of Voice (SoV)",
        data,
        backgroundColor: ["#7c4dff","#9575cd","#b39ddb","#ce93d8"],
        borderColor: "#fff",
        borderWidth: 1,
      }],
    },
    options: {
      plugins: {
        legend: { position: "bottom", labels: { color: "#eee" } },
        tooltip: {
          callbacks: {
            label: (tooltipItem) => {
              const label = labels[tooltipItem.dataIndex] || "";
              const value = data[tooltipItem.dataIndex] || 0;
              return `${label}: ${(value * 100).toFixed(2)}% SoV`;
            },
          },
        },
      },
    },
  });
}

function escapeHtml(str) {
  return (str || "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
