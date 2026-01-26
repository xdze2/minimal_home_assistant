import click
from miniha.influx_interface import InfluxInterface

from miniha.config import config
from pathlib import Path
import pandas as pd


@click.command()
@click.option("-m", "measurement", default=None, help="Measurement name to query.")
@click.option("-d", "day", default=None, help="Day.")
def main(measurement: str = None, day: str = None) -> None:
    print(f"Connecting to InfluxDB at {config.INFLUX_HOST}:{config.INFLUX_PORT} ...")
    influx_client = InfluxInterface(
        host=config.INFLUX_HOST,
        port=config.INFLUX_PORT,
        database=config.INFLUX_DB,
    )

    measurements = influx_client.list_measurements()
    click.echo(f"Measurements: {", ".join(measurements)}")

    if measurement is not None:
        click.echo(f"\nQuerying records for measurement '{measurement}':")

        df_dicts = influx_client.query_df(
            measurement=measurement,
            field_list=[
                "temperature",
                "name",
            ],
            start=day,
            end=pd.to_datetime(day) + pd.Timedelta(days=1),
            group_by="name",
        )

        output_dir = "out"
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        for key, df in df_dicts.items():
            click.echo(f"\nGroup: {key}")
            click.echo(key)
            name = key[1][0][1].replace("/", "_")
            print(f"Exporting data for {name} to CSV...")
            df.to_csv(
                Path(output_dir, f"{measurement}_{key[0]}_{name}.csv"),
                index=True,
                index_label="time",
            )


if __name__ == "__main__":
    main()
