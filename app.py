import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta
import yaml
from miniha.influx_interface import InfluxInterface
import json
from flask import Flask, send_from_directory, jsonify, request

import pandas as pd
from miniha.config import config


# --- uPlot Rendering Helper ---
def st_uplot(df_dict, measurement):
    """
    df_dict: dict of {group_name: DataFrame}
    """
    if not df_dict:
        st.warning("No data found.")
        return

    # Combine data for uPlot format: [ [timestamps], [series1], [series2]... ]
    # We'll use the first available dataframe to get the X-axis (timestamps)
    first_key = list(df_dict.keys())[0]
    df_first = df_dict[first_key]

    if df_first.empty:
        st.warning("Dataframe is empty.")
        return

    timestamps = (df_first.index.view("int64") // 10**9).tolist()
    uplot_data = [timestamps]
    series_opts = [{"label": "Time"}]

    # Generate series for each group and each field
    colors = ["#3498db", "#e74c3c", "#2ecc71", "#f1c40f", "#9b59b6", "#1abc9c"]
    color_idx = 0

    for group_name, df in df_dict.items():
        for field in df.columns:
            uplot_data.append(df[field].tolist())
            series_opts.append(
                {
                    "label": f"{group_name} - {field}",
                    "stroke": colors[color_idx % len(colors)],
                    "width": 1.5,
                }
            )
            color_idx += 1

    uplot_html = f"""
    <html>
    <head>
        <link rel="stylesheet" href="https://unpkg.com/uplot/dist/uPlot.min.css">
        <script src="https://unpkg.com/uplot/dist/uPlot.iife.min.js"></script>
    </head>
    <body>
        <div id="chart"></div>
        <script>
            const data = {json.dumps(uplot_data)};
            const opts = {{
                title: "{measurement}",
                width: 1000,
                height: 500,
                scales: {{ x: {{ time: true }} }},
                series: {json.dumps(series_opts)},
                axes: [{{}}, {{ space: 40 }}],
                cursor: {{ drag: {{ setScale: false }} }}
            }};
            new uPlot(opts, data, document.getElementById("chart"));
        </script>
    </body>
    </html>
    """
    st.components.v1.html(uplot_html, height=550)


# --- App Logic ---
st.title("📊 InfluxDB TimeSeries Explorer")

influx_client = InfluxInterface(
    host=config.INFLUX_HOST,
    port=config.INFLUX_PORT,
    username="",
    password="",
    database=config.INFLUX_DB,
)


# 1. Fetch available measurements
measurements = influx_client.list_measurements()
selected_meas = st.sidebar.selectbox("Measurement", measurements)

# 2. Fetch fields for selected measurement
if selected_meas:
    available_fields = influx_client.show_fields(selected_meas)
    available_fields_name = [field["fieldKey"] for field in available_fields]
    with st.sidebar.form("query_form"):
        selected_fields = st.multiselect("Fields", available_fields_name)
        day = st.date_input(
            "Start Day", datetime.now() - timedelta(days=1), format="YYYY-MM-DD"
        )
        nbr_days = st.number_input("Days", min_value=1, value=1)

        available_series = influx_client.show_series(selected_meas)
        st.write(available_series)

        availabel_tags = influx_client.show_tags(selected_meas)
        group_by = st.selectbox(
            "Group By Tag (optional)",
            [None] + [tag["tagKey"] for tag in availabel_tags],
        )
        st.write(group_by)
        submit = st.form_submit_button("Run Query")

    if submit and selected_fields:
        with st.spinner("Fetching data..."):
            # Execute Query
            # Note: Assuming your client returns a dict of DFs when group_by is used
            fields = selected_fields + [
                group_by,
            ]
            df_dicts = influx_client.query_df(
                measurement=selected_meas,
                field_list=fields,
                start=day,
                end=pd.to_datetime(day) + pd.Timedelta(days=nbr_days),
                group_by=group_by if group_by else None,
                wheres=[("name", "sensors/thA")],
            )
            st.write(f"{df_dicts}")
        if not df_dicts:
            st.warning("No data returned for this query.")
        else:
            st.write(df_dicts)
            # 3. Data Wrangling for st.line_chart
            # If it's a dict, we need to prefix columns with the group name to distinguish lines
            combined_df = pd.DataFrame(df_dicts[selected_meas])
            # combined_df = pd.DataFrame()
            # if isinstance(df_dicts, dict):
            #     for group_name, df in df_dicts.items():
            #         if not df.empty:
            #             # Rename columns: "temperature" -> "Device_A: temperature"
            #             renamed_df = df[selected_fields].rename(
            #                 columns={
            #                     col: f"{group_name}: {col}" for col in selected_fields
            #                 }
            #             )
            #             combined_df = pd.concat([combined_df, renamed_df], axis=1)
            # else:
            #     # If it's a single DataFrame (no group_by)
            #     combined_df = df_dicts[selected_fields]

            # 4. Display the Graph
            if not combined_df.empty:
                st.subheader(f"Results: {selected_meas}")
                st.line_chart(combined_df)

                with st.expander("Show Raw Data Table"):
                    st.write(combined_df)
            else:
                st.info("The query returned an empty dataset.")
