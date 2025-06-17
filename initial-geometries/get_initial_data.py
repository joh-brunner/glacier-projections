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
import scipy
import oggm.cfg as cfg
import oggm.utils as utils
import oggm.workflow as workflow
import oggm.tasks as tasks
import xarray as xr

NO_SPINUP_URL = "https://cluster.klima.uni-bremen.de/~oggm/gdirs/oggm_v1.6/L3-L5_files/2023.3/elev_bands/W5E5"

RGI_ID = ["RGI60-06.00416"]
RGI_ID = ["RGI60-11.01450"]

TEMP_WD = "initial-geometries/temp"
TEMP_WD_OGGM_INVERSION = "initial-geometries/temp_inver"

IGM_INVERSION_PARAM_FILE = "initial-geometries/igm_inv/igm_inv_params.json"
IGM_INVERSION_BASH_SCRIPT = "initial-geometries/igm_inv/igm_run.sh"
TEMP_IGM_NC = "initial-geometries/igm_inv/temp_igm.nc"

OUT_FOLDER_NAME = "res"
FILES_TO_STORE = ["gridded_data.nc", "glacier_grid.json", "outlines.tar.gz"]

# toDo: Add IGM inversion again


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

    # OGGM inversion from another temporary gdir (level 4)
    add_oggm_inversion_from_server(gdir)

    # Carry out IGM inversion and add the resulting thickness
    # add_igm_inversion()

    # Set all thicknesses to NAN outside the mask
    set_outside_to_nan(gdir)

    rename_cook_var(gdir)

    # Copy the files and delete the temporary gdir
    if not os.path.exists("initial-geometries/" + OUT_FOLDER_NAME):
        os.makedirs("initial-geometries/" + OUT_FOLDER_NAME)
    for file in FILES_TO_STORE:
        shutil.copy(gdir.dir + "/" + file, "initial-geometries/" + OUT_FOLDER_NAME + "/" + file)
    shutil.rmtree(TEMP_WD)


def rename_cook_var(gdir):
    ds = xr.open_dataset(gdir.dir + "/gridded_data.nc", mode="r+")
    ds.load()  # Load all into memory
    ds.close()  # Close file handle before overwriting

    if "cook23_thk" in ds:
        ds = ds.rename({"cook23_thk": "cook23_ice_thickness"})

    ds.to_netcdf(gdir.dir + "/gridded_data.nc", mode="w")


def set_outside_to_nan(gdir):
    ds_res = xr.open_dataset(gdir.dir + "/gridded_data.nc", mode="r+")
    ds_res["millan_ice_thickness"] = ds_res["millan_ice_thickness"].where(ds_res["glacier_mask"] != 0, np.nan)
    # ds_res["igm_inv_thickness"] = ds_res["igm_inv_thickness"].where(ds_res["glacier_mask"] != 0, np.nan)
    if "cook23_thk" in ds_res:
        ds_res["cook23_thk"] = ds_res["cook23_thk"].where(ds_res["glacier_mask"] != 0, np.nan)
    ds_res.to_netcdf(gdir.dir + "/gridded_data.nc", mode="a")
    ds_res.close()


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


def get_outlines():
    rgi_ids = utils.get_rgi_glacier_entities(RGI_ID)
    return rgi_ids


def initialize_oggm(WD):
    # Initialize OGGM and set up the default run parameters
    cfg.initialize()

    cfg.PARAMS["continue_on_error"] = False
    cfg.PARAMS["use_multiprocessing"] = False
    cfg.PARAMS["use_intersects"] = False

    # Where to store the data for the run - should be somewhere you have access to
    cfg.PATHS["working_dir"] = WD


def oggm_nc_to_igm_nc(oggm_nc_file, igm_nc_file):
    ds_oggm = xr.open_dataset(oggm_nc_file, mode="r+")

    # Rename the vars for IGM inversion
    rename_map = {
        "topo": "usurf",
        "glacier_mask": "icemask",
        "consensus_ice_thickness": "thk",
        "millan_vx": "uvelsurfobs",
        "millan_vy": "vvelsurfobs",
        "hugonnet_dhdt": "dhdt",
    }
    ds_igm = ds_oggm[list(rename_map.keys())].rename(rename_map)

    # Apply masks and set NaNs for IGM Inversion
    ds_igm["thkobs"] = xr.full_like(ds_igm["thk"], np.nan)
    ds_igm["thk"] = ds_igm["thk"].fillna(0)
    ds_igm["thkinit"] = ds_igm["thk"]
    ds_igm["thkinit"] = ds_igm["thkinit"].fillna(0)

    ds_igm["icemaskobs"] = ds_igm["icemask"]
    ds_igm["usurfobs"] = ds_igm["usurf"]

    ds_igm["uvelsurfobs"] = ds_igm["uvelsurfobs"].where(ds_igm["icemask"] != 0, 0)
    ds_igm["vvelsurfobs"] = ds_igm["vvelsurfobs"].where(ds_igm["icemask"] != 0, 0)
    ds_igm["dhdt"] = ds_igm["dhdt"].where(ds_igm["icemask"] != 0, 0)
    ds_igm["dhdt"] = ds_igm["dhdt"].fillna(0)

    # Convert ice mask datatype
    ds_igm = ds_igm.assign({"icemask": ds_igm["icemask"].astype(np.float32)})
    ds_igm = ds_igm.assign({"icemaskobs": ds_igm["icemaskobs"].astype(np.float32)})

    # Smooth velocity fields
    smoothed_uvel = scipy.signal.medfilt2d(ds_igm["uvelsurfobs"].values, kernel_size=3)
    ds_igm = ds_igm.assign({"uvelsurfobs": (ds_igm["uvelsurfobs"].dims, smoothed_uvel)})
    smoothed_vvel = scipy.signal.medfilt2d(ds_igm["vvelsurfobs"].values, kernel_size=3)
    ds_igm = ds_igm.assign({"vvelsurfobs": (ds_igm["vvelsurfobs"].dims, smoothed_vvel)})

    # Flip the data horizontally (not sure why this is necessary, but it is...)
    flipped_vars = {}

    for var in ds_igm.data_vars:
        if ds_igm[var].ndim == 2 and "y" in ds_igm[var].dims:
            flipped = ds_igm[var].sel(y=slice(None, None, -1))
            flipped_vars[var] = flipped
        else:
            flipped_vars[var] = ds_igm[var]
    coords = dict(ds_igm.coords)
    if "y" in coords:
        coords["y"] = coords["y"][::-1]
    ds_flipped = xr.Dataset(flipped_vars, coords=coords, attrs=ds_igm.attrs)

    # Store input file for IGM inversion
    if os.path.exists(igm_nc_file):
        os.remove(igm_nc_file)
    ds_flipped.to_netcdf(igm_nc_file)

    # Close all nc-files
    ds_oggm.close()
    ds_igm.close()
    ds_flipped.close()


def copy_variable_between_netcdfs(source_file, target_file, source_variable_name, target_variable_name):
    ds_source = xr.open_dataset(source_file)
    ds_target = xr.open_dataset(target_file, mode="r+")
    var_data = ds_source[source_variable_name]
    ds_updated = ds_target.assign({target_variable_name: var_data})
    ds_updated.to_netcdf(target_file, mode="a")
    ds_source.close()
    ds_target.close()


def delete_folder(path):
    for entry in os.listdir(path):
        full_path = os.path.join(path, entry)
        if os.path.isfile(full_path) or os.path.islink(full_path):
            os.remove(full_path)
        elif os.path.isdir(full_path):
            shutil.rmtree(full_path)


main()
