#==========================================================#
# Shoreline extraction from satellite images
#==========================================================#

# load modules
import os, sys
COASTSAT = os.path.expanduser('~/canonical-project-repos/CoastSat')
sys.path.insert(0, COASTSAT)
os.chdir(COASTSAT)
import numpy as np
import pickle
import warnings
warnings.filterwarnings("ignore")
import matplotlib.pyplot as plt
from matplotlib import gridspec
plt.ion()
import pandas as pd
from scipy import interpolate
from scipy import stats
from datetime import datetime, timedelta
import pytz
import json
from pyproj import CRS
from coastsat import SDS_download, SDS_preprocess, SDS_shoreline, SDS_tools, SDS_transects

# authenticate GEE with project name (YOU NEED TO INPUT YOUR OWN PROJECT NAME)
project_name = 'msc-erp-490313' # to get this value, run in the terminal "gcloud config get-value project"
SDS_download.authenticate_and_initialize(project_name)

# region of interest (longitude, latitude in WGS84)
polygon = [[[-0.20, 53.57],
            [0.15, 53.57],
            [0.15, 54.12],
            [-0.20, 54.12],
            [-0.20, 53.57],]]

# convert polygon to a smallest rectangle (sides parallel to coordinate axes)
polygon = SDS_tools.smallest_rectangle(polygon)

# date range
dates = ['1990-01-01', '2024-12-01']

# satellite missions
sat_list = ['L5','L7','L8','L9','S2']
# name of the site
sitename = 'HOLDERNESS'

# filepath where data will be stored
filepath_data = os.path.join(os.getcwd(), 'data')

# put all the inputs into a dictionnary
inputs = {
    'polygon': polygon,
    'dates': dates,
    'sat_list': sat_list,
    'sitename': sitename,
    'filepath': filepath_data,
    # 'LandsatWRS': '089083',
    # 'S2tile': '56HLH',
        }

# 2. Retrieve images

# retrieve satellite images from GEE
metadata = SDS_download.retrieve_images(inputs)