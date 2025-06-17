# Create OGGM projections using the initial geometries, mass balance calibration and synthetic climate data

import os
import shutil
import oggm.cfg as cfg
from oggm import workflow, DEFAULT_BASE_URL, tasks
import xarray as xr

TEMP_WD = "forward-runs/temp"
RGI_ID = ["RGI60-11.01450"]

start_year = 2000
end_year = 2500

thicknesses = [
    "millan_ice_thickness",
    "consensus_ice_thickness",
    "cook23_ice_thickness",
    "oggm_inv_distributed",
]

calibs = [
    "informed_threestep",
    "order_husshock",
    "meltf_only",
]

climate_file = "climate-background/simulation_climate.nc"
grid_file = "initial-geometries/res/glacier_grid.json"
thicknesses_file = "initial-geometries/res/gridded_data.nc"
outlines_file = "initial-geometries/res/outlines.tar.gz"
calibrations_path = "mass-balance-calibrations/res"

OUT_FOLDER_NAME = "simulation_res"

sliding = False


def main():
    cfg.initialize()

    cfg.PATHS["working_dir"] = TEMP_WD

    # Get a new gdir
    gdir = workflow.init_glacier_directories(RGI_ID, prepro_base_url=DEFAULT_BASE_URL, from_prepro_level=4)[0]

    # Delete everyting in the gdir (I don't know how to initialize an empty gdir...)
    print(gdir.dir)
    shutil.rmtree(gdir.dir)
    os.makedirs(gdir.dir)

    # Copy the previously generated files for the simulation
    shutil.copy(climate_file, gdir.dir + "/climate_historical.nc")  # we need to name it "historical" for sanity checks
    shutil.copy(thicknesses_file, gdir.dir + "/gridded_data.nc")
    shutil.copy(grid_file, gdir.dir + "/glacier_grid.json")
    shutil.copy(outlines_file, gdir.dir + "/outlines.tar.gz")

    # Run the simulations for every calibration and thickness
    for mb_calib in calibs:
        shutil.copy(calibrations_path + "/" + mb_calib + ".json", gdir.dir + "/mb_calib.json")

        for thickness in thicknesses:
            prepare_simulation(gdir, thk_var=thickness)

            if sliding:
                cfg.PARAMS["fs"] = 5.7e-20
                cfg.PARAMS["inversion_fs"] = 5.7e-20

            tasks.run_from_climate_data(
                gdir,
                ys=start_year,
                ye=end_year,
                climate_filename="climate_historical",
                climate_input_filesuffix="",
                output_filesuffix="_" + thickness + "_" + mb_calib,
                store_model_geometry=False,
            )

            if not os.path.exists("forward-runs/" + OUT_FOLDER_NAME):
                os.makedirs("forward-runs/" + OUT_FOLDER_NAME)

            file_name = "model_diagnostics" + "_" + thickness + "_" + mb_calib + ".nc"

            if sliding:
                out_name = "forward-runs/" + OUT_FOLDER_NAME + "/" + thickness + "_oggmslide_" + mb_calib + ".nc"
            else:
                out_name = "forward-runs/" + OUT_FOLDER_NAME + "/" + thickness + "_oggm_" + mb_calib + ".nc"

            shutil.copy(gdir.dir + "/" + file_name, out_name)

    # Clean the gdir
    shutil.rmtree(gdir.dir)


def print_volumes(path):
    for mb_calib in calibs:
        for thickness in thicknesses:
            for i in ["oggm", "oggmslide"]:
                ds = xr.open_dataset(path + "/" + thickness + "_" + i + "_" + mb_calib + ".nc")
                print(thickness + "_" + i + "_" + mb_calib + ".nc", end=" ")
                print(ds["volume_m3"].values[500] / 10e8)


def prepare_simulation(gdir, thk_var):
    # Bin elevations
    tasks.elevation_band_flowline(gdir, bin_variables=[thk_var], preserve_totals=[True])
    tasks.fixed_dx_elevation_band_flowline(gdir, bin_variables=[thk_var], preserve_totals=[True])
    # -> Inversion_flowlines.pkl + 2x xxx.csv

    # Calculate downstream
    tasks.compute_downstream_line(gdir)
    tasks.compute_downstream_bedshape(gdir)
    # -> Creates downstream_line.pkl from inversion_flowlines.pkl

    tasks.init_present_time_glacier(gdir, use_binned_thickness_data=thk_var)
    # -> Creates the model_flowlines.pkl


#main()

path = "forward-runs/" + OUT_FOLDER_NAME
print_volumes(path)
