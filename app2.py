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


from dataclasses import dataclass

from miniha.exp_fit import expfit, exponential_func
import numpy as np


@dataclass
class TimeSerie:
    name: str
    measurement: str
    tag_name: str
    tag_value: str
    fields: list[str]


available_series = [
    TimeSerie(
        name="ThA",
        measurement="sonoff_thermometer",
        tag_name="name",
        tag_value="sensors/thA",
        fields=["temperature"],
    ),
    TimeSerie(
        name="ThA",
        measurement="sonoff_thermometer",
        tag_name="name",
        tag_value="sensors/thA",
        fields=["temperature"],
    ),
    TimeSerie(
        name="Salon",
        measurement="sonoff_thermometer",
        tag_name="name",
        tag_value="sensors/thF",
        fields=["temperature"],
    ),
    TimeSerie(
        name="temperature_cuisine",
        measurement="sonoff_thermometer",
        tag_name="name",
        tag_value="sensors/thC",
        fields=["temperature"],
    ),
    TimeSerie(
        name="T_ext",
        measurement="daikin_aircon",
        tag_name="mac",
        tag_value="C0E434E6AA1C",
        fields=["outside_temperature"],
    ),
]

# --- App Logic ---
st.title("📊 InfluxDB TimeSeries Explorer")

influx_client = InfluxInterface(
    host=config.INFLUX_HOST,
    port=config.INFLUX_PORT,
    username="",
    password="",
    database=config.INFLUX_DB,
)

import matplotlib.pyplot as plt

with st.sidebar.form("query_form"):

    day = st.date_input(
        "Start Day", datetime.now() - timedelta(days=1), format="YYYY-MM-DD"
    )
    nbr_days = st.number_input("Days", min_value=1, value=1)

    selected_serie = st.selectbox(
        "serie",
        available_series,
        format_func=lambda x: f"{x.name}",
    )

    submit = st.form_submit_button("Run Query")


if submit and selected_serie:
    st.write(selected_serie)

    with st.spinner("Fetching data..."):
        df_dicts = influx_client.query_df(
            measurement=selected_serie.measurement,
            field_list=selected_serie.fields,
            start=day,
            end=pd.to_datetime(day) + pd.Timedelta(days=nbr_days),
            wheres=[(selected_serie.tag_name, selected_serie.tag_value)],
        )
    if not df_dicts:
        st.warning("No data returned for this query.")
    else:
        data = df_dicts[selected_serie.measurement]

        st.line_chart(data)

        # st.write(data)

        df1 = data.copy()
        regular_index = pd.date_range(
            start=df1.index.min(), end=df1.index.max(), freq="15T"
        )
        st.write(regular_index)
        df = df1.reindex(regular_index).interpolate(method="time")
        st.write(data)
        df["ts"] = df.index.values.astype(np.int64) // 10**9

        time = df["ts"].to_numpy()
        time = (time - time[0]) / 60 / 60  # to hour, Normalize time to start at 0
        temp = df["temperature"].to_numpy()

        idx_start = 0
        idx_end = idx_start + 4 * 10

        st.write(df)

        x, y = time[idx_start:idx_end], temp[idx_start:idx_end]
        popt, std_err, y_pred = expfit(x, y)

        st.write(f"popt: {popt}, std_err: {std_err}")

        y_pred_full = exponential_func(time, *popt, t0=x[0])

        fig, ax = plt.subplots()
        ax.plot(time, temp, label="Data")
        ax.plot(time, y_pred_full, label="Exponential Fit", linestyle="--")

        st.pyplot(fig)
