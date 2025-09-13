import os
import subprocess
import sys

RGI_ID = "RGI60-09.00971"


def main():
    if os.path.basename(os.getcwd()) != "glacier-projections":
        print("Error: The parent directory must be 'glacier-projections'. Exiting.")
        sys.exit(1)

    subprocess.run(["python", "initial-geometries/get_initial_data.py", RGI_ID])

    subprocess.run(["python", "climate-background/create_climate_file.py", RGI_ID])

    subprocess.run(["python", "mass-balance-calibrations/create_calibrations.py", RGI_ID])

    subprocess.run(["python", "forward-runs/run_projections.py", RGI_ID])


main()
