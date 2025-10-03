import click
from miniha.influx_interface import InfluxInterface

from miniha.config import config




@click.command()
def main():
    influx = InfluxInterface(
        host=config.INFLUX_HOST,
        port=config.INFLUX_PORT,
        database=config.INFLUX_DB,
    )


    measurements = influx.list_measurements()
    click.echo("Measurements:")
    for m in measurements:
        click.echo(m)

    # if show_last:
    #     measurements = influx.list_measurements()
    #     for m in measurements:
    #         click.echo(f"\nMeasurement: {m}")
    #         df = influx.get_last_record_for_measurement(m)
    #         if df.empty:
    #             click.echo("No records found.")
    #         else:
    #             click.echo(df)

if __name__ == "__main__":
    main()

