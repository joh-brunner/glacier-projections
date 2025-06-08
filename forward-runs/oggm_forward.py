# Create OGGM projections using the initial geometries, mass balance calibration and synthetic climate data

import os
import shutil
import oggm.cfg as cfg
from oggm import GlacierDirectory
from oggm import utils
from oggm import workflow
from oggm import DEFAULT_BASE_URL
from oggm import tasks

# toDo: think about grid.json
# toDo: Check calib params is currently set to false
# toDo: Set paths to geometry files in constants


TEMP_WD = "forward-runs/temp"
RGI_ID = ["RGI60-11.01450"]

start_year = 2000
end_year = 2500

thicknesses = [
    "millan_ice_thickness",
    "consensus_ice_thickness",
    "cook23_thk",
    "oggm_inv_distributed",
]


def main():
    cfg.initialize()

    cfg.PATHS["working_dir"] = TEMP_WD

    # Get a new gdir
    gdir = workflow.init_glacier_directories(RGI_ID, prepro_base_url=DEFAULT_BASE_URL, from_prepro_level=4)[0]

    # Delete everyting in the gdir (I don't know how to initialize an empty gdir...)
    print(gdir.dir)
    shutil.rmtree(gdir.dir)
    os.makedirs(gdir.dir)

    # Copy the files for the simulation
    shutil.copy("climate-background/climate_long.nc", gdir.dir + "/climate_historical.nc")
    shutil.copy("initial-geometries/res.nc", gdir.dir + "/gridded_data.nc")
    shutil.copy("initial-geometries/res.json", gdir.dir + "/glacier_grid.json")
    shutil.copy("initial-geometries/outlines.tar.gz", gdir.dir + "/outlines.tar.gz")
    shutil.copy("mass-balance-calibrations/oggm_default_calib.json", gdir.dir + "/mb_calib.json")

    for thickness in thicknesses:
        prepare_simulation(gdir, thk_var=thickness)

        tasks.run_from_climate_data(
            gdir,
            ys=start_year,
            ye=end_year,
            climate_filename="climate_historical",
            climate_input_filesuffix="",
            output_filesuffix="_" + thickness,
            store_model_geometry=False,
        )

    # toDo: Export the results
    shutil.rmtree(gdir.dir)


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
