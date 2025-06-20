# utitlity functions

import json
import os
import re
import shutil
import numpy as np
import scipy
import xarray as xr

# Helpers


def load_json_with_comments(filename):
    with open(filename, "r") as file:
        content = file.read()
    content = re.sub(r"//.*", "", content)
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    return json.loads(content)


def save_json_to_file(data, filename):
    with open(filename, "w") as file:
        json.dump(data, file, indent=4)


def oggm_nc_to_igm_nc(oggm_nc_file, igm_nc_file, thickness):
    ds_oggm = xr.open_dataset(oggm_nc_file, mode="r+")

    # Rename the vars for IGM inversion
    rename_map = {
        "topo": "usurf",
        "glacier_mask": "icemask",
        thickness: "thk",
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
