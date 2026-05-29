function getTodayISO() {
  const d = new Date();
  return d.toISOString().slice(0, 10);
}

let linkyPlot = null;
let tempPlot = null;
let selectedDate = new Date();
selectedDate.setHours(0, 0, 0, 0);

function fetchAndShowDailySummary(day) {
  fetch(`/linky_daily?day=${day}`)
    .then((res) => res.json())
    .then((summary) => {
      const el = document.getElementById("daily-summary");
      if (!summary || summary.total_kwh === null) {
        el.innerHTML = "<b>No daily summary available.</b>";
        return;
      }
      let statusColor = "#aaa";
      if (summary.status === "ok") statusColor = "#22c55e";
      else if (summary.status === "ongoing") statusColor = "#f59e42";
      else if (summary.status === "nok") statusColor = "#e41a1c";
      el.innerHTML = `
        <div style="display:flex;flex-wrap:wrap;align-items:center;gap:2em;">
          <div>
            <div style="font-size:1.1em;font-weight:600;">Total kWh</div>
            <div style="font-size:2em;">${summary.total_kwh ?? "-"}</div>
          </div>
          <div>
            <div style="font-size:1.1em;font-weight:600;">Status</div>
            <div style="font-size:1.2em;font-weight:600;color:${statusColor};">${
        summary.status
      }</div>
          </div>
          <div>
            <div style="font-size:1.1em;font-weight:600;">Cost (€)</div>
            <div style="font-size:1.5em;">${summary.cost_eur ?? "-"}</div>
          </div>
        </div>
        <div style="margin-top:1em;">
          <div style="font-size:1.1em;font-weight:600;">Top 5 Consumption Events</div>
          <ol style="margin:0.5em 0 0 1.5em;">
            ${
              summary.top_events && summary.top_events.length
                ? summary.top_events
                    .map(
                      (ev) =>
                        `<li>
                      <span style="font-weight:500;">${ev.start.slice(
                        11,
                        16
                      )}–${ev.end.slice(11, 16)}</span>
                      (${ev.duration_min} min, max ${ev.max_power} W)
                    </li>`
                    )
                    .join("")
                : "<li>No events</li>"
            }
          </ol>
        </div>
      `;
    })
    .catch((err) => {
      document.getElementById("daily-summary").innerHTML =
        "<b>Failed to load daily summary.</b>";
      console.error(err);
    });
}

function fetchAndDraw(day) {
  fetchAndShowDailySummary(day);

  // Linky chart
  fetch(`/linky?day=${day}`)
    .then((res) => res.json())
    .then((jsonObj) => {
      const data = jsonObj.data;
      if (!data || data.length === 0) {
        document.getElementById("chart").innerText = "No data";
        linkyPlot = null;
        return;
      }

      const times = data
        .map((row) => {
          const dt = new Date(row.time);
          if (isNaN(dt.getTime())) return null;
          return dt.getUTCHours() * 60 + dt.getUTCMinutes();
        })
        .filter((v) => v !== null);

      const apparentPower = data.map((row) => row.apparent_power);
      const activePower = data.map((row) => row.active_power);

      const opts = {
        title: "Apparent Power over Time",
        width: 600,
        height: 300,
        scales: { x: { time: false } },
        series: [
          {
            label: "Time",
            value: (u, v) => {
              const h = Math.floor(v / 60)
                .toString()
                .padStart(2, "0");
              const m = (v % 60).toString().padStart(2, "0");
              return `${h}:${m}`;
            },
          },
          { label: "Apparent Power", stroke: "#377eb8" },
          { label: "Active Power", stroke: "#97441eff" },
        ],
        axes: [
          {
            label: "Time (HH:MM)",
            values: (u, ticks) =>
              ticks.map((v) => {
                const h = Math.floor(v / 60)
                  .toString()
                  .padStart(2, "0");
                const m = (v % 60).toString().padStart(2, "0");
                return `${h}:${m}`;
              }),
          },
          { label: "Power" },
        ],
      };

      const chartDiv = document.getElementById("chart");
      chartDiv.innerHTML = "";
      linkyPlot = new uPlot(
        opts,
        [times, apparentPower, activePower],
        chartDiv
      );
    })
    .catch((err) => {
      document.getElementById("chart").innerText = "Failed to load data";
      linkyPlot = null;
      console.error(err);
    });

  // Temperatures chart
  fetchAndDrawTemperatures(day);
}

function fetchAndDrawTemperatures(day) {
  fetch(`/temperatures?day=${day}`)
    .then((res) => res.json())
    .then((jsonObj) => {
      const chartDiv = document.getElementById("temp-chart");
      if (!jsonObj || Object.keys(jsonObj).length === 0) {
        chartDiv.innerText = "No data";
        tempPlot = null;
        return;
      }

      // Collect all unique times (minutes since midnight UTC)
      const timeSet = new Set();
      const sensorNames = Object.keys(jsonObj).sort();
      const sensorSeries = {};

      sensorNames.forEach((sensor) => {
        const data = jsonObj[sensor]?.data || [];
        sensorSeries[sensor] = {};
        data.forEach((row) => {
          const dt = new Date(row.time);
          if (isNaN(dt.getTime())) return;
          const t = dt.getUTCHours() * 60 + dt.getUTCMinutes();
          timeSet.add(t);
          sensorSeries[sensor][t] = row.temperature;
        });
      });

      const times = Array.from(timeSet).sort((a, b) => a - b);

      // Build series arrays: [times, serie1, serie2, ...]
      const seriesData = sensorNames.map((sensor) =>
        times.map((t) =>
          sensorSeries[sensor][t] !== undefined ? sensorSeries[sensor][t] : null
        )
      );
      const dataArr = [times, ...seriesData];

      // Define a color palette for strokes
      const palette = [
        "#e41a1c",
        "#377eb8",
        "#4daf4a",
        "#984ea3",
        "#ff7f00",
        "#a65628",
        "#f781bf",
        "#999999",
        "#66c2a5",
        "#fc8d62",
      ];

      // Build series config with stroke
      const series = [
        {
          label: "Time",
          value: (u, v) => {
            const h = Math.floor(v / 60)
              .toString()
              .padStart(2, "0");
            const m = (v % 60).toString().padStart(2, "0");
            return `${h}:${m}`;
          },
        },
        ...sensorNames.map((name, idx) => ({
          label: name,
          stroke: palette[idx % palette.length],
          spanGaps: true,
        })),
      ];

      const opts = {
        title: "Temperatures",
        width: 600,
        height: 300,
        scales: { x: { time: false } },
        series,
        axes: [
          {
            label: "Time (HH:MM)",
            values: (u, ticks) =>
              ticks.map((v) => {
                const h = Math.floor(v / 60)
                  .toString()
                  .padStart(2, "0");
                const m = (v % 60).toString().padStart(2, "0");
                return `${h}:${m}`;
              }),
          },
          { label: "Temperature (°C)" },
        ],
      };

      chartDiv.innerHTML = "";
      tempPlot = new uPlot(opts, dataArr, chartDiv);
    })
    .catch((err) => {
      document.getElementById("temp-chart").innerText = "Failed to load data";
      tempPlot = null;
      console.error(err);
    });
}

let monthlyData = null;
let monthlyPlots = [];

const PALETTE = [
  "#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00",
  "#a65628", "#f781bf", "#999999", "#66c2a5", "#fc8d62",
];

function statusColor(status) {
  if (status === "ok") return "#22c55e";
  if (status === "ongoing") return "#f59e42";
  if (status === "nok") return "#e41a1c";
  return "#bbb";
}

// Map a numeric value to a background color across a min..max range.
// scheme: "kwh" (blue scale), "cold" (blue), "warm" (red).
function heatColor(value, min, max, scheme) {
  if (value == null || min == null || max == null || max === min) return "";
  const t = Math.max(0, Math.min(1, (value - min) / (max - min)));
  // Light → saturated, white background blended with the hue.
  const alpha = 0.08 + t * 0.55;
  let rgb;
  if (scheme === "warm") rgb = "228, 26, 28";
  else if (scheme === "cold") rgb = "55, 126, 184";
  else rgb = "55, 126, 184";
  return `rgba(${rgb}, ${alpha.toFixed(3)})`;
}

function fmtNum(v, digits) {
  if (v == null || Number.isNaN(v)) return "—";
  return Number(v).toFixed(digits);
}

function renderMonthlyCharts() {
  const root = document.getElementById("monthly-charts");
  root.innerHTML = "";
  monthlyPlots.forEach((p) => p.destroy());
  monthlyPlots = [];

  if (!monthlyData || !monthlyData.days || !monthlyData.days.length) return;

  // Oldest → newest, x-axis = unix seconds (uPlot time scale).
  const ordered = [...monthlyData.days].reverse();
  const xs = ordered.map((d) => new Date(d.date + "T00:00:00Z").getTime() / 1000);

  const rooms = monthlyData.rooms || [];
  const width = Math.max(600, root.clientWidth - 16);
  const height = 220;

  const commonAxes = [{}, { size: 45 }];

  // 1) Daily kWh as bars.
  const kwh = ordered.map((d) => (d.kwh == null ? null : d.kwh));
  monthlyPlots.push(makeChart(root, "Daily energy (kWh)", {
    width, height,
    series: [
      {},
      {
        label: "kWh",
        stroke: "#377eb8",
        fill: "rgba(55,126,184,0.4)",
        paths: uPlot.paths.bars({ size: [0.7, 100] }),
        points: { show: false },
      },
    ],
    axes: commonAxes,
  }, [xs, kwh]));

  // 2) Temperatures: outdoor min/max + indoor min/max per room.
  const extMin = ordered.map((d) => (d.ext_min == null ? null : d.ext_min));
  const extMax = ordered.map((d) => (d.ext_max == null ? null : d.ext_max));
  const tempSeries = [
    {},
    { label: "Outdoor min", stroke: "#377eb8", width: 2, spanGaps: true },
    { label: "Outdoor max", stroke: "#e41a1c", width: 2, spanGaps: true },
  ];
  const tempData = [xs, extMin, extMax];
  rooms.forEach((r, i) => {
    const color = PALETTE[(i + 2) % PALETTE.length];
    tempSeries.push({ label: `${r} min`, stroke: color, dash: [4, 3], spanGaps: true });
    tempSeries.push({ label: `${r} max`, stroke: color, spanGaps: true });
    tempData.push(ordered.map((d) => d.rooms?.[r]?.min ?? null));
    tempData.push(ordered.map((d) => d.rooms?.[r]?.max ?? null));
  });
  monthlyPlots.push(makeChart(root, "Temperatures (°C, daily min/max)", {
    width, height,
    series: tempSeries,
    axes: commonAxes,
  }, tempData));
}

function makeChart(root, title, opts, data) {
  const wrap = document.createElement("div");
  wrap.className = "monthly-chart";
  const h = document.createElement("div");
  h.className = "monthly-chart-title";
  h.textContent = title;
  wrap.appendChild(h);
  root.appendChild(wrap);
  return new uPlot(opts, data, wrap);
}

function renderMonthOverview() {
  const root = document.getElementById("month-overview");
  if (!monthlyData) {
    root.textContent = "Loading…";
    return;
  }
  const { days, rooms } = monthlyData;
  if (!days || !days.length) {
    root.textContent = "No data.";
    return;
  }

  // Oldest → newest so reading order is left-to-right chronological.
  const orderedDays = [...days].reverse();

  const selISO = selectedDate.toISOString().slice(0, 10);

  const table = document.createElement("table");
  table.className = "month-table";

  // Build a per-row helper: label + a value-cell builder for each day.
  const rows = [];

  // Date: split into day-of-month and month rows.
  rows.push({
    label: "Day",
    build: (d) => {
      const dt = new Date(d.date + "T00:00:00");
      const td = document.createElement("td");
      td.className = "date";
      td.textContent = dt.getDate();
      if (dt.getDay() === 0 || dt.getDay() === 6) td.classList.add("weekend");
      return td;
    },
  });
  rows.push({
    label: "Month",
    build: (d, idx) => {
      const dt = new Date(d.date + "T00:00:00");
      const td = document.createElement("td");
      td.className = "month";
      // Show month label on the 1st of the month or on the leftmost column.
      const showLabel = dt.getDate() === 1 || idx === 0;
      td.textContent = showLabel ? dt.getMonth() + 1 : "";
      return td;
    },
  });

  // kWh status (one dot per day).
  rows.push({
    label: "Energy",
    build: (d) => {
      const td = document.createElement("td");
      td.innerHTML = `<span class="status-dot" title="${d.status} (${fmtNum(d.kwh, 1)} kWh)" style="background:${statusColor(d.status)}"></span>`;
      return td;
    },
  });

  // One row per sensor/room: data-present dot.
  rooms.forEach((r) => {
    rows.push({
      label: r,
      build: (d) => {
        const td = document.createElement("td");
        const room = d.rooms?.[r];
        const present = room && (room.min != null || room.max != null);
        const color = present ? "#22c55e" : "#ddd";
        const title = present
          ? `${r}: ${fmtNum(room.min, 1)} / ${fmtNum(room.max, 1)} °C`
          : `${r}: no data`;
        td.innerHTML = `<span class="status-dot" title="${title}" style="background:${color}"></span>`;
        return td;
      },
    });
  });

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    const th = document.createElement("th");
    th.scope = "row";
    th.textContent = row.label;
    tr.appendChild(th);
    orderedDays.forEach((d, idx) => {
      const td = row.build(d, idx);
      if (d.date === selISO) td.classList.add("col-selected");
      td.onclick = () => {
        selectedDate = new Date(d.date + "T00:00:00");
        selectedDate.setHours(0, 0, 0, 0);
        renderMonthOverview();
        document.getElementById("day-detail-title").textContent = `Detail — ${d.date}`;
        fetchAndDraw(d.date);
      };
      td.style.cursor = "pointer";
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);

  root.innerHTML = "";
  root.appendChild(table);
}

function fetchMonthOverview() {
  fetch(`/monthly_summary?days=60`)
    .then((res) => res.json())
    .then((data) => {
      monthlyData = data;
      renderMonthlyCharts();
      renderMonthOverview();
    })
    .catch((err) => {
      document.getElementById("month-overview").textContent =
        "Failed to load monthly summary.";
      console.error(err);
    });
}

document.addEventListener("DOMContentLoaded", () => {
  const iso = selectedDate.toISOString().slice(0, 10);
  document.getElementById("day-detail-title").textContent = `Detail — ${iso}`;
  fetchMonthOverview();
  fetchAndDraw(iso);
});
