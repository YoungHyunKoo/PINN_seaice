import pandas as pd
import glob, os
import matplotlib.pyplot as plt
import numpy as np
import numpy.ma as ma
import geopandas
import netCDF4
import h5py
import datetime as dt
import pyproj
from tqdm import tqdm
from pyproj import Proj, transform
from shapely.geometry import Polygon
import cartopy.crs as ccrs

from scipy.interpolate import griddata

import cdsapi
import xarray as xr
from urllib.request import urlopen

import pickle

global data_path
data_path = "D:\\PINN\\data"
# data_path = "C:\\Users\\yok223\\Research\\PINN\\data"

from scipy.ndimage.filters import gaussian_filter

def get_ice_motion(ncfile, i, sampling_size = 1):
# ncfile: input monthly ERA5 file (ncfile)
# field: input variable ('sst', 't2m', 'u10', 'v10')
# bounding_box: processed area (Ross Sea - Amundsen Sea)
# latlon_ib: geocoordinates of the iceberg (lat, lon)
# time_ib: date of the iceberg (datetime format)

    nc = netCDF4.Dataset(ncfile, 'r')
    keys = nc.variables.keys()
    fields = ['u', 'v']

    xs = np.array(nc.variables['x'])[::sampling_size]
    ys = np.array(nc.variables['y'])[::sampling_size]  
    xx, yy = np.meshgrid(xs, ys)
    lat = np.array(nc.variables['latitude'])[::sampling_size, ::sampling_size]
    lon = np.array(nc.variables['longitude'])[::sampling_size, ::sampling_size]

    days = np.array(nc.variables['time']).astype(float)

    for field in fields:                

        data2 = []       

        data = np.array(nc.variables[field][i][::sampling_size, ::sampling_size])
        # cm/s to km/day
        data[data == -9999] = np.nan
        data2.append(data*(3600*24/100000))                        

        data2 = np.array(data2) 
        data_mean = np.array([np.mean(data2, axis = 0)])

        # df[field] = data_mean.flatten()

        if field == "u":
            u = data2 # data_mean
            # u[np.isnan(u)] = 0
        elif field == "v":
            v = data2 # data_mean
            # v[np.isnan(v)] = 0   
    
    nc.close()
    
    u[np.isnan(u)] = 0
    v[np.isnan(v)] = 0
    
    # Apply Gaussian filter
    u = gaussian_filter(u, sigma = 3)
    v = gaussian_filter(v, sigma = 3)
    
    return xx, yy, lat, lon, u, v


def get_SIC(t1, xx, yy, dtype = "noaa", region = "NH"):
    ## Read SIC data (AMSR) ==================================================
    if dtype == "AMSR":
        h5file = data_path + "/{0}/SIC/AMSR_U2_L3_SeaIce25km_B04_{1}.he5".format(region, dt.datetime.strftime(t1, "%Y%m%d"))

        if os.path.exists(h5file):
            f = h5py.File(h5file)

            lat2 = f['HDFEOS']['GRIDS']['NpPolarGrid25km']['lat'][:]
            lon2 = f['HDFEOS']['GRIDS']['NpPolarGrid25km']['lon'][:]
            sic = f['/HDFEOS/GRIDS/NpPolarGrid25km/Data Fields/SI_25km_NH_ICECON_DAY'][:].astype(float)
            sic[sic <= 0] = 0
            sic[sic > 100] = 0

            # EPSG:4326 (WGS84); EPSG:3408 (NSIDC EASE-Grid North - Polar pathfinder sea ice movement)
            inProj = Proj('epsg:4326')  
            outProj = Proj('epsg:3408')
            xx2,yy2 = transform(inProj,outProj,lat2,lon2)
            grid_sic = griddata((xx2.flatten(), yy2.flatten()), sic.flatten(), (xx, yy), method='linear')
            grid_sic[np.isnan(grid_sic)] = 0
            return grid_sic * 0.01  # Change into 0-1

        else:
            print("Filename is NOT correct!")
            
    elif dtype == "noaa":
        ncfile = data_path + "/{0}/SIC_NOAA/seaice_conc_daily_{0}_{1}_f17_v04r00.nc".format(region, dt.datetime.strftime(t1, "%Y%m%d"))
        
        if os.path.exists(ncfile):
            nc = netCDF4.Dataset(ncfile, 'r')
            
            xx0 = np.array(nc.variables['xgrid'])
            yy0 = np.array(nc.variables['ygrid'])
            sic = np.array(nc.variables['cdr_seaice_conc'])[0] # CDR SIC
            # bt = np.array(nc.variables['nsidc_bt_seaice_conc'])[0] # BT SIC
            # nt = np.array(nc.variables['nsidc_nt_seaice_conc'])[0] # NT SIC
            
            sic[sic <= 0] = 0
            sic[sic > 1] = 0

            # ESPG:3411 (NSIDC Sea Ice Polar Stereographic North - SIC data)
            if region == "NH":
                inProj = Proj('epsg:3411')
                outProj = Proj('epsg:3408')
            elif region == "SH":
                inProj = Proj('epsg:3412')
                outProj = Proj('epsg:3409')
            xx1, yy1 = np.meshgrid(xx0, yy0)
            xx2,yy2 = transform(inProj,outProj,xx1,yy1)
            grid_sic = griddata((xx2.flatten(), yy2.flatten()), sic.flatten(), (xx, yy), method='linear')
            grid_sic[np.isnan(grid_sic)] = 0
            return grid_sic

        else:
            print("Filename is NOT correct!")

def retrieve_ERA5(year, region = "NH"):
    c = cdsapi.Client()
    # dataset to read
    dataset = 'reanalysis-era5-single-levels'
    # flag to download data
    download_flag = False
    # api parameters 
    if region == "NH":
        params = {
            'format': 'netcdf',
            'product_type': 'reanalysis',
            'variable': ['10m_u_component_of_wind', '10m_v_component_of_wind', '2m_temperature', 'sea_ice_cover'],
            'year':[str(year)],
            'month': ['01', '02', '03', '04', '05', '06','07', '08', '09','10', '11', '12'],
            'day': ['01', '02', '03',
                '04', '05', '06',
                '07', '08', '09',
                '10', '11', '12',
                '13', '14', '15',
                '16', '17', '18',
                '19', '20', '21',
                '22', '23', '24',
                '25', '26', '27',
                '28', '29', '30',
                '31',
                   ],
            'grid': [1, 0.5],
            'area': [90, -180, 50, 180]
            }
    
    elif region == "SH":
        params = {
            'format': 'netcdf',
            'product_type': 'reanalysis',
            'variable': ['10m_u_component_of_wind', '10m_v_component_of_wind', '2m_temperature', 'sea_ice_cover'],
            'year':[str(year)],
            'month': ['01', '02', '03', '04', '05', '06','07', '08', '09','10', '11', '12'],
            'day': ['01', '02', '03',
                '04', '05', '06',
                '07', '08', '09',
                '10', '11', '12',
                '13', '14', '15',
                '16', '17', '18',
                '19', '20', '21',
                '22', '23', '24',
                '25', '26', '27',
                '28', '29', '30',
                '31',
                   ],
            'time': ['12:00'],
            'grid': [1, 0.5],
            'area': [-50, -180, -90, 180]
            }

    # retrieves the path to the file
    fl = c.retrieve(dataset, params)

    # load into memory
    with urlopen(fl.location) as f:
        ds = xr.open_dataset(f.read())

    return ds

def rotate_vector(u, v, lon):
    angle = lon*np.pi/180 # rotation angle (radian)
    u2 = u*np.cos(angle) - v*np.sin(angle)
    v2 = u*np.sin(angle) + v*np.cos(angle)
    return u2, v2

def get_ERA5(ds, i, xx, yy, region = "NH"):
    lat3, lon3 = np.meshgrid(ds.latitude, ds.longitude)
    inProj = Proj('epsg:4326')
    if region == "NH":
        outProj = Proj('epsg:3408')
    elif region == "SH":
        outProj = Proj('epsg:3409')
        
    xx3,yy3 = transform(inProj,outProj,lat3,lon3)
    t2m = np.array(ds.t2m[i]).transpose()
    u10 = np.array(ds.u10[i]).transpose()
    v10 = np.array(ds.v10[i]).transpose()
    sic = np.array(ds.siconc[i]).transpose()
    
    u10, v10 = rotate_vector(u10, v10, lon3)
    
    grid_t2m = griddata((xx3.flatten(), yy3.flatten()), np.array(t2m).flatten(), (xx, yy), method='linear')
    grid_u10 = griddata((xx3.flatten(), yy3.flatten()), np.array(u10).flatten(), (xx, yy), method='linear')
    grid_v10 = griddata((xx3.flatten(), yy3.flatten()), np.array(v10).flatten(), (xx, yy), method='linear')
    grid_sic = griddata((xx3.flatten(), yy3.flatten()), np.array(sic).flatten(), (xx, yy), method='linear')
    
    grid_t2m[np.isnan(grid_t2m)] = 0
    grid_u10[np.isnan(grid_u10)] = 0
    grid_v10[np.isnan(grid_v10)] = 0
    grid_sic[np.isnan(grid_sic)] = 0
    
    return grid_t2m, grid_u10, grid_v10, grid_sic

def make_dataset(year, n_samples, ds, w = 1, datatype = "entire", region = "NH"):
    # ncfile = glob.glob("F:\\2022_Ross\\ERA5\\icemotion_daily_sh_25km_{0}*.nc".format(year))[0]
    ncfile = data_path + f"/{region}/Sea_ice_drift/icemotion_daily_nh_25km_{year}0101_{year}1231_v4.1.nc"
    nc = netCDF4.Dataset(ncfile, 'r')
    ## Adjust the number of training datasets ===========================
    days = np.array(nc.variables['time']).astype(float)[:]
    row, col = np.shape(np.array(nc.variables['latitude']))
    
    # Initialize grid input ==========================================
    grid_input = np.zeros([len(n_samples), row, col, 6])
    grid_output = np.zeros([len(n_samples), row, col, 3])
    
    first = True
    
    for i, idx in tqdm(enumerate(n_samples)):
        t1 = dt.datetime(1970, 1, 1) + dt.timedelta(days = days[idx])
        t2 = dt.datetime(1970, 1, 1) + dt.timedelta(days = days[idx]+1)  

        ## Read ice motion data ===========================================
        sampling_size = 1
        xx, yy, lat, lon, u, v = get_ice_motion(ncfile, idx, sampling_size)
        grid_u = np.mean(u, axis = 0)
        grid_v = np.mean(v, axis = 0) 

        ## Read SIC data ==================================================
        # grid_sic = get_SIC(t1, xx, yy, region = region)

        ## Read ERA5 data =================================================
        grid_t2m, grid_u10, grid_v10, grid_sic = get_ERA5(ds, idx, xx, yy, region = region)

        grid_input[i, :, :, 0] = grid_u / 50
        grid_input[i, :, :, 1] = grid_v / 50
        grid_input[i, :, :, 2] = grid_sic
        grid_input[i, :, :, 3] = (grid_t2m - 240)/(320 - 240) #Max temp = 320 K, Min temp = 240 K)
        grid_input[i, :, :, 4] = grid_u10 / 50
        grid_input[i, :, :, 5] = grid_v10 / 50

        _, _, _, _, u2, v2 = get_ice_motion(ncfile, idx+1, sampling_size)
        grid_u2 = np.mean(u2, axis = 0)
        grid_v2 = np.mean(v2, axis = 0) 
        grid_output[i, :, :, 0] = grid_u2 / 50
        grid_output[i, :, :, 1] = grid_v2 / 50
        # grid_sic2 = get_SIC(t2, xx, yy, region = region)
        _, _, _, grid_sic2 = get_ERA5(ds, idx+1, xx, yy, region = region)
        grid_output[i, :, :, 2] = grid_sic2
        
        # Masking ======================================
        mask1 = (grid_sic == 0) #(np.isnan(grid_u))
        mask2 = (grid_sic2 == 0) #(np.isnan(grid_u2))

        if datatype == "cell":
            xx1, yy1 = [], []
            for m in range(w, row-w):
                for n in range(w, col-w):
                    ip = np.array([grid_input[i, m-w:m+w+1, n-w:n+w+1, :]])
                    if mask1[m,n] == False: #np.prod(ip[0, :, :, 2]) > 0:
                        op = np.array([grid_output[i, m-w:m+w+1, n-w:n+w+1, :]])
                        xx1.append(xx[m, n])
                        yy1.append(yy[m, n])
                        if first:
                            conv_input = ip
                            conv_output = op
                            first = False
                        else:
                            conv_input = np.concatenate((conv_input, ip), axis = 0)
                            conv_output = np.concatenate((conv_output, op), axis = 0)            

        elif datatype == "entire":
            var_ip = np.shape(grid_input)[3]
            var_op = np.shape(grid_output)[3]
            
            conv_input = np.copy(grid_input)
            conv_output = np.copy(grid_output)
            
            for m in range(0, var_ip):
                subset = grid_input[i, :, :, m]
                subset[mask1] = 0
                conv_input[i, :, :, m] = subset
                
            for n in range(0, var_op):
                subset = grid_output[i, :, :, n]
                subset[mask2] = 0
                conv_output[i, :, :, n] = subset
                
            xx1, yy1 = xx, yy

        elif datatype == "table":
            
            xx1, yy1 = [], []
            for m in range(w, row-w):
                for n in range(w, col-w):
                    ip = np.array([grid_input[i, m-w:m+w+1, n-w:n+w+1, :].flatten()])
                    if np.prod(grid_sic[m-w:m+w+1, n-w:n+w+1]) > 0:
                        op = np.array([grid_output[i, m-w:m+w+1, n-w:n+w+1, :].flatten()])
                        xx1.append(xx[m, n])
                        yy1.append(yy[m, n])
                        
                        if first:
                            conv_input = ip
                            conv_output = op
                            first = False
                        else:
                            conv_input = np.concatenate((conv_input, ip), axis = 0)
                            conv_output = np.concatenate((conv_output, op), axis = 0)  

    return xx1, yy1, conv_input, conv_output

def make_lstm_input2D(data_input, data_output, days = 7):
    # Input & output should be entire images for CNN
    n_samples, row, col, var_ip = np.shape(data_input)
    _, _, _, var_op = np.shape(data_output)
    row,col = 320, 320;
    lstm_input = np.zeros([n_samples-days, days, row, col, var_ip], dtype="int")
    lstm_output = np.zeros([n_samples-days, row, col, var_op], dtype="int")
    
    for n in range(0, n_samples-days):
        for i in range(0, days):
            for v in range(0, var_ip):
                lstm_input[n, i, :, :, v] = (data_input[n+i, 41:, :-41, v])
            for v in range(0, var_op):
                lstm_output[n, :, :, v] = (data_output[n+days, 41:, :-41, v])
    return lstm_input, lstm_output

def make_cnn_input2D(data_input, data_output, days = 3):
    # Input & output should be entire images for CNN
    n_samples, row, col, var_ip = np.shape(data_input)
    _, _, _, var_op = np.shape(data_output)
    row,col = 320, 320;
    cnn_input = np.zeros([n_samples-days, row, col, var_ip * days])
    cnn_output = np.zeros([n_samples-days, row, col, var_op])
    
    for n in range(0, n_samples-days):
        for v in range(0, var_ip):
            for i in range(0, days):
                cnn_input[n, :, :, v+i] = (data_input[n+i, :, :, v])
        for v in range(0, var_op):
            cnn_output[n, :, :, v] = (data_output[n+days, :, :, v])
    return cnn_input, cnn_output


def MAE(obs, prd):
    return np.nanmean(abs(obs-prd))

def corr(prd, obs):
    prd = prd.flatten()
    obs = obs.flatten()
    
    r = ma.corrcoef(ma.masked_invalid(prd), ma.masked_invalid(obs))[0, 1]
    return r

def float_to_int(input0, output0):
    offset = [-0.5, -0.5, 0, 0, -0.5, -0.5]
    
    input1 = np.zeros(np.shape(input0), dtype = np.int16)
    output1 = np.zeros(np.shape(output0), dtype = np.int16)
    
    for c in range(0, 6):
        sub_ip = input0[:, :, :, c] + offset[c]
        sub_ip[sub_ip < -1] = -1
        sub_ip[sub_ip > 1] = 1
        
        if c in [0, 1, 4, 5]:
            sub_ip[sub_ip == offset[c]] = 0
        
        sub_ip = (sub_ip * 20000).astype(np.int16)
        input1[:, :, :, c] = sub_ip
        
        if c < 3:
            sub_op = output0[:, :, :, c] + offset[c]
            sub_op[sub_op < -1] = -1
            sub_op[sub_op > 1] = 1
            
            if c in [0, 1, 4, 5]:
                sub_op[sub_op == offset[c]] = 0
            
            sub_op = (sub_op * 20000).astype(np.int16)
            output1[:, :, :, c] = sub_op
    
    return input1, output1