# Here we load a default Glacier Directory (level 3) and take the historical climate file
# We create a new climate file for forward runs (years 2000-3000) by extending the climate from 1990-2019
# We add some (monthly) randomness to avoid cyclicity in the data
# We end up with synthetic climate data representing the conditions (including variability) from 1990 to 2019

import shutil
import cftime
import numpy as np
import oggm.cfg as cfg
import oggm.workflow as workflow
import xarray as xr

NO_SPINUP_URL = "https://cluster.klima.uni-bremen.de/~oggm/gdirs/oggm_v1.6/L3-L5_files/2023.3/elev_bands/W5E5"

TEMP_WD = "climate-background/temp"
RGI_ID = ["RGI60-11.01450"]

# Scaling factor of the standard distribution for random extension
# Use 0 for the monthly mean of climate variables
sd_scale = 1

seed = 0  # Random seed

reference_climate_period_start = "1990-01-01"
reference_climate_period_end = "2019-12-01"

synthetic_start_date = "2000-01-01"
synthetic_end_date = "2999-12-01"

simulation_climate_file = "climate-background/simulation_climate.nc"


def main():
    cfg.initialize()

    cfg.PATHS["working_dir"] = TEMP_WD

    climate_gdir = workflow.init_glacier_directories(RGI_ID, prepro_base_url=NO_SPINUP_URL, from_prepro_level=3, reset=True, force=True)[0]

    simulation_climate(climate_gdir.dir + "/climate_historical.nc", simulation_climate_file)

    check_climate_files(climate_gdir)

    # Clean gdir
    shutil.rmtree(TEMP_WD)


def simulation_climate(climate_data_file, out):
    ds = xr.open_dataset(climate_data_file)

    # Convert strings to numpy.datetime64
    start = np.datetime64(reference_climate_period_start)
    end = np.datetime64(reference_climate_period_end)

    # Get min/max from dataset
    min_time = ds.time.values[0]
    max_time = ds.time.values[-1]

    # Bounds check
    if start < min_time or end > max_time:
        raise ValueError(f"Requested time range ({start} to {end}) is outside of dataset range ({min_time} to {max_time})")

    selected_time = ds.sel(time=slice(reference_climate_period_start, reference_climate_period_end))

    # Generate a range of dates (1000 years)
    year, month, day = map(int, synthetic_end_date.split("-"))
    end_date = cftime.DatetimeGregorian(year, month, day)

    year, month, day = map(int, synthetic_start_date.split("-"))
    start_date = cftime.DatetimeGregorian(year, month, day)

    monthly_dates = [start_date]
    while monthly_dates[-1] < end_date:
        year, month = monthly_dates[-1].year, monthly_dates[-1].month
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1
        monthly_dates.append(cftime.DatetimeGregorian(next_year, next_month, 1))

    # Group climate data by month
    climatology_mean = selected_time.groupby("time.month").mean()
    climatology_std = selected_time.groupby("time.month").std()

    # Generate synthetic future data
    future_prcp = []
    future_temp = []
    np.random.seed(seed)

    for t in monthly_dates:
        month = t.month

        # Generate random variation based on monthly climate data
        temp_val = np.random.normal(loc=climatology_mean.temp.sel(month=month), scale=sd_scale * (climatology_std.temp.sel(month=month)))
        future_temp.append(temp_val)

        prcp_val = np.random.normal(loc=climatology_mean.prcp.sel(month=month), scale=sd_scale * climatology_std.prcp.sel(month=month))
        prcp_val = max(0, prcp_val)  # prcp cannot be negative
        future_prcp.append(prcp_val)

    # Convert to arrays
    future_prcp = np.array(future_prcp)
    future_temp = np.array(future_temp)

    # Create the new extended dataset
    ds_synthetic = xr.Dataset(
        {
            "prcp": (["time"], future_prcp),
            "temp": (["time"], future_temp),
        },
        coords={"time": np.concatenate([monthly_dates])},
        attrs=ds.attrs,  # Keep original metadata
    )
    ds_synthetic.attrs["yr_0"] = int(reference_climate_period_start[:4])
    ds_synthetic.attrs["yr_1"] = int(reference_climate_period_end[:4])
    ds_synthetic.to_netcdf(out)


def check_climate_files(climate_gdir):
    # Check if the monthly mean of the synthetic climate equals the original data

    ds_historic = xr.open_dataset(climate_gdir.dir + "/climate_historical.nc")
    ds_synthetic = xr.open_dataset(simulation_climate_file)

    hist_values = ds_historic.sel(time=slice(reference_climate_period_start, reference_climate_period_end))

    synt_values = ds_synthetic

    # Check for January
    print(np.mean(hist_values["prcp"].values[::12]))
    print(np.mean(synt_values["prcp"].values[::12]))
    print(np.mean(hist_values["temp"].values[::12]))
    print(np.mean(synt_values["temp"].values[::12]))


main()
