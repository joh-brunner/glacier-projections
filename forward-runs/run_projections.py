# Create OGGM projections using the initial geometries, mass balance calibration and synthetic climate data

import os
import shutil
import subprocess
import sys
import oggm.cfg as cfg
from oggm import workflow, DEFAULT_BASE_URL, tasks
import xarray as xr

# toDo: Add IGM model import?

# Import utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from common.utils import *

RGI_ID = ["RGI60-11.01450"]

start_year = 2000
end_year = 2100

thicknesses = [
    "millan_ice_thickness",
    "consensus_ice_thickness",
    "cook23_ice_thickness",
    "oggm_inv_distributed",
    "igm_inv_thickness",
]

calibs = [
    "informed_threestep",
    "order_husshock",
    "meltf_only",
]

# Shared data across the flow models
CLIMATE_FILE = "climate-background/simulation_climate.nc"
INITIAL_GEOMETRIES_FILE = "initial-geometries/res/gridded_data.nc"
CALIBS_PATH = "mass-balance-calibrations/res"
OUT_FOLDER_NAME = "simulation_res"

# IGM
TEMP_IGM_NC = "forward-runs/test.nc"
IGM_PARAMS_FORWARD = "forward-runs/igm_forward/params_ti.json"
IGM_RUN_SH = "forward-runs" + "/igm_run.sh"

# OGGM
TEMP_WD = "forward-runs/temp"
OUTLINES_FILE = "initial-geometries/res/outlines.tar.gz"
GRID_FILE = "initial-geometries/res/glacier_grid.json"


def main():
    gdir = init_oggm_gdir()

    for thickness in thicknesses:
        for calib in calibs:
            print("Processing " + thickness + " | " + calib)
            oggm_forward(thickness, calib, gdir)
            igm_forward(thickness, calib)

    # Clean the gdir
    shutil.rmtree(gdir.dir)


def igm_forward(thickness, calib, detailed=False):
    print("Processing IGM")
    oggm_nc_to_igm_nc(INITIAL_GEOMETRIES_FILE, TEMP_IGM_NC, thickness)

    params = load_json_with_comments(IGM_PARAMS_FORWARD)
    params["lncd_input_file"] = TEMP_IGM_NC
    # params["iflo_emulator"] = inversion_dir + "/iceflow-model"
    params["iflo_emulator"] = ""

    out_file_name = "forward-runs/" + OUT_FOLDER_NAME + "/" + thickness + "_igm_" + calib + ".nc"
    params["wts_output_file"] = out_file_name

    calib_file = CALIBS_PATH + "/" + calib + ".json"
    params["smb_mb_calib_file"] = calib_file
    params["clim_mb_calib_file"] = calib_file
    params["clim_forward_climate_file"] = CLIMATE_FILE

    params["time_start"] = start_year
    params["time_end"] = end_year
    params["time_save"] = 1.0

    if detailed:
        params["modules_postproc"] = ["write_ts", "print_info", "write_ncdf"]
        params["wncd_vars_to_save"] = [
            "usurf",
            "thk",
            "slidingco",
            "velsurf_mag",
            "velsurfobs_mag",
            "divflux",
            "icemask",
            "arrhenius",
            "thkobs",
            "smb",
            "volume",
            "meanprec",
            "meantemp",
        ]
        params["wncd_output_file"] = "forward-runs/" + OUT_FOLDER_NAME + "/" + thickness + "_igm_" + "test_vars" + ".nc"

    save_json_to_file(params, "forward-runs" + "/params_run.json")

    # Run
    result = subprocess.run([IGM_RUN_SH, "forward-runs" + "/params_run.json"])
    print("Output:", result.stdout)
    print("Error:", result.stderr)
    print("Return Code:", result.returncode)

    os.remove(TEMP_IGM_NC)


def oggm_forward(thickness, mb_calib, gdir, sliding=False):
    shutil.copy(CALIBS_PATH + "/" + mb_calib + ".json", gdir.dir + "/mb_calib.json")
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


def init_oggm_gdir():
    cfg.initialize()

    cfg.PATHS["working_dir"] = TEMP_WD

    # Get a new gdir
    gdir = workflow.init_glacier_directories(RGI_ID, prepro_base_url=DEFAULT_BASE_URL, from_prepro_level=4)[0]

    # Delete everyting in the gdir (I don't know how to initialize an empty gdir...)
    print(gdir.dir)
    shutil.rmtree(gdir.dir)
    os.makedirs(gdir.dir)

    # Copy the previously generated files for the simulation
    shutil.copy(CLIMATE_FILE, gdir.dir + "/climate_historical.nc")  # we need to name it "historical" for sanity checks
    shutil.copy(INITIAL_GEOMETRIES_FILE, gdir.dir + "/gridded_data.nc")
    shutil.copy(GRID_FILE, gdir.dir + "/glacier_grid.json")
    shutil.copy(OUTLINES_FILE, gdir.dir + "/outlines.tar.gz")
    return gdir


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


main()

# path = "forward-runs/" + OUT_FOLDER_NAME
# print_volumes(path)
