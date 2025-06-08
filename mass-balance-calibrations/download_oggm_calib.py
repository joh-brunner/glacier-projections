# Here we load a default Glacier Directory (level 4) and store the default (three-step) OGGM mass balance calibration

import shutil
import oggm.cfg as cfg
import oggm.workflow as workflow
from oggm import DEFAULT_BASE_URL

TEMP_WD = "mass-balance-calibrations/temp"
RGI_ID = ["RGI60-11.01450"]


def main():
    cfg.initialize()

    cfg.PATHS["working_dir"] = TEMP_WD

    # Get the pre-processed glacier directories
    mb_gdir = workflow.init_glacier_directories(RGI_ID, prepro_base_url=DEFAULT_BASE_URL, from_prepro_level=4, reset=True, force=True)[0]

    shutil.copy(mb_gdir.dir + "/mb_calib.json", "mass-balance-calibrations/oggm_default_calib.json")

    # Clean gdir
    shutil.rmtree(TEMP_WD)


main()
