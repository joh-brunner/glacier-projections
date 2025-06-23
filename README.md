# glacier-projections

## 🛠️ Prerequisites

- [ ] Forked IGM Installation, including the option to use custom climate and mb calib files
- [ ] Forked OGGM Installation, including the option to run from custom thickness without previous inversion

### 🔧 Step 1: Load initial geometries

**Script:**  
initial-geometries/get_initial_data.py

**Output:**
- [ ] glacier_grid.json
- [ ] outlines.tar.gz
- [ ] gridded_data.nc with up to 5 different initial thicknesses

### 🔧 Step 2: Create climatic background

**Script:**  
climate-background/create_climate_file.py

**Output:**
simulation_climate.nc representing the climate from 1990 to 2020

### 🔧 Step 3: Create the TI model calibrations 

**Script:**  
mass-balance-calibrations/create_calibrations.py

**Output:**
- [ ] informed_threestep.json
- [ ] meltf_only.json
- [ ] order_husshock.json

### 🔧 Step 4: Run the projections

**Script:**  
forward-runs/run_projections.py

**Input:**
All previously generated files

**Output:**
- [ ] forward-runs/simulation_res
- [ ] NC-Files for every run containing volume and area evolution data

### -> fully automated in workflow.py, only depending on RGI ID
