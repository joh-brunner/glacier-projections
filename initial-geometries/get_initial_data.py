# This script uses the OGGM shop to generate a nc-file containing initial data for both IGM and OGGM
# We do not need any duplicate fields, because the individual nc files for forward simulations are created later on
# The initial geometries include data from Farinotti, Millan and Cook from the OGGM shop (where available)
# Moreover, IGM and OGGM inversions with default parameter settings are carried out to generate additional ice thickness options
# Code is based on Fabien Maussion's code in IGM oggm shop module

import os
import shutil
import subprocess
import sys
import numpy as np
import oggm.cfg as cfg
import oggm.utils as utils
import oggm.workflow as workflow
import oggm.tasks as tasks
import xarray as xr

# Import utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from common.utils import *

if len(sys.argv) <= 1:
    RGI_ID = "RGI60-11.01450"
else:
    RGI_ID = sys.argv[1]

NO_SPINUP_URL = "https://cluster.klima.uni-bremen.de/~oggm/gdirs/oggm_v1.6/L3-L5_files/2023.3/elev_bands/W5E5"

TEMP_WD = "initial-geometries/temp"
TEMP_WD_OGGM_INVERSION = "initial-geometries/temp_inver"

IGM_INVERSION_PARAM_FILE = "initial-geometries/igm_inv/igm_inv_params.json"
IGM_INVERSION_BASH_SCRIPT = "initial-geometries/igm_inv/igm_run.sh"
TEMP_IGM_NC = "initial-geometries/igm_inv/temp_igm.nc"

OUT_FOLDER_NAME = "res/" + RGI_ID
FILES_TO_STORE = ["gridded_data.nc", "glacier_grid.json", "outlines.tar.gz"]

ADD_IGM_INVERSION = True  # disable for debug


def main():
    if os.path.basename(os.getcwd()) != "glacier-projections":
        print("Error: The parent directory must be 'glacier-projections'. Exiting.")
        sys.exit(1)

    initialize_oggm(TEMP_WD)

    rgi_ids = get_outlines()

    # Init glacier dir
    gdirs = workflow.init_glacier_directories(rgi_ids, reset=True, force=True)
    gdir = gdirs[0]

    # Grid and DEM
    tasks.define_glacier_region(gdir, source="DEM3")
    tasks.simple_glacier_masks(gdir)

    # Consensus, Millan, Cook
    add_thicknesses_from_shop(gdirs)
    add_additional_data_for_igm_inversion(gdirs)

    # OGGM inversion from another temporary gdir (level 3)
    add_oggm_inversion_from_server(gdir)

    # Carry out IGM inversion and add the resulting thickness
    if ADD_IGM_INVERSION:
        add_igm_inversion(gdir)

    # Set all thicknesses to NAN outside the mask
    set_outside_to_nan(gdir)

    # Rename cook var so that every thickness field contains three words
    rename_cook_var(gdir)

    # Copy the files and delete the temporary gdir
    if not os.path.exists("initial-geometries/" + OUT_FOLDER_NAME):
        os.makedirs("initial-geometries/" + OUT_FOLDER_NAME)
    for file in FILES_TO_STORE:
        shutil.copy(gdir.dir + "/" + file, "initial-geometries/" + OUT_FOLDER_NAME + "/" + file)
    shutil.rmtree(TEMP_WD)


def initialize_oggm(WD):
    # Initialize OGGM and set up the default run parameters
    cfg.initialize()

    cfg.PARAMS["continue_on_error"] = False
    cfg.PARAMS["use_multiprocessing"] = False
    cfg.PARAMS["use_intersects"] = False

    # Where to store the data for the run - should be somewhere you have access to
    cfg.PATHS["working_dir"] = WD


def get_outlines():
    rgi_ids = utils.get_rgi_glacier_entities([RGI_ID], version = "62")
    return rgi_ids


def add_thicknesses_from_shop(gdirs):

    from oggm.shop.millan22 import thickness_to_gdir

    try:
        workflow.execute_entity_task(thickness_to_gdir, gdirs)

    except ValueError:
        print("No millan22 thk data available!")

    from oggm.shop import bedtopo

    workflow.execute_entity_task(bedtopo.add_consensus_thickness, gdirs)

    if gdirs[0].rgi_region == "11":
        from oggm.shop import cook23

        workflow.execute_entity_task(cook23.cook23_to_gdir, gdirs, vars=["thk"])


def add_additional_data_for_igm_inversion(gdirs):
    from oggm.shop import hugonnet_maps

    workflow.execute_entity_task(hugonnet_maps.hugonnet_to_gdir, gdirs)

    from oggm.shop.millan22 import velocity_to_gdir

    workflow.execute_entity_task(velocity_to_gdir, gdirs)


def add_oggm_inversion_from_server(gdir):
    cfg.PATHS["working_dir"] = TEMP_WD_OGGM_INVERSION

    # Get the pre-processed glacier directories
    inversion_gdir = workflow.init_glacier_directories(RGI_ID, prepro_base_url=NO_SPINUP_URL, from_prepro_level=3, reset=True, force=True)[0]

    # Thickness from inversion to 2D Field
    tasks.distribute_thickness_per_altitude(inversion_gdir)

    # Copy to results nc
    copy_variable_between_netcdfs(inversion_gdir.dir + "/gridded_data.nc", gdir.dir + "/gridded_data.nc", "distributed_thickness", "oggm_inv_distributed")

    # Clean gdir
    shutil.rmtree(TEMP_WD_OGGM_INVERSION)


def add_igm_inversion(gdir):
    # We need to rename the variables in the nc for IGM
    oggm_nc_to_igm_nc(gdir.dir + "/gridded_data.nc", TEMP_IGM_NC)

    # Run igm inversion (includes cleaning of temp files)
    subprocess.run([IGM_INVERSION_BASH_SCRIPT, IGM_INVERSION_PARAM_FILE])

    # Copy thickness from IGM inversion to the main nc file
    copy_variable_between_netcdfs("geology-optimized.nc", gdir.dir + "/gridded_data.nc", "thk", "igm_inv_thickness")

    # Clean
    os.remove("geology-optimized.nc")
    os.remove(TEMP_IGM_NC)


def set_outside_to_nan(gdir):
    ds_res = xr.open_dataset(gdir.dir + "/gridded_data.nc", mode="r+")
    ds_res["millan_ice_thickness"] = ds_res["millan_ice_thickness"].where(ds_res["glacier_mask"] != 0, np.nan)
    if ADD_IGM_INVERSION:
        ds_res["igm_inv_thickness"] = ds_res["igm_inv_thickness"].where(ds_res["glacier_mask"] != 0, np.nan)
    if "cook23_thk" in ds_res:
        ds_res["cook23_thk"] = ds_res["cook23_thk"].where(ds_res["glacier_mask"] != 0, np.nan)
    ds_res.to_netcdf(gdir.dir + "/gridded_data.nc", mode="a")
    ds_res.close()


def rename_cook_var(gdir):
    ds = xr.open_dataset(gdir.dir + "/gridded_data.nc", mode="r+")
    ds.load()  # Load all into memory
    ds.close()  # Close file handle before overwriting

    if "cook23_thk" in ds:
        ds = ds.rename({"cook23_thk": "cook23_ice_thickness"})

    ds.to_netcdf(gdir.dir + "/gridded_data.nc", mode="w")


main()
