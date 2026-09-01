window.setTimeout(function () {
  document.querySelectorAll(".flash").forEach(function (item) { item.remove(); });
}, 5000);

document.addEventListener("DOMContentLoaded", function () {
  if (window.lucide) window.lucide.createIcons();
  var menu = document.querySelector("[data-menu-toggle]");
  if (menu) menu.addEventListener("click", function () {
    document.querySelector("#sidebar").classList.toggle("open");
  });
  document.querySelectorAll("[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
});

var chartColors = { healthy: "#28a287", degraded: "#d49b2d", down: "#d95768" };

window.PulseOpsDashboard = async function () {
  var root = document.querySelector("[data-dashboard]");
  if (!root || !window.Chart) return;
  var responseChart;
  var distributionChart;
  var uptimeChart;
  var refresh = async function () {
    try {
      var response = await fetch("/api/v1/dashboard/summary", { headers: { Accept: "application/json" } });
      if (!response.ok) return;
      var payload = await response.json();
      Object.entries(payload.summary).forEach(function (entry) {
        var key = entry[0], value = entry[1];
        var element = document.querySelector('[data-kpi="' + key + '"]');
        if (!element) return;
        if (key === "avg_response") element.textContent = value === null ? "No data" : value + " ms";
        else if (key === "uptime_pct") element.textContent = value === null ? "No data" : value + "%";
        else element.textContent = value;
      });
      payload.services.forEach(function (service) {
        var row = document.querySelector('[data-service-id="' + service.id + '"]');
        if (!row) return;
        row.querySelector('[data-field="health"]').innerHTML = '<span class="badge ' + service.health + '">' + service.health + '</span>';
        row.querySelector('[data-field="status"]').textContent = service.last_status || "—";
        row.querySelector('[data-field="latency"]').textContent = service.last_response_time_ms === null ? "—" : service.last_response_time_ms + " ms";
        row.querySelector('[data-field="uptime"]').textContent = service.uptime_24h === null ? "No data" : service.uptime_24h + "%";
        row.querySelector('[data-field="checked"]').textContent = service.last_checked_at ? new Date(service.last_checked_at).toLocaleString() : "Never";
        row.querySelector('[data-field="monitoring"]').innerHTML = '<span class="monitor-dot ' + (service.is_active ? "on" : "") + '"></span>' + (service.is_active ? "Active" : "Paused");
      });
      var points = payload.charts.response_time;
      var responseBox = document.querySelector("#responseChart").parentElement;
      responseBox.classList.toggle("empty", !points.length);
      if (points.length) {
        var serviceNames = Array.from(new Set(points.map(function (point) { return point.service; })));
        var palette = ["#5368df", "#18a081", "#d49225", "#d95768", "#7a56c5", "#0b8193", "#d16728", "#68758c"];
        var responseDatasets = serviceNames.map(function (serviceName, index) {
          var color = palette[index % palette.length];
          return {
            label: serviceName,
            data: points.map(function (point) { return point.service === serviceName ? point.response_time_ms : null; }),
            borderColor: color,
            backgroundColor: color,
            borderWidth: 2,
            tension: .32,
            pointRadius: 0,
            pointHoverRadius: 4,
            spanGaps: true
          };
        });
        var responseConfig = {
          type: "line",
          data: { labels: points.map(function (p) { return new Date(p.checked_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit" }); }), datasets: responseDatasets },
          options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false }, plugins: { legend: { position: "bottom", labels: { usePointStyle: true, pointStyle: "circle", boxWidth: 7, padding: 16, font: { size: 10 } } } }, scales: { y: { beginAtZero: true, grid: { color: "#edf0f5" }, title: { display: true, text: "ms" } }, x: { grid: { display: false }, ticks: { maxTicksLimit: 7, maxRotation: 0 } } } }
        };
        if (responseChart) { responseChart.data = responseConfig.data; responseChart.update(); }
        else responseChart = new Chart(document.querySelector("#responseChart"), responseConfig);
      }
      var distribution = payload.charts.distribution;
      var values = [distribution.healthy || 0, distribution.degraded || 0, distribution.down || 0];
      var distributionBox = document.querySelector("#distributionChart").parentElement;
      distributionBox.classList.toggle("empty", values.every(function (value) { return value === 0; }));
      if (values.some(function (value) { return value > 0; })) {
        var distributionConfig = { type: "doughnut", data: { labels: ["Healthy", "Degraded", "Failed"], datasets: [{ data: values, backgroundColor: [chartColors.healthy, chartColors.degraded, chartColors.down], borderColor: "#fff", borderWidth: 4, hoverOffset: 5 }] }, options: { responsive: true, maintainAspectRatio: false, cutout: "72%", plugins: { legend: { position: "bottom", labels: { usePointStyle: true, pointStyle: "circle", boxWidth: 7, padding: 18, font: { size: 10 } } } } } };
        if (distributionChart) { distributionChart.data = distributionConfig.data; distributionChart.update(); }
        else distributionChart = new Chart(document.querySelector("#distributionChart"), distributionConfig);
      }
      var uptimePoints = payload.charts.uptime_trend;
      var knownUptime = uptimePoints.some(function (point) { return point.uptime !== null; });
      var uptimeBox = document.querySelector("#uptimeChart").parentElement;
      uptimeBox.classList.toggle("empty", !knownUptime);
      if (knownUptime) {
        var uptimeConfig = {
          type: "line",
          data: { labels: uptimePoints.map(function (p) { return p.date; }), datasets: [{ label: "Uptime (%)", data: uptimePoints.map(function (p) { return p.uptime; }), borderColor: chartColors.healthy, backgroundColor: "rgba(40,162,135,.08)", fill: true, tension: .2, spanGaps: false }] },
          options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { min: 0, max: 100, grid: { color: "#edf0f5" }, title: { display: true, text: "%" } }, x: { grid: { display: false } } } }
        };
        if (uptimeChart) { uptimeChart.data = uptimeConfig.data; uptimeChart.update(); }
        else uptimeChart = new Chart(document.querySelector("#uptimeChart"), uptimeConfig);
      }
    } catch (error) { /* Preserve server-rendered content during polling failures. */ }
  };
  await refresh();
  window.setInterval(refresh, Math.max(10, Number(root.dataset.refresh || 25)) * 1000);
};

window.PulseOpsServiceChart = async function (serviceId) {
  var canvas = document.querySelector("#serviceResponseChart");
  if (!canvas || !window.Chart) return;
  try {
    var response = await fetch("/api/v1/services/" + serviceId + "/history?limit=100");
    if (!response.ok) return;
    var points = (await response.json()).reverse();
    canvas.parentElement.classList.toggle("empty", !points.length);
    if (!points.length) return;
    new Chart(canvas, {
      type: "line",
      data: { labels: points.map(function (p) { return new Date(p.checked_at).toLocaleString(); }), datasets: [{ label: "Response time (ms)", data: points.map(function (p) { return p.response_time_ms; }), borderColor: "#4b63e8", pointBackgroundColor: points.map(function (p) { return chartColors[p.health_state]; }), pointRadius: 3, tension: .2 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, title: { display: true, text: "ms" } }, x: { ticks: { maxTicksLimit: 10 } } } }
    });
  } catch (error) { canvas.parentElement.classList.add("empty"); }
};
