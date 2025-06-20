#!/bin/bash

export TF_DEVICE_MIN_SYS_MEMORY_IN_MB=300
source activate igm
igm_run --param_file $1

rm params_saved.json
rm costs.dat
rm optimize.nc
rm rms_std.dat
rm clean.sh
