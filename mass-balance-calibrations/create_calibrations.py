# Here we load another default Glacier Directory (level 3) and carry out three different TI model calibrations
# One is the default OGGM informed threestep calibration
# Second is based on the order of parameter adjustement from Huss and Hock 2015
# Third is an experimental calibration where only ddf (melt_f) is adjusted and precip_f (1) and temp_bias (0) are kept constant

import os
import shutil
import sys
import oggm.cfg as cfg
import oggm.workflow as workflow

if len(sys.argv) <= 1:
    RGI_ID = "RGI60-11.01450"
else:
    RGI_ID = sys.argv[1]

TEMP_WD = "mass-balance-calibrations/temp"

NO_SPINUP_URL = "https://cluster.klima.uni-bremen.de/~oggm/gdirs/oggm_v1.6/L3-L5_files/2023.3/elev_bands/W5E5"

OUT_FOLDER_NAME = "res/" + RGI_ID


def main():
    if os.path.basename(os.getcwd()) != "glacier-projections":
        print("Error: The parent directory must be 'glacier-projections'. Exiting.")
        sys.exit(1)

    cfg.initialize()

    cfg.PATHS["working_dir"] = TEMP_WD

    # Get the pre-processed glacier directories
    mb_gdir = workflow.init_glacier_directories(RGI_ID, prepro_base_url=NO_SPINUP_URL, from_prepro_level=3, reset=True, force=True)[0]

    # 1. Informed threestep
    workflow.tasks.mb_calibration_from_geodetic_mb(mb_gdir, filesuffix="_informed_threestep", informed_threestep=True)

    # Disable the informed calibration for additional calibrations
    cfg.PARAMS["use_temp_bias_from_file"] = False
    cfg.PARAMS["use_winter_prcp_fac"] = False
    cfg.PARAMS["prcp_fac"] = 1

    #cfg.PARAMS["melt_f"] = 4.5
    #cfg.PARAMS["melt_f_min"] = 2.65
    #cfg.PARAMS["melt_f_max"] = 6.75
    cfg.PARAMS["melt_f"] = 6
    cfg.PARAMS["melt_f_min"] = 3.5
    cfg.PARAMS["melt_f_max"] = 9

    cfg.PARAMS["prcp_fac"] = 1.5
    cfg.PARAMS["prcp_fac_min"] = 0.8
    cfg.PARAMS["prcp_fac_max"] = 2

    # 2. Here we keep the standard ranges from OGGM for W5E5 climate but use the calibration order from Huss and Hock 2025
    workflow.tasks.mb_calibration_from_geodetic_mb(
        mb_gdir,
        calibrate_param1="prcp_fac",
        calibrate_param2="melt_f",
        calibrate_param3="temp_bias",
        filesuffix="_order_husshock",
    )

    # 3. This is a rather experimental calibration where only the the ddf is adjusted and no climate correction is applied
    #    Min and max values are from Schuster 2023
    workflow.tasks.mb_calibration_from_geodetic_mb(
        mb_gdir,
        calibrate_param1="melt_f",
        calibrate_param2="prcp_fac",
        calibrate_param3="temp_bias",
        filesuffix="_meltf_only",
    )

    # Store the results
    if not os.path.exists("mass-balance-calibrations/" + OUT_FOLDER_NAME):
        os.makedirs("mass-balance-calibrations/" + OUT_FOLDER_NAME)
    shutil.copy(mb_gdir.dir + "/mb_calib_informed_threestep.json", "mass-balance-calibrations/" + OUT_FOLDER_NAME + "/informed_threestep.json")
    shutil.copy(mb_gdir.dir + "/mb_calib_meltf_only.json", "mass-balance-calibrations/" + OUT_FOLDER_NAME + "/meltf_only.json")
    shutil.copy(mb_gdir.dir + "/mb_calib_order_husshock.json", "mass-balance-calibrations/" + OUT_FOLDER_NAME + "/order_husshock.json")

    # Clean gdir
    shutil.rmtree(TEMP_WD)


main()
