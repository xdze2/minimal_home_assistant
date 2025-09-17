function getTodayISO() {
  const d = new Date();
  return d.toISOString().slice(0, 10);
}

const dayInput = document.getElementById("day");
dayInput.value = getTodayISO();

function fetchAndDraw(day) {
  fetch(`/linky?day=${day}`)
    .then((res) => res.json())
    .then((jsonObj) => {
      const data = jsonObj.data;
      if (!data || data.length === 0) {
        document.getElementById("chart").innerText = "No data";
        return;
      }

      // Parse ISO time string to minutes since midnight (UTC)
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
          { label: "Apparent Power", stroke: "red" },
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

      // Remove previous chart if exists
      const chartDiv = document.getElementById("chart");
      chartDiv.innerHTML = "";
      const dataArr = [times, apparentPower];
      new uPlot(opts, dataArr, chartDiv);
    })
    .catch((err) => {
      document.getElementById("chart").innerText = "Failed to load data";
      console.error(err);
    });
}

dayInput.addEventListener("change", (e) => {
  fetchAndDraw(e.target.value);
});

// Initial load
fetchAndDraw(dayInput.value);
