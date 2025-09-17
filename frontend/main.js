function getTodayISO() {
  const d = new Date();
  return d.toISOString().slice(0, 10);
}

let currentEvent = null;
let linkyPlot = null;
let tempPlot = null;
let eventRanges = [];

function fetchAndDraw(day) {
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
          { label: "Apparent Power" },
        ],
      };

      const chartDiv = document.getElementById("chart");
      chartDiv.innerHTML = "";
      linkyPlot = new uPlot(opts, [times, apparentPower], chartDiv);
    })
    .catch((err) => {
      document.getElementById("chart").innerText = "Failed to load data";
      linkyPlot = null;
      console.error(err);
    });

  // Temperatures chart
  fetchAndDrawTemperatures(day);
  // Events
  fetchAndShowEvents(day);
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

function fetchAndShowEvents(day) {
  fetch(`/events?day=${day}`)
    .then((res) => res.json())
    .then((events) => {
      eventRanges = events.map((ev, idx) => {
        // Parse start/end as minutes since midnight UTC
        const startDt = new Date(ev.start);
        const endDt = new Date(ev.end);
        return {
          ...ev,
          idx,
          startMinutes: startDt.getUTCHours() * 60 + startDt.getUTCMinutes(),
          endMinutes: endDt.getUTCHours() * 60 + endDt.getUTCMinutes(),
        };
      });
      renderEventList();
    })
    .catch((err) => {
      document.getElementById("event-list").innerText = "Failed to load events";
      eventRanges = [];
      renderEventList();
      console.error(err);
    });
}

function renderEventList() {
  const ul = document.getElementById("event-list");
  ul.innerHTML = "";
  if (!eventRanges.length) {
    ul.innerHTML = "<li>No events</li>";
    return;
  }
  eventRanges.forEach((ev) => {
    const li = document.createElement("li");
    li.className =
      "event-item" +
      (currentEvent && currentEvent.idx === ev.idx ? " selected" : "");
    li.innerHTML = `<div class="event-title">${ev.title}</div>
      <div class="event-message">${ev.message}</div>
      <div style="font-size:0.9em;color:#888;">
        ${formatMinutes(ev.startMinutes)} - ${formatMinutes(ev.endMinutes)}
      </div>`;
    li.onclick = () => {
      currentEvent = ev;
      console.log("Selected event", ev);
      renderEventList();
      // Redraw graphs with highlight
      // fetchAndDraw(document.getElementById("day").value);
    };
    ul.appendChild(li);
  });
}

function formatMinutes(mins) {
  const h = Math.floor(mins / 60)
    .toString()
    .padStart(2, "0");
  const m = (mins % 60).toString().padStart(2, "0");
  return `${h}:${m}`;
}

const dayInput = document.getElementById("day");
dayInput.value = getTodayISO();

dayInput.addEventListener("change", (e) => {
  currentEvent = null;
  fetchAndDraw(e.target.value);
});

// Initial load
fetchAndDraw(dayInput.value);

// Initial load
fetchAndDraw(dayInput.value);
