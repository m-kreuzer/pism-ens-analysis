
import os
import numpy as np
import netCDF4 as nc
import collections
import pandas as pd
import glob
# import matplotlib.pylab as plt
from matplotlib import _cntr as cntr
import scipy.ndimage



def get_spatial_variable(fname,varname):

    """ get one pism variable """

    try:
        ncf = nc.Dataset(fname,"r")
    except IOError as error:
        print fname, "not found."
        raise error
    return np.squeeze(ncf.variables[varname])


def get_spatial_variables(ncfile,variables):

    """ get several variables at once """

    ncf = nc.Dataset(ncfile,"r")
    nc_data = {}
    for var in variables:
        nc_data[var] = np.squeeze(ncf.variables[var][:])
    ncf.close()

    return nc_data


def return_hashes_with_paramval(ensemble_table, param, value):

    """ select ensemble member hashes that belong to a certain parameter
        value and return these hashes
    """

    hashes = ensemble_table[ensemble_table[param] == value].index

    return hashes


def get_reference_data(input_root_dir, grid_id):

    """ get data from input_root_dir with grid_id.
        uses standard file structure from github.com/pism/pism-ais

    """
    rignot_vel_file = os.path.join(input_root_dir,"rignotvel","rignotvel_"+grid_id+".nc")
    bedmap2_file = os.path.join(input_root_dir,"bedmap2","bedmap2_"+grid_id+".nc")
    zwally_basin_file = os.path.join(input_root_dir,"zwally_basins","zwally_basins_"+grid_id+".nc")

    rignc = nc.Dataset(rignot_vel_file,"r")
    bedmnc = nc.Dataset(bedmap2_file,"r")
    zwallync = nc.Dataset(zwally_basin_file,"r")

    bedm_mask = bedmnc.variables["mask"][:]
    bedm_thk = bedmnc.variables["thk"][:]
    bedm_thk_grounded = np.ma.array(bedm_thk,mask=bedm_mask!=0)

    basins = zwallync.variables["basins"][:]

    # swap orientation
    rignot_velsurf_mag = rignc.variables["v_magnitude"][::-1,:]
    # simplify velocities, set masked areas at the domain boundaries to zero.
    msk = rignot_velsurf_mag.mask
    rignot_velsurf_mag = np.array(rignot_velsurf_mag)
    rignot_velsurf_mag[msk] = 0.

    rignc.close()
    bedmnc.close()
    zwallync.close()

    return bedm_mask, bedm_thk, bedm_thk_grounded, basins, rignot_velsurf_mag


def get_run_with_val(tsdata, variable, year, func=np.min):

    """ from the ensemble of timeseries tsdata and certain variable
        and year, get the run that fulfills run == func(run)
        func could be np.min, np.max, np.median
        example:
            get_run_with_val(tsdata, "slvol", 2800)
        gives you the ensemble member that has minimum sea level volume
        in year 2800.
    """

    slarr = np.array([])
    keys = []

    for em in tsdata:
        try:
            slarr = np.append(slarr,tsdata[em][variable][year])
            keys.append(em)
        except IndexError:
            continue

    run =  keys[np.where(slarr==func(slarr))[0][0]]
    return run, tsdata[run][variable][year]


def get_data_on_maskval_above_threshold(data, mask, maskval, threshold):

    """ create a field that is nonly nonzero where mask==maskval
        field larger then threshold. Return this field.
        This function is useful, for example, to extract grounded velocities
        that are larger than X meter per year.
    """

    threshdata = data.copy()
    # use isclose because of rounding errors during regridding
    threshdata[~np.isclose(mask,maskval)] = 0.
    threshdata[threshdata < threshold] = 0.
    return threshdata


def get_sum_per_basin(field, basins, basin_range="all",
                     weigh_by_size=False):

    """ loop over basins from basin_range and sum up the cells
        in each basin. write this sum to a pandas datafram and return.
        you can weigh the sum by the number of basin grid cells.
    """

    if basin_range=="all":
        basin_range = np.arange(1,basins.max()+1)

    sum_per_basin = pd.Series(index=basin_range)

    for bs in basin_range:
        sum_per_basin.loc[bs] = field[bs==basins].sum()

        if weigh_by_size:
            sum_per_basin.loc[bs] /= (basins==bs).sum()

    return sum_per_basin


def get_area_errors(pism_mask, bedm_mask):

    """ find difference in areas of floating and observed,
        between pism_mask and bedm_mask.
        we use np.isclose as the bedmap mask deviates from
        integer by interpolation. default tolerance is 1e-5
        in pism:
        mask=2 is grounded ice,
        mask=3 is floating ice,
        mask=4 is ocean.
        in bedm_mask:
        mask=2 is ocean
        mask=1 is floating ice
        mask=0 is grounded ice
        """

    ad = collections.OrderedDict()

    ad["floating_in_obs_now_not"] = np.array((np.isclose(bedm_mask,1)) &
        (pism_mask !=3),dtype=np.float)
    ad["floating_now_not_in_obs"] = np.array(~(np.isclose(bedm_mask,1)) &
        (pism_mask ==3),dtype=np.float)

    ad["grounded_in_obs_now_not"] = np.array((np.isclose(bedm_mask,0)) &
         (pism_mask !=2),dtype=np.float)
    ad["grounded_now_not_in_obs"] = np.array(~(np.isclose(bedm_mask,0)) &
         (pism_mask ==2),dtype=np.float)

    ad["floating_area_error"] = ad["floating_in_obs_now_not"] + \
        ad["floating_now_not_in_obs"]

    ad["grounded_area_error"] = ad["grounded_in_obs_now_not"] + \
        ad["grounded_now_not_in_obs"]

    return ad

# def get_grounding_line_deviaton_per_basin_old(pism_mask, distance_to_observed_gl,
#     basins, basin_range="all"):

#     glmask = pism_mask.copy()
#     glmask[glmask <= 2] = -1
#     glmask[glmask > 2] = 1

#     if basin_range=="all":
#         basin_range = np.arange(1,basins.max()+1)

#     gl_per_basin = pd.Series(index=basin_range)

#     for bs in basin_range:
#         # grounding line is extracted from contour plot
#         cs = plt.contour(np.ma.masked_array(glmask,mask=(bs==basins)),[0.0],colors='r',linewidth=1)

#         #calculate mean along the grounding line(s)
#         mean_dist_gl = 0
#         cnt_p = 0

#         for p in cs.collections[0].get_paths()[:]:
#             v = p.vertices
#             cx = v[:,0]
#             cy = v[:,1]
#             lenc=len(cx)
#             cnt_p += lenc
#             diffdistint = scipy.ndimage.map_coordinates(distance_to_observed_gl, [cy, cx], order=1)

#             for i in xrange(lenc):
#                 mean_dist_gl += (diffdistint[i])**2

#         mean_dist_gl=mean_dist_gl/cnt_p

#         mean_dist_gl = np.sqrt(mean_dist_gl)
#         printline='\nTOTGL (rmse GL distance in km)'

#         gl_per_basin.loc[bs] = mean_dist_gl

#     return gl_per_basin


def get_grounding_line_deviaton_per_basin(pism_mask, distance_to_observed_gl, basins, basin_range="all"):

    glmask = pism_mask.copy()
    glmask[glmask <= 2] = -1
    glmask[glmask > 2] = 1

    if basin_range=="all":
        basin_range = np.arange(1,basins.max()+1)

    gl_per_basin = pd.Series(index=basin_range)

    for bs in basin_range:

        glmask_basin = np.ma.masked_array(glmask,mask=(bs!=basins))

        x, y = np.mgrid[:glmask_basin.shape[0], :glmask_basin.shape[1]]
        c = cntr.Cntr(x, y, glmask_basin)

        # trace a contour at z == 0.0
        res = c.trace(0.0)

        # result is a list of arrays of vertices and path codes
        # (see docs for matplotlib.path.Path)
        nseg = len(res) // 2
        segments, codes = res[:nseg], res[nseg:]

        # use only longest segment. this should be Antarctic continent.
        segment = sorted(segments, key= len)[-1]

        diffdistint = scipy.ndimage.map_coordinates(distance_to_observed_gl,
            [segment[:,1], segment[:,0]], order=1)

        # square root error
        diffdistint = np.sqrt((diffdistint**2.).sum())

        # weigh by number of points of grounding line
        gl_per_basin.loc[bs] = diffdistint/segment.shape[0]

    return gl_per_basin, segment


#### outdated code below. to be removed.

def get_rms_error(score, varname, ncr, refncr, spatial=True):

    """ get the root mean square error between variable and
    refvariable. Also get the sum of the rms for
    grounded+floating, and grounded and floating alone.
    mask=2 is grounded,
    mask=3 is floating,
    mask=4 is ocean.
    TODO: weight the RMS:
          the closer to the grounding line, the more important.
    """

    variable = np.squeeze(ncr.variables[varname][:])
    mask = np.squeeze(ncr.variables["mask"][:])
    refvariable = np.squeeze(refncr.variables[varname][:])

    rms = np.sqrt((variable-refvariable)**2.)

    ## do not count where now is ocean (could have been icy in ref)
    ## FIXME: is this a reasonable decision?
    rms[mask==4] = 0.

    if spatial:
        return rms

    rms_floating = np.array(rms, copy=True)
    rms_floating[mask==2] = 0.

    rms_grounded = np.array(rms, copy=True)
    rms_grounded[mask==3] = 0.

    rms_error_sums = {"rms_"+varname:rms.sum(),
                        "rms_"+varname+"_grounded":rms_grounded.sum(),
                        "rms_"+varname+"_floating":rms_floating.sum()}

    # ensure same order for all dicts
    score.update((sorted(rms_error_sums.items())))
    return score


def get_rms_error_in_basin(varname, mask_other_basins, ncr, refncr, spatial=False,
                          floating_grounded=False):

    """ get the root mean square error between variable and
    refvariable for a certain basin. Get the sum of the rms for
    grounded+floating, and grounded and floating alone.
    mask=2 is grounded,
    mask=3 is floating,
    mask=4 is ocean in pism mask.
    Input:
        mask_other_basins: this is a mask where all regions that
        should not be considered have the value 1, region to be considered 0.
    """

    variable = np.squeeze(ncr.variables[varname][:])
    pism_mask = np.squeeze(ncr.variables["mask"][:])
    refvariable = np.squeeze(refncr.variables[varname][:])

    variable = np.ma.array(variable,mask=mask_other_basins)

    rms = np.sqrt((variable-refvariable)**2.)

    ## do not count where now is ocean (could have been icy in ref)
    ## FIXME: is this a reasonable decision?
    rms[pism_mask==4] = 0.

    if spatial:
        return rms

    rms_error_sums = {"rms_"+varname:rms.sum()}

    if floating_grounded:
        rms_floating = np.array(rms, copy=True)
        rms_floating[pism_mask==2] = 0.

        rms_grounded = np.array(rms, copy=True)
        rms_grounded[pism_mask==3] = 0.

        rms_error_sums["rms_"+varname+"_grounded"] = rms_grounded.sum()
        rms_error_sums["rms_"+varname+"_floating"] = rms_floating.sum()

    # ensure same order for all dicts
#     score.update((sorted(rms_error_sums.items())))
    return rms_error_sums


def get_rms_for_experiments(varname, refncr, experiments, filepattern, mask_other_basins):

    """ use the get_rms_in_basin function for a set of experiments.
        Collect into data frame.
    """

    df_rms = pd.DataFrame()

    for exp in experiments:
        print exp

        ncfiles = sorted(glob.glob(os.path.join(exp,filepattern)))

        for i, fl in enumerate(ncfiles):

            expncr = nc.Dataset(fl,"r")
            rms_error = get_rms_error_in_basin(varname, mask_other_basins, expncr, refncr, spatial=False)
            expncr.close()
            yr = fl.split("extra_")[1][0:4]
            print yr,
            df_rms.loc[int(yr),exp.split("/")[-1]] = rms_error["rms_"+varname]

        print ""

    return df_rms


def get_wais_ungrounded_area(score, ncr, refncr,
                             wais_latbounds = [-180,-30]):

    """ This is a good measure for detecting collapsed WAIS states,
        but it is not necessarily a good measure to define a good
        (stable) WAIS. This is because it does not take into
        account when new areas ground that should not.
    """

    lon = np.squeeze(refncr.variables["lon"][:])
    wais_msk = (lon < wais_latbounds[0]) | (lon > wais_latbounds[1])

    mask = np.squeeze(ncr.variables["mask"][:])
    refmask = np.squeeze(refncr.variables["mask"][:])

    floating_or_ocean_now_grounded_in_obs = np.ma.masked_array((refmask == 2) &
            ((mask==3)|(mask==4)),dtype=np.float,mask=wais_msk)

    score.update({"wais_ungrounded":
        floating_or_ocean_now_grounded_in_obs.sum()})

    return score


def mean_melt_rate_deviation(score, ncr, basins, rignot_bmr_data, basins_for_score,
                            spatial=False, absolute_values=False):

    rho_ice = 910. # in kg/m^3

    pism_melt_rates = pd.DataFrame(index=rignot_bmr_data.index,
                                   columns=["mean basal melt rate per basin"])

    effshelfbmassflux = np.squeeze(
        ncr.variables['effective_shelf_base_mass_flux'][:])

    mask = np.squeeze(ncr.variables['mask'][:])

    # all basins, hardcoded for now
    for basin_id in np.arange(1,20,1):
        # select only floating ice in basin
        data_basin = np.ma.masked_array(effshelfbmassflux,
            mask = np.logical_or(basins!=basin_id, mask!=3) )
        pism_melt_rates.iloc[basin_id-1] = data_basin.mean()/rho_ice

    if absolute_values:
        return pism_melt_rates

    scorem = (pism_melt_rates - rignot_bmr_data)["mean basal melt rate per basin"]
    # root mean square
    scorem = np.power(scorem.loc[basins_for_score]**2.,0.5)

    if spatial:
        return scorem

    else:
        score.update({"basal_melt_per_basin":scorem.sum()})
        return score

def collect_scores_to_arrays(measures):

    """ this is a kind of resorting: use a dictionary of
        the measures at top level and sort all the single
        runs into a numpy array. We thus can easily use
        numpy methods. """

    run_names = measures.keys()
    measure_names = measures[measures.keys()[0]].keys()

    measure_arrays = collections.OrderedDict()
    for mn in measure_names:
        measure_arrays[mn] = np.zeros(len(run_names))
        for i,run in enumerate(run_names):
            measure_arrays[mn][i] = measures[run][mn]

    return measure_arrays


def normalize_scores(measure_arrays):

    """ calculate the ensemble mean per measure, and
        normalize all runs with that ensemble mean, i.e. divide it. """

    measure_arrays_mean = [arr.mean() for m,arr in measure_arrays.iteritems()]

    measure_arrays_normal = collections.OrderedDict()

    for i,nm in enumerate(measure_arrays.keys()):
        measure_arrays_normal[nm] = np.zeros(len(measure_arrays[nm]))
        if measure_arrays_mean[i] != 0.0:
            measure_arrays_normal[nm] = measure_arrays[nm]/measure_arrays_mean[i]

    return measure_arrays_normal



def collect_scores(ensemble_members, varnames_for_rms,
                   refncr, basins, rignot_bmr_data, basins_for_score,
                   fixed_analysis_year=None):

    """ run all score measures and collect them in the scores ordered
    dictionary.
    """

    scores = collections.OrderedDict()

    for em in ensemble_members:
        run = em.split("/")[-1]
        print run,

        if fixed_analysis_year != None:
            ncr = nc.Dataset(os.path.join(em,"snapshots_"+str(fixed_analysis_year)+".000.nc"),"r")
        else:
            analysis_year = get_last_snap_year(em, pattern="snapshots_")
            ncr = nc.Dataset(os.path.join(em,"snapshots_"+str(analysis_year)+".000.nc"),"r")

        scores[run] = collections.OrderedDict()
        for varname in varnames_for_rms:
            scores[run] = get_rms_error(scores[run], varname, ncr, refncr, spatial=False)
        scores[run] = get_area_errors(scores[run], ncr, refncr, spatial=False)
        scores[run] = get_wais_ungrounded_area(scores[run], ncr, refncr)
        scores[run] = mean_melt_rate_deviation(scores[run], ncr, basins, rignot_bmr_data,
                        basins_for_score)
        ncr.close()

    return scores


def get_last_snap_year(ensemble_member, pattern="snapshots_"):

    all_files = sorted(glob.glob(os.path.join(
        ensemble_member,pattern+"[0-9]*")))

    last_avail_year = all_files[-1].split(pattern)[-1].split(".000.nc")[0]
    return int(last_avail_year)

def get_performance_stats(nc_file):

    """ get some statistics on the runs,
     works for example for extra files."""

    ncf = nc.Dataset(nc_file,"r")
    processor_hours = ncf.variables["run_stats"].processor_hours
    wall_clock_hours = ncf.variables["run_stats"].wall_clock_hours
    model_years_per_processor_hour = ncf.variables[
        "run_stats"].model_years_per_processor_hour
    ncf.close()

    return np.array([processor_hours, wall_clock_hours,
                     model_years_per_processor_hour])