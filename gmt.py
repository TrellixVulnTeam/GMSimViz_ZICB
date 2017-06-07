"""
Library which simplifies the use of GMT.
Functions should hide obvious parameters.

TODO:
grid dx and dy should be by default automatically calculated
consistency among accessory functions' working directory logic
add support for different interpolation methods
    (xyz2grd, surface, nearestneighbour etc...)
avg_ll calculated elsewhere should be local function that works over equator
"""

from math import ceil, log10, sqrt
import os
from shutil import copyfile, move
from subprocess import call, PIPE, Popen
from sys import byteorder
from time import time

import numpy as np

# only needed if plotting fault planes direct from SRF
try:
    from srf import *
except ImportError:
    print('srf.py not found. will not be able to plot faults from SRF.')
# only needed for some functions
try:
    import geo
except ImportError:
    print('geo.py not found. some functions will not work.')

# if gmt available in $PATH, gmt_install_bin should be ''
# to use a custom location, set full path to gmt 'bin' folder below
gmt_install_bin = ''
GMT = os.path.join(gmt_install_bin, 'gmt')

# GMT 5.2+ argument mapping
GMT52_POS = {'map':'g', 'plot':'x', 'norm':'n', 'rel':'j', 'rel_out':'J'}

GMT_DATA = '/home/nesi00213/PlottingData'
# LINZ DATA
LINZ_COAST = {
        '150k':os.path.join(GMT_DATA, 'Paths/lds-nz-coastlines-and-islands/150k.gmt')
}
LINZ_LAKE = {
        '150k':os.path.join(GMT_DATA, 'Paths/lds-nz-lake-polygons/150k.gmt'),
        '1500k':os.path.join(GMT_DATA, 'Paths/lds-nz-lake-polygons/1500k.gmt'),
        '1250k':os.path.join(GMT_DATA, 'Paths/lds-nz-lake-polygons/1250k.gmt')
}
LINZ_RIVER = {
    '150k':os.path.join(GMT_DATA, 'Paths/lds-nz-river-polygons/150k.gmt')
}
LINZ_ROAD = os.path.join(GMT_DATA, 'Paths/lds-nz-road-centre-line/wgs84.gmt')
LINZ_HWY = os.path.join(GMT_DATA, 'Paths/shwy/wgs84.gmt')
# OTHER GEO DATA
TOPO_HIGH = os.path.join(GMT_DATA, 'Topo/srtm_all_filt_nz.grd')
CHCH_WATER = os.path.join(GMT_DATA, 'Paths/water_network/water.gmt')
# CPT DATA
CPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plot', 'cpt')
CPTS = {
    'nztopo-green-brown':os.path.join(CPT_DIR, 'palm_springs_nz_topo.cpt'),
    'mmi':os.path.join(CPT_DIR, 'mmi.cpt'),
    'slip':os.path.join(CPT_DIR, 'slip.cpt'),
    'trise':os.path.join(CPT_DIR, 'trise.cpt')
}

def update_gmt_path(gmt_bin):
    """
    Allow changing GMT binary location.
    """
    global GMT, GMT_VERSION, GMT_MAJOR, GMT_MINOR, psconvert

    GMT = gmt_bin
    # retrieve version of GMT
    gmtp = Popen([GMT, '--version'], stdout = PIPE)
    GMT_VERSION = gmtp.communicate()[0].rstrip()
    gmtp.wait()
    GMT_MAJOR, GMT_MINOR = map(int, GMT_VERSION.split('.')[:2])

    if GMT_MAJOR != 5:
        print('This library is only for GMT version 5. You have %s.' \
                % (GMT_VERSION))
    # ps2raster becomes psconvert in GMT 5.2
    elif GMT_MINOR < 2:
        psconvert = 'ps2raster'
    else:
        psconvert = 'psconvert'
update_gmt_path(GMT)

###
### COMMON RESOURCES
###
# definition of locations which can be mapped
# longitude, latitude,
# point position [Left Centre Right, Top Middle Bottom]
sites = { \
    'Akaroa':(172.9683333, -43.80361111, 'RB'), \
    'Blenheim':(173.9569444, -41.5138888, 'LM'), \
    'Christchurch':(172.6347222, -43.5313888, 'LM'), \
    'Darfield':(172.1116667, -43.48972222, 'CB'), \
    'Dunedin':(170.3794444, -45.8644444, 'LM'), \
    'Greymouth':(171.2063889, -42.4502777, 'RM'), \
    'Haast':(169.0405556, -43.8808333, 'LM'), \
    'Kaikoura':(173.6802778, -42.4038888, 'LM'), \
    'Lyttleton':(172.7194444, -43.60305556, 'LM'), \
    'Masterton':(175.658333, -40.952778, 'LM'), \
    'Napier':(176.916667, -39.483333, 'LM'), \
    'New Plymouth':(174.083333, -39.066667, 'RM'), \
    'Nelson':(173.2838889, -41.2761111, 'CB'), \
    'Oxford':(172.1938889, -43.29555556, 'LB'), \
    'Palmerston North':(175.611667, -40.355000, 'RM'), \
    'Queenstown':(168.6680556, -45.0300000, 'LM'), \
    'Rakaia':(172.0230556, -43.75611111, 'RT'), \
    'Rolleston':(172.3791667, -43.59083333, 'RB'), \
    'Rotorua':(176.251389, -38.137778, 'LM'), \
    'Taupo':(176.069400, -38.6875, 'LM'), \
    'Tekapo':(170.4794444, -44.0069444, 'LM'), \
    'Timaru':(171.2430556, -44.3958333, 'LM'), \
    'Wellington':(174.777222, -41.288889, 'RM'), \
    'Westport':(171.5997222, -41.7575000, 'RM')}
# sites which can be drawn on an NZ wide map
# shouldn't have problems with overlapping
sites_major = ['Blenheim', 'Christchurch', 'Dunedin', 'Greymouth', \
        'Haast', 'Kaikoura', 'Masterton', 'Napier', 'New Plymouth', \
        'Nelson', 'Palmerston North', 'Queenstown', 'Rotorua', \
        'Taupo', 'Tekapo', 'Timaru', 'Wellington', 'Westport']
# region to use when plotting the whole of NZ
nz_region = (166, 179, -47.5, -34)

###
### ACCESSORY FUNCTIONS
###
def make_movie(input_pattern, output, fps = 20):
    """
    Makes animation from output images.
    Must have ffmpeg available in $PATH.
    ffmpeg compiled with:
     - local filesystem input support,
     - qtrle video encoder support,
     - quicktime container write support
    input_pattern: matches sequence of images eg: PNG/image-%04d.png
    output: movie output filename
    fps: frames per second (images per second of video)
    """
    if output[-4:] != '.mov':
        output = '%s.mov' % (output)

    with open('/dev/null', 'w') as sink:
        Popen(['ffmpeg', '-y', '-framerate', str(fps), '-i', input_pattern, \
                '-c:v', 'qtrle', '-r', str(fps), output], stderr = sink).wait()

def make_seismo(out_file, timeseries, x0, y0, xfac, yfac, \
            pos = 'simple', fmt = 'inc', append = True, title = None):
    """
    Make seismogram files to plot with GMT.
    out_file: file to store seismogram data
    timeseries: series of values to plot
    x0: origin x position
    y0: origin y position
    xfac: x increment per step in timeseries
    yfac: y values are the product of yfac with timeseries values
    pos: 'simple' x0, y0 are geo coords,
            movement is linear but with geo coords
            works OK with rectangular projections
            OR: x0, y0 are in distance units, movement is linear
            start pos (x0, y0) is calculated with mapproject prior
            ideal method within GMT as works with paper position, not geo
            must change spacial projection to equvalent 'X' before drawing
    fmt: 'inc' points extend out from origin
        'time' points grow out of origin
    append: add to end of out_file (True) instead of overwriting (False)
        fmt must remain the same within the same file
    title: station title within the file headers
    """
    # make sure timeseries is a numpy array
    # don't modify original data
    if type(timeseries).__name__ == 'list':
        tsy = np.array(timeseries)
    else:
        tsy = np.copy(timeseries)

    if title == None:
        title = 'station at x = %s, y = %s' % (x0, y0)

    # output
    if append:
        mode = 'a'
    else:
        mode = 'w'
    out = open(out_file, mode)

    if fmt == 'inc':
        # adjust amplitude, baseline
        tsy = tsa * yfac + y0 - yfac * tsa[0]
        # correspanding x value
        tsx = np.arange(len(tsy)) * xfac + x0
        # store
        np.savetxt(out, np.dstack(tsx, tsy), fmt = '%s', \
                header = '> %s' % (title), comments = '')

    elif fmt == 'time':
        for t in xrange(len(tsa)):
            tsy = tsa
            tsx = np.arange(len(tsy)) * xfac + x0

    out.close()

def auto_tick(x_min, x_max, width):
    """
    Try to determine ideal major tick interval on map for x axis.
    # TODO: allow font size specification to modify factors
    x_min: minimum longitude
    x_max: maximum longitude
    width: width of map
    """
    # maximum ticks per inch - 18 point with 0 decimal places
    # this should be modified based on font size
    tpi = 1.4
    # adjusted for 1dp and 2dp, looping
    tpi_dp = [tpi, tpi * 0.93, tpi * 0.86]

    # starting tick is increased until ticks per inch is less than max
    major_tick = 0.01
    for i in xrange(12):
        # check tpi vs tpi max for decimal places in major_tick
        if ((x_max - x_min) / major_tick) / width \
                > tpi_dp[max(0, 2 - i // 3)]:
            # increase by factor of 2, 2.5, 2, 2, 2.5, 2, 2, 2.5...
            # this gives a major_tick of 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1...
            major_tick *= 2 + ((i + 2) % 3 == 0) * 0.5
        else:
            break

    # minor tick 10 times per major unless ending with 5 in which case 5 times
    minor_tick = major_tick / 10.0 * (2 - ((i + 2) % 3 == 0))

    return major_tick, minor_tick

def get_region(region_name, as_components = False):
    """
    Returns region as tuple (x_min, x_max, y_min, y_max).
    Also returns list of sites which fit in region without crowding.
    as_components: True will return x_min, x_max etc. as individual values
    region_name: predefined region name to get parameters for
    """
    if region_name == 'CANTERBURY':
        x_min, x_max, y_min, y_max = 171.75, 173.00, -44.00, -43.20
        region_sites = ['Rolleston', 'Darfield', 'Lyttelton', \
                'Akaroa', 'Kaiapoi', 'Rakaia', 'Oxford']
    elif region_name == 'WIDERCANT':
        x_min, x_max, y_min, y_max = 170.52, 173.67, -44.4, -42.53
        region_sites = ['Rolleston', 'Darfield', 'Lyttelton', \
                'Akaroa', 'Kaiapoi', 'Rakaia', 'Oxford']
    elif region_name == 'SOUTHISLAND':
        x_min, x_max, y_min, y_max = 166.0, 174.5, -47.50, -40.00
        region_sites = ['Queenstown', 'Dunedin', 'Tekapo', \
                'Christchurch', 'Haast', 'Greymouth', 'Westport', \
                'Kaikoura', 'Nelson', 'Blenheim', 'Timaru']
    elif region_name == 'MIDNZ':
        x_min, x_max, y_min, y_max = 168.2, 177.9, -45.7, -37.85
        region_sites = ['Queenstown', 'Tekapo', 'Timaru', \
        'Christchurch', 'Haast', 'Greymouth', 'Westport', \
        'Kaikoura', 'Nelson', 'Blenheim', 'Wellington', \
        'Masterton', 'Napier', 'New Plymouth', 'Taupo', 'Rotorua']
    else:
        # calling this in a Try block, except TypeError
        # would be one way of handling this if expanded to 2 vars
        return None

    if as_components:
        return x_min, x_max, y_min, y_max, region_sites
    return (x_min, x_max, y_min, y_max), region_sites

def is_native_xyv(xyv_file, x_min, x_max, y_min, y_max, v_min = None):
    """
    Detects whether an input file is native or if it needs bytes swapped.
    It makes sure values are sane, if not. Non-native is assumed.
    xyv_file: file containing 3 columns
    x_min: minimum x value (first column)
    x_max: maximum x value
    y_min: minimum y value (second column)
    y_max: maximum y value
    v_min: minimum value in third column (None for skip)
    """
    # form array of xyv data (3 columns of 4 byte floats)
    bin_data = np.fromfile(xyv_file, dtype = '3f4')

    # check the first few rows
    for i in xrange(min(10, len(bin_data))):
        if x_min <= bin_data[i, 0] <= x_max and \
                y_min <= bin_data[i, 1] <= y_max and \
                (v_min == None or v_min <= bin_data[i, 2]):
            continue
        else:
            # invalid values, not native
            return False
    # no invalid values found, assuming native endian
    return True

def swap_bytes(xyv_file, native_version, bytes_per_var = 4):
    """
    Simple and fast way to swap bytes in a file.
    xyv_file: input file
    native_version: where to store the result
    bytes_per_var: how long each value is
    """
    if byteorder == 'little':
        data = np.fromfile(xyv_file, dtype = '>f%d' % (bytes_per_var))
    else:
        data = np.fromfile(xyv_file, dtype = '<f%d' % (bytes_per_var))

    data.astype(np.float32).tofile(native_version)

def abs_max(x_file, y_file, z_file, out_file, native = True):
    """
    Creates a file containing the absolute max value of 3 components.
    Each file is assumed to contain 3 columns of 4 byte values.
    x_file: 1st input file (named x here)
    y_file: 2nd input file (named y here)
    z_file: 3rd input file (named z here)
    out_file: where to store the result
    native: files are in native endian if True
    """
    # allow all-in-one with byteswap capability
    if native:
        fmt = '3f4'
    elif byteorder == 'little':
        fmt = '3>f4'
    else:
        fmt = '3<f4'

    result = np.fromfile(x_file, dtype = fmt)
    y = np.fromfile(y_file, dtype = fmt)[:, 2]
    z = np.fromfile(z_file, dtype = fmt)[:, 2]

    result[:, 2] = np.sqrt(result[:, 2] ** 2 + y ** 2 + z ** 2)
    result.astype('f4').tofile(out_file)

def xyv_spacing(xyv_file, factor = 0.5):
    """
    Reads the spacing of a binary lon, lat, value file.
    Returns the grid spacing that should be using given the factor.
    Factor should be between 1/3 and 1.0 otherwise gaps form in GMT.
    Assumes dx == dy, grid is equi-distant as is consistent with emod3d.
    xyv_file: native binary float file containing lon, lat, x values
    factor: multiply spacing by this number in returned value
    """
    lonlat = np.memmap(xyv_file, dtype = '3f')
    spacing = geo.ll_dist(lonlat[0, 0], lonlat[0, 1], lonlat[1, 0], lonlat[1, 1])
    return spacing * factor

def xyv_cpt_range(xyv_file, max_step = 12, percentile = 99.5, \
        my_max = None, my_inc = None):
    """
    Return total min, cpt increment, max and total max.
    Only working for a scale starting with 0.
    xyv_file: native binary float file containing lon, lat, x values
    max_step: max number of increments from minimum value
    percentile: cpt range should cover this percentile
    my_max: override result max
    my_inc: override result increment
    """
    lonlatvalue = np.memmap(xyv_file, dtype = '3f')
    mn = np.min(lonlatvalue[:, 2])
    mx = np.max(lonlatvalue[:, 2])

    cpt_mx = np.percentile(lonlatvalue[:, 2], percentile)
    if cpt_mx < 100:
        # 1 sf
        cpt_mx = round(cpt_mx, -int(log10(cpt_mx)))
    else:
        # 2 sf
        cpt_mx = round(cpt_mx, -int(log10(cpt_mx) - 1))
    if my_max != None:
        cpt_mx = my_max

    # un-rounded smallest increment for cpt
    min_inc = cpt_mx / max_step
    # rounded up to nearest power of 10
    inc_10 = 10 ** ceil(log10(min_inc))
    # will be ok 1x10**x
    cpt_inc = inc_10
    # 5x10**x and 2x10**x are also a round numbers
    for factor in [0.2, 0.5]:
        if inc_10 * factor > min_inc:
            cpt_inc = inc_10 * factor
            break
    if my_inc != None:
        cpt_inc = my_inc

    return mn, cpt_inc, cpt_mx, mx

def srf2map(srf, out_dir, prefix = 'plane', value = 'slip', cpt_percentile = 95):
    """
    Creates geographic overlay data from SRF files.
    out_dir: where to place outputs
    prefix: output files are prefixed with this
    value: which srf value to retrieve at subfaults,
            TODO: None to only create masks - don't re-create them
    cpt_percentile: also create CPT to fit SRF data range
            covers this percentile of data
    """
    dx, dy = srf_dxy(srf)
    plot_dx = '%sk' % (dx * 0.6)
    plot_dy = '%sk' % (dy * 0.6)
    bounds = get_bounds(srf)
    np_bounds = np.array(bounds)
    seg_llvs = srf2llv_py(srf, value = value)
    all_vs = np.concatenate((seg_llvs))[:, 2]
    percentile = np.percentile(all_vs, cpt_percentile)
    # TODO: fix mess
    cpt = os.path.join(os.path.dirname(os.path.abspath(__file__)), \
            'cpt', 'slip.cpt')
    makecpt(cpt, '%s/%s.cpt' % (out_dir, prefix), 0, percentile, 1)
    # each plane will use a region which just fits
    # these are needed for plotting
    regions = []
    # create resources for each plane
    for s in xrange(len(bounds)):
        # data in binary files
        seg_llvs[s].astype(np.float32).tofile('%s/%s_%d_slip.bin' \
                % (out_dir, prefix, s))
        # mask path
        geo.path_from_corners(corners = bounds[s], min_edge_points = 100, \
                output = '%s/%s_%d_bounds.ll' % (out_dir, prefix, s))
        x_min, y_min = np.min(np_bounds[s], axis = 0)
        x_max, y_max = np.max(np_bounds[s], axis = 0)
        regions.append((x_min, x_max, y_min, y_max))
        # GMT grd mask
        grd_mask('%s/%s_%d_bounds.ll' % (out_dir, prefix, s), \
                '%s/%s_%d_mask.grd' % (out_dir, prefix, s), \
                dx = plot_dx, dy = plot_dy, region = regions[s])

    return (plot_dx, plot_dy), regions

# TODO: function should be able to modify result CPT such that:
#       background colour is extended just like foreground (bidirectional)
def makecpt(source, output, low, high, inc = None, invert = False, \
        wd = None, bg = None, fg = None, continuing = False, \
        continuous = False, log = False, transparency = 0):
    """
    Creates a colour palette file.
    source: inbuilt scale or template file
    output: filepath to store file
    low: minimum range
    high: maximum range
    inc: discrete increment
    invert: whether to swap colour order
    wd: working directory containing gmt.conf
        gmt.conf only used with bg and fg options
    bg: custom background colour
    fg: custom foreground colour
    continuing: bg and fg colours match lowest and highest values
    continuous: set to True to prevent discrete colour transitions
    log: logarithmic cpt (input is log10(z))
    transparency: cpt colour value transparency (0 for opaque)
    """
    # determine working directory
    if wd == None:
        wd = os.path.dirname(output)
        if wd == '':
            wd = '.'
    backup_history(wd = wd)
    # work out GMT colour range parameter
    crange = '%s/%s' % (low, high)
    if inc != None:
        crange = '%s/%s' % (crange, inc)

    if os.path.exists(source):
        source = os.path.abspath(source)
    cmd = [GMT, 'makecpt', '-A%s' % (transparency), \
            '-T%s' % (crange), '-C%s' % (source)]
    if invert:
        cmd.append('-I')
    if log:
        cmd.append('-Qi')
    if continuing:
        cmd.append('-Do')
    if continuous:
        cmd.append('-Z')
    elif bg != None or fg != None:
        if bg:
            Popen([GMT, 'set', 'COLOR_BACKGROUND', bg], cwd = wd).wait()
        if fg:
            Popen([GMT, 'set', 'COLOR_FOREGROUND', fg], cwd = wd).wait()
        cmd.append('-M')
    with open(output, 'w') as cptf:
        Popen(cmd, stdout = cptf, cwd = wd).wait()
    backup_history(restore = True, wd = wd)

def table2grd(table_in, grd_file, file_input = True, grd_type = 'surface', \
        region = None, dx = '1k', dy = None, climit = 1, wd = None, \
        geo = True, sectors = 4, min_sectors = 2, search = '1k', header = 0, \
        cols = None, tension = '0.0', \
        automask = None, mask_dist = '1k', outside = 'NaN'):
    """
    Create a grid file from an xyz (table data) file.
    Currently tested with "surface", "xyz2grd" and "nearneighbor".
    More feature expansion will take place as required.
    table_in: contains x, y and value columns
    grd_file: output file
    file_input: input is a file (True) or pipe string (False)
    grd_type: type of grd file to create
    region: region to create the grid for
    dx: horizontal grid spacing of the grid file
    dy: vertical grid spacing (leave None to use dx)
    climit: consider interpolation result correct if diff < climit
    wd: GMT working directory (default is destination folder)
    geo: True if given lon lat coords, False if given cartesian coords
    sectors: for nearneighbour, split radius in eg = 4 (quadrants)
        takes average of closest point per sector
    min_sectors: for nearneighbour, min sectors to contain values, else nan
    search: for nearneighbour, search radius
    header: number of lines to skip at beginning of input file
    cols: gmt column definition, eg: '0,1,2'
    automask: filename to store mask generated with mask_search option below
    mask_dist: generate mask using grdmask -S option
        inside mask: anything which has at most this distance to any location
    outside: value outside of mask
    """
    # determine working directory
    if wd == None:
        wd = os.path.dirname(grd_file)
        if wd == '':
            wd = '.'

    # should not affect history in wd
    # TODO: should be optional
    write_history(False, wd = wd)

    # prepare parameters
    if region == None:
        region = '-R'
    else:
        region = '-R%s/%s/%s/%s' % region
    if dy == None:
        dy = dx

    # create surface grid
    cmd = [GMT, grd_type, \
            '-G%s' % (os.path.abspath(grd_file)), \
            '-I%s/%s' % (dx, dy), region]
    # second command for optionally creating a mask
    # input for grdmask cannot be stdin as at GMT 5.3
    if file_input and automask != None:
        cmd_mask = [GMT, 'grdmask', os.path.abspath(table_in), \
                '-G%s' % (os.path.abspath(automask)), \
                '-I%s/%s' % (dx, dy), region, \
                '-N%s/1/1' % (outside), '-S%s' % (mask_dist)]
    else:
        cmd_mask = []

    if geo:
        cmd.append('-fg')
        cmd_mask.append('-fg')
    if header > 0:
        cmd.append('-hi%d' % (header))
        cmd_mask.append('-hi%d' % (header))
    if cols != None:
        cmd.append('-i%s' % (cols))
        cmd_mask.append('-i%s' % (cols))

    if grd_type == 'surface':
        cmd.append('-T%s' % (tension))
        cmd.append('-C%s' % (climit))
    elif grd_type == 'xyz2grd':
        cmd.append('-r')
    elif grd_type == 'nearneighbor':
        nspec = '-N%s' % (sectors)
        if min_sectors != None:
            nspec = '%s/%s' % (nspec, min_sectors)
        cmd.append(nspec)
        cmd.append('-S%s' % (search))

    if file_input:
        cmd.append(os.path.abspath(table_in))
        # test if text (otherwise binary assumed)
        try:
            # test if text file
            with open(table_in, 'r') as tf:
                for _ in xrange(header):
                    tf.readline()
                map(float, tf.readline().split()[:2])
        except ValueError:
            cmd.append('-bi3f')
        # run command
        Popen(cmd, cwd = wd).wait()
        # also create radius based mask if wanted
        if automask != None:
            Popen(cmd_mask, cwd = wd).wait()
    else:
        grdp = Popen(cmd, stdin = PIPE, cwd = wd)
        grdp.communicate(table_in)
        grdp.wait()

    write_history(True, wd = wd)

def grd_mask(xy_file, out_file, region = None, dx = '1k', dy = '1k', \
        wd = None, outside = 'NaN', geo = True, mask_dist = None):
    """
    Creates a mask file from a path or surrounding point area with mask_dist.
    xy_file: file containing a path
    out_file: name of output GMT grd file
    region: tuple region of grd file (must be set if gmt.history doesn't exist)
    dx: x grid spacing size
    dy: y grid spacing size
    wd: GMT working directory (default is destination folder)
    outside: value placed outside the mask
    geo: True if given lon lat coords, False if given cartesian coords
    mask_dist: -S option, mask includes area of this distance around each point
    """
    if wd == None:
        wd = os.path.dirname(out_file)
        if wd == '':
            wd = '.'
    cmd = ([GMT, 'grdmask', os.path.abspath(xy_file), \
            '-G%s' % (os.path.abspath(out_file)), \
            '-N%s/1/1' % (outside), '-I%s/%s' % (dx, dy)])
    if geo:
        cmd.append('-fg')
    if mask_dist != None:
        cmd.append('-S%s' % (mask_dist))
    if region == None:
        cmd.append('-R')
    else:
        # TODO: optionally do not store history
        cmd.append('-R%s/%s/%s/%s' % region)

    write_history(False, wd = wd)
    Popen(cmd, cwd = wd).wait()
    write_history(True, wd = wd)

def grdmath(expression, region = None, dx = '1k', dy = '1k', \
        wd = '.'):
    """
    Does operations on input grids and data (values or xyv files) RPN style
    gmt.soest.hawaii.edu/doc/5.1.0/grdmath.html
    expression: list containing RPN expression as defined by GMT
        examples are below
    region: region of interest
    dx: x resolution of grids
    dy: y resolution of grids
    wd: GMT working directory

    examples:
    expression = ['grdfile1', 'SQRT', '=', 'grdfile2']
    grdfile2 = sqrt(grdfile1)
    expression = ['gridfile1', 1, 'SUB', 'SQRT', '=', 'grdfile2']
    grdfile2 = sqrt(gridfile1 - 1)
    """

    cmd = [GMT, 'grdmath']
    # append optional arguments
    # TODO:...

    # required parameters are at the end of the command
    cmd.extend(map(str, expression))
    Popen(cmd, cwd = wd).wait()

def gmt_defaults(wd = '.', font_annot_primary = 16, \
        map_tick_length_primary = '0.05i', font_label = 16, \
        ps_page_orientation = 'portrait', map_frame_pen = '1p,black', \
        format_geo_map = 'D', map_frame_type = 'plain', \
        format_float_out = '%lg', proj_length_unit = 'i', \
        ps_media = 'A0', extra = []):
    """
    Sets default values for GMT.
    GMT stores these values in the file 'gmt.conf'
    wd: which directory to set for
    extra: list of params eg: ['FONT_ANNOT_SECONDARY', '12', 'KEY', '=', 'VALUE']
    """
    cmd = [GMT, 'set', \
            'FONT_ANNOT_PRIMARY', '%s' % (font_annot_primary), \
            'MAP_TICK_LENGTH_PRIMARY', '%s' % (map_tick_length_primary), \
            'FONT_LABEL', '%s' % (font_label), \
            'PS_PAGE_ORIENTATION', ps_page_orientation, \
            'MAP_FRAME_PEN', '%s' % (map_frame_pen), \
            'FORMAT_GEO_MAP', format_geo_map, \
            'MAP_FRAME_TYPE', map_frame_type, \
            'FORMAT_FLOAT_OUT', format_float_out, \
            'PROJ_LENGTH_UNIT', proj_length_unit, \
            'PS_MEDIA', '=', ps_media]
    # protect users from entering non-string values
    cmd.extend(map(str, extra))
    Popen(cmd, cwd = wd).wait()

def mapproject(x, y, wd = '.', projection = None, region = None, \
    inverse = False, unit = None):
    """
    Project coordinates to get position or get coordinates from position.
    NOTE: if projection specifies units of length,
            output will still be in default units
    projection: map projection, default uses history file
    region: map region (x_min, x_max, y_min, y_max), default uses history file
    inverse: False to get coords from pos, True to get pos from coords
    unit: return value units, default uses PROJ_LENGTH_UNIT from gmt.conf
    """
    # calculation should not affect plotting
    write_history(False, wd = wd)

    cmd = [GMT, 'mapproject']
    if projection == None:
        cmd.append('-J')
    else:
        cmd.append('-J%s' % (projection))
    if region == None:
        cmd.append('-R')
    else:
        cmd.append('-R%s/%s/%s/%s' % (region))
    if inverse:
        cmd.append('-I')
    if unit != None:
        cmd.append('-D%s' % (unit))

    projp = Popen(cmd, stdin = PIPE, stdout = PIPE, cwd = wd)
    result = projp.communicate('%f %f\n' % (x, y))[0]
    projp.wait()

    # re-enable history file
    write_history(True, wd = wd)

    return map(float, result.split())

def map_width(projection, height, region, wd = '.', abs_diff = False, \
        start_width = 6, accuracy = 0.01, reference = 'left'):
    """
    Usually you create a map by giving the total width or width scaling.
    This finds out how wide a map should be given a wanted height.
    returns: width, height
    projection: projection of the map
    height: wanted height of the result dimentions
    region: region of the map
    wd: working directory (important for gmt_history: proj_length_unit)
    start_width: start closing in with this width
    accuracy: how close to approach wanted height before returning result
    abs_diff: whether accuracy is relative (False) or absolute (True)
    reference: consider greatest height of map to be at 'left' or 'mid'(dle)
            could detect automatically in the future
    """
    # some map projections will be higher/lower in the middle of the map
    if reference == 'left':
        x_ref = region[0]
    elif reference == 'mid':
        x_ref = region[1] - region[0]

    if abs_diff:
        window_max = height + accuracy
        window_min = height - accuracy
    else:
        window_max = height * (1 + accuracy)
        window_min = height * (1 - accuracy)

    width = start_width
    while True:
        new_height = mapproject(x_ref, region[3], wd = wd, \
                projection = '%s%s' % (projection, width), region = region)[1]
        if new_height > window_max or new_height < window_min:
            width *= window_max / float(new_height)
        else:
            break

    return width, new_height

def adjust_latitude(projection, width, height, region, wd = '.', \
        abs_diff = False, accuracy = 0.01, reference = 'left'):
    """
    Usually you create a region and adjust the size keeping aspect ratio.
    This adjusts latitude range such that both X and Y dimentions fit.
    Note that adjusting longitude with Mercator projection is simple math.
    projection: map projection
    width: this will be the width of the result scaling
    height: this will be the height of the result scaling +- accuracy
    region: initial region which may have its latitude adjusted
    """
    # TODO: merge this and map_width function as 90% is the same
    # some map projections will be higher/lower in the middle of the map
    if reference == 'left':
        x_ref = region[0]
    elif reference == 'mid':
        x_ref = region[1] - region[0]

    if abs_diff:
        window_max = height + accuracy
        window_min = height - accuracy
    else:
         window_max = height * (1 + accuracy)
         window_min = height * (1 - accuracy)

    mid_lat = sum(region[2:]) / 2.

    while True:
        new_height = mapproject(x_ref, region[3], wd = wd, \
                projection = '%s%s' % (projection, width), region = region)[1]
        if new_height > window_max or new_height < window_min:
            # this would work first time with constant latitude distance
            scale_factor = height / float(new_height)
            # how much latitude will now be on either side of the centre
            diff_lat = (region[3] - region[2]) * scale_factor * 0.5
            region = (region[0], region[1], \
                    mid_lat - diff_lat, mid_lat + diff_lat)
        else:
            break

    return new_height, region

def fill_space(space_x, space_y, region, dpi, proj = 'M', wd = '.'):
    """
    Given minimal region, extend vertically or horizontally to fit avaliable space.
    Only works with perpendicular north, east projections.
    Will return exact dimentions and extended region.
    """
    # scale image size to fit and extend to prevent letterboxing
    # note map project units may be different but ratios remain same
    letterbox_width, letterbox_height = \
            mapproject(region[1], region[3], \
            projection = '%s%s' % (proj, space_x), \
            region = region, wd = wd)
    # make sure total height fits into square of max_edge sides
    if letterbox_height > space_y:
        letterbox_width, letterbox_height = map_width(proj, space_y, \
                region, wd = wd, abs_diff = True, accuracy = 0.4 / float(dpi))
        # extend longitude to fit width
        diff_lon = (space_x / float(letterbox_width) \
                * (region[1] - region[0]) \
                - (region[1] - region[0])) * 0.5
        region = (region[0] - diff_lon, region[1] + diff_lon, \
                region[2], region[3])
        # adjust final hight very slightly
        space_x, space_y = mapproject(region[1], region[3], \
                projection = '%s%s' % (proj, space_x), region = region, wd = wd)
    else:
        # extend latitude to fit height
        space_y, region = adjust_latitude(proj, \
                space_x, space_y, region, wd = wd, \
                abs_diff = True, accuracy = 0.4 / float(dpi))

    return space_x, space_y, region

def region_transition(projection, region_start, region_end, \
        space_x, space_y, dpi_target, frame, frame_total, \
        wd = '.', movement = 'sqrt'):
    """
    For animations where view window zooms,
    calculate region of view windows, also return any margins required.
    Keeps the total size of view window the same along transformation.
    NB/TODO/FIX:
        ZOOM is assumed to be zoom in, not out
        region_end must be within region_start
        ideally will also work as arbitrary pan
        space is best used for region_end
    projection: only mercator 'M' tested
    region start: initial view window region
    region end: final view window region
    space_x: maximum x space to use for plot
    space_y: maximum y space to use for plot
    dpi_target: render target to make sure result is within pixel
    frame: current step in transformation
    frame_total: total steps in transformation
    wd: where GMT commands should be executed from
    movement: style of camera movement (speed over time changes)
    """
    # XXX: dangerous code will fail under certain circumstances.
    # make sure new region is in valid range.
    # ie. latitude > -90 (not very likely to happen)

    # position along transformation
    # linear may not appear linear as
    #     same increments will be relatively larger when zooming in
    # TODO: make a movement style which has same relative movement
    if movement == 'linear':
        position = frame / (float(frame_total) - 1)
    elif movement == 'log':
        position = log10(frame + 1) / log10(frame_total)
    elif movement == 'sqrt':
        position = sqrt(frame) / sqrt(frame_total - 1)
    else:
        # TODO: this should really be throwing an exception
        print('Not a supported camera movement style. Exiting.')
        exit(1)

    # centre positions used for panning window
    # distortions along y axis during tracking are ignored
    centre_start = sum(region_start[:2]) / 2., sum(region_start[2:]) / 2.
    centre_end = sum(region_end[:2]) / 2., sum(region_end[2:]) / 2.

    # dimentions of regions
    size_ll = {'sw' : float(region_start[1] - region_start[0]), \
            'sh' : float(region_start[3] - region_start[2]), \
            'ew' : float(region_end[1] - region_end[0]), \
            'eh' : float(region_end[3] - region_end[2])}

    # differences in lon, lat regions are used for zooming window
    diff_ll = size_ll['sw'] - size_ll['ew'], \
            size_ll['sh'] - size_ll['eh']
    # centre position approaches region_end
    centre_now = centre_start[0] \
            + (centre_end[0] - centre_start[0]) * position, \
            centre_start[1] \
            + (centre_end[1] - centre_start[1]) * position

    # region_end must fit in space_x by space_y
    # find if region_start is taller (start_y > space_y) or wider
    plot_width = space_x
    start_y = mapproject(region_start[1], region_start[3], \
            region = region_start, \
            projection = '%s%s' % (projection, plot_width), wd = wd)[1]
    if start_y > space_y:
        # zoom by reducing latitude, make y fit, crop longitude
        diff_lat = 0.5 * (size_ll['sh'] - diff_ll[1] * position)
        # move by adjusting to centre
        region_new = (centre_now[0] - 0.5 * size_ll['sw'], \
                centre_now[0] + 0.5 * size_ll['sw'], \
                centre_now[1] - diff_lat, centre_now[1] + diff_lat)
        # find height of map given ideal width
        end_y = mapproject(region_new[1], region_new[3], \
                region = region_new, \
                projection = '%s%s' % (projection, plot_width), wd = wd)[1]
        # find correct width +- 0.4 pixels
        plot_width, plot_height = map_width(projection, space_y, \
                region_new, abs_diff = True, \
                wd = wd, accuracy = 0.4 / float(dpi_target), \
                start_width = space_y / float(end_y) * space_x)
        if end_y < space_y:
            # have to reduce longitude also
            diff_lon = space_x / float(plot_width) \
                    * size_ll['sw'] * 0.5
            region_new = (centre_now[0] - diff_lon, \
                    centre_now[0] + diff_lon, \
                    region_new[2], region_new[3])
            # find final dimentions
            plot_width, plot_height = mapproject(region_new[1], \
                    region_new[3], region = region_new, \
                    projection = '%s%s' % (projection, space_x), \
                    wd = wd)
    else:
        # zoom by reducing longitude, make x fit, crop latitude
        diff_lon = 0.5 * (size_ll['sw'] - diff_ll[0] * position)
        # move by adjusting to centre
        region_new = (centre_now[0] - diff_lon, centre_now[0] + diff_lon, \
                centre_now[1] - 0.5 * size_ll['sh'], \
                centre_now[1] + 0.5 * size_ll['sh'])
        # find height of map givent ideal width
        plot_height = mapproject(region_new[1], region_new[3], \
                region = region_new, \
                projection = '%s%s' % (projection, plot_width), wd = wd)[1]
        if plot_height > space_y:
            # have to reduce latitude also, keep height +- 0.4 pixels
            plot_height, region_new = adjust_latitude(projection, \
                    plot_width, space_y, region_new, wd = wd, \
                    abs_diff = True, accuracy = 0.4 / float(dpi_target))

    return region_new, plot_width, \
            (space_x - plot_width) / 2., (space_y - plot_height) / 2.

def write_history(writable, wd = '.'):
    """
    Set whether GMT should update history for parameters.
    writable: True: updates history, False: readonly history
    """
    if writable:
        history = 'true'
    else:
        history = 'readonly'

    Popen([GMT, 'set', 'GMT_HISTORY', history], cwd = wd).wait()

def backup_history(restore = False, wd = '.'):
    """
    Copy history file or overwrite with original copied version.
    Useful when changes need to be made but original file wanted after.
    restore: False will backup history file, True will restore it
    wd: gmt working directory containing the history file
    """
    original = os.path.join(wd, 'gmt.conf')
    backup = os.path.join(wd, 'gmt.conf.bak')

    if restore:
        if os.path.exists(backup):
            move(backup, original)
        else:
            # there was originally no history file, keep it that way
            if os.path.exists(original):
                os.remove(original)
        return

    if os.path.exists(original):
        copyfile(original, backup)

###
### MAIN PLOTTING CLASS
###
class GMTPlot:

    def __init__(self, pspath, append = False, reset = True):
        self.pspath = pspath
        if append:
            self.psf = open(pspath, 'a')
            self.new = False
        else:
            self.psf = open(pspath, 'w')
            self.new = True
        # figure out where to run GMT from
        self.wd = os.path.abspath(os.path.dirname(pspath))
        if self.wd == '':
            self.wd = os.path.abspath('.')
        # gmt default values for working directory
        # TODO: test all plot functions changing reset default -> false
        if reset or not os.path.exists(os.path.join(self.wd, 'gmt.conf')):
            gmt_defaults(wd = self.wd)
        # place to reject unwanted warnings
        self.sink = open('/dev/null', 'a')

    def history(self, item):
        """
        Retrieve properties from GMT history file.
        item: item wanted eg: 'J' or 'R'
        """
        with open(os.path.join(self.wd, 'gmt.history')) as hf:
            for line in hf:
                line_data = line.split()
                if len(line_data) > 0 and line_data[0] == item:
                    # assuming values will never contain white space
                    return line_data[1]
        # wanted item has not been set yet
        return None

    def background(self, length, height, \
            x_margin = 0, y_margin = 0, colour = 'white'):
        """
        Draws background on GMT plot.
        This should be the first action.
        length: how wide the background should be (x margin included)
        height: how high the background should be (y margin included)
        x_margin: start with shifted origin, this much space is on left
        y_margin: start with shifted origin, this much space is on bottom
        colour: the colour of the background
        """
        # draw background and place origin up, right as wanted
        cmd = [GMT, 'psxy', '-K', '-G%s' % (colour), \
                '-JX%s/%s' % (length, height), '-R0/%s/0/%s' % (length, height), \
                '-Xa%s' % (x_margin), '-Ya%s' % (y_margin)]
        # one of the functions that can be run on a blank file
        # as such, '-O' flag needs to be taken care of
        if self.new:
            self.new = False
        else:
            cmd.append('-O')
        proc = Popen(cmd, stdin = PIPE, stdout = self.psf, cwd = self.wd)
        proc.communicate('%s 0\n%s %s\n0 %s\n0 0' \
                % (length, length, height, height))
        proc.wait()

    def spacial(self, proj, region, \
            lon0 = None, lat0 = None, sizing = 1, \
            x_shift = 0, y_shift = 0, fill = None):
        """
        Sets up the spacial parameters for plotting.
        doc http://gmt.soest.hawaii.edu/doc/5.1.0/gmt.html#j-full
        proj: GMT projection eg 'X' = cartesian, 'M|m' = mercator
        region: tuple containing x_min, x_max, y_min, y_max
        lon0: standard meridian (not always necessary)
        lat0: standard parallel (not always necessary)
        sizing: either scale: distance / degree longitude at meridian
                    or width: total distance of region
        x_shift: move plotting origin in the X direction
        y_shift: move plotting origin in the Y direction
        fill: colour to fill area with
        """
        # work out projection format
        if proj.lower() == 't' and lon0 == None:
            # lon0 is not optional, use centre as default
            lon0 = sum(map(float, rogion.split('/')[:2])) / 2.
        if lon0 == None:
            gmt_proj = '-J%s%s' % (proj, sizing)
        elif lat0 == None:
            gmt_proj = '-J%s%s/%s' % (proj, lon0, sizing)
        else:
            gmt_proj = '-J%s%s/%s/%s' % (proj, lon0, lat0, sizing)

        cmd = [GMT, 'psxy', gmt_proj, '-X%s' % (x_shift), \
                '-Y%s' % (y_shift), '-K', \
                '-R%s/%s/%s/%s' % region]
        # one of the functions that can be run on a blank file
        # as such, '-O' flag needs to be taken care of
        if self.new:
            self.new = False
        else:
            cmd.append('-O')

        if fill != None:
            cmd.append('-G%s' % (fill))
            spipe = Popen(cmd, stdin = PIPE, stdout = self.psf, cwd = self.wd)
            spipe.communicate('%s %s\n%s %s\n%s %s\n%s %s\n' % \
                    (region[0], region[2], region[1], region[2], \
                    region[1], region[3], region[0], region[3]))
            spipe.wait()
        else:
            cmd.append('-T')
            Popen(cmd, stdout = self.psf, cwd = self.wd).wait()

    def text(self, x, y, text, dx = 0, dy = 0, align = 'CB', \
            size = '10p', font = 'Helvetica', colour = 'black', \
            clip = False, box_fill = None, angle = 0):
        """
        Add text to plot.
        x: x position
        y: y position
        text: text to add
        dx: x position offset
        dy: y position offset
        align: Left Centre Right, Top, Middle, Bottom
        size: font size
        font: font familly
        colour: font colour
        clip: crop text to map boundary
        box_fill: colour to fill text box with
        """
        cmd = [GMT, 'pstext', '-J', '-R', '-K', '-O', \
                '-D%s/%s' % (dx, dy), \
                '-F+f%s,%s,%s+j%s+a%s' % (size, font, colour, align, angle)]
        if not clip:
            cmd.append('-N')
        if box_fill != None:
            cmd.append('-G%s' % (box_fill))
        tproc = Popen(cmd, stdin = PIPE, stdout = self.psf, cwd = self.wd)
        tproc.communicate('%s %s %s\n' % (x, y, text))
        tproc.wait()

    def sites(self, site_names, shape = 'c', size = 0.1, \
            width = 0.8, colour = 'black', \
            fill = 'gainsboro', transparency = 50, spacing = 0.08, \
            font = 'Helvetica', font_size = '10p', font_colour = 'black'):
        """
        Add sites to map.
        site_names: list of sites to add from defined dictionary
            append ',LB' to change alignment to 'LB' or other
        """
        # step 1: add points on map
        sites_xy = '\n'.join([' '.join(map(str, sites[x.split(',')[0]][:2])) \
                for x in site_names])
        sproc = Popen([GMT, 'psxy', '-J', '-R', '-S%s%s' % (shape, size), \
                '-G%s@%s' % (fill, transparency), '-K', '-O', \
                '-W%s,%s' % (width, colour)], \
                stdin = PIPE, stdout = self.psf, cwd = self.wd)
        sproc.communicate(sites_xy)
        sproc.wait()

        # step 2: label points
        # array of x, y, alignment, name
        xyan = []
        for i, xy in enumerate(sites_xy.split('\n')):
            try:
                # user has decided to override position
                name, align = site_names[i].split(',')
            except ValueError:
                # using default position
                name = site_names[i]
                align = sites[name][2]
            xyan.append('%s %s %s' % (xy, align, name))

        tproc = Popen([GMT, 'pstext', '-J', '-R', '-K', '-O', \
                '-Dj%s/%s' % (spacing, spacing), \
                '-F+j+f%s,%s,%s+a0' % (font_size, font, font_colour)], \
                stdin = PIPE, stdout = self.psf, cwd = self.wd)
        tproc.communicate('\n'.join(xyan))
        tproc.wait()

    def water(self, colour = 'lightblue', res = '150k'):
        """
        Adds water areas.
        colour: colour of water
        res: resolution of GMT internal data (f,h,i,l,c)
                or use LINZ data (150k, 1250k, 1500k)
        """
        # GMT land areas are made up of smaller segments
        # as such you can see lines on them and affect visuals
        # therefore the entire area is filled, but then clipped to water
        # pscoast etc can also slightly overlay tickmark (map) outline

        # using LINZ data
        if len(res) > 1:
            # start cropping inverted (-N) land area
            Popen([GMT, 'psclip', '-J', '-R', '-K', '-O', \
                    LINZ_COAST[res], '-N'], \
                    stdout = self.psf, cwd = self.wd).wait()
            # fill map with water colour
            Popen([GMT, 'pscoast', '-J', '-R', '-G%s' % (colour), \
                '-Dc', '-K', '-O', '-S%s' % (colour)], \
                stdout = self.psf, cwd = self.wd).wait()
            # finish crop
            Popen([GMT, 'psclip', '-C', '-K', '-O'], \
                    stdout = self.psf, cwd = self.wd).wait()
            # also add lakes and rivers
            Popen([GMT, 'psxy', '-J', '-R', '-K', '-O', \
                    '-G%s' % (colour), LINZ_LAKE[res]], \
                    stdout = self.psf, cwd = self.wd).wait()
            Popen([GMT, 'psxy', '-J', '-R', '-K', '-O', \
                    '-G%s' % (colour), LINZ_RIVER[res]], \
                    stdout = self.psf, cwd = self.wd).wait()
            return

        # start cropping to only show wet areas
        Popen([GMT, 'pscoast', '-J', '-R', '-D%s' % (res), \
                '-Sc', '-K', '-O'], \
                stdout = self.psf, cwd = self.wd).wait()
        # fill land and water to prevent segment artifacts
        Popen([GMT, 'pscoast', '-J', '-R', '-G%s' % (colour), \
                '-Dc', '-K', '-O', '-S%s' % (colour)], \
                stdout = self.psf, cwd = self.wd).wait()
        # crop (-Q) land area off to show only water
        Popen([GMT, 'pscoast', '-J', '-R', '-Q', '-K', '-O'], \
                stdout = self.psf, cwd = self.wd).wait()

    def land(self, fill = 'lightgray', res = '150k'):
        """
        Fills land area.
        fill: colour of land
        res: resolution 'f' full, 'h' high, 'i' intermediate, 'l' low, 'c' crude
        """

        # LINZ correct res option
        if len(res) > 1:
            Popen([GMT, 'psxy', '-J', '-R', '-K', '-O', \
                    '-G%s' % (fill), LINZ_COAST[res]], \
                    stdout = self.psf, cwd = self.wd).wait()
            return

        # just like with water, land will show segment artifacts
        # therefore the whole area needs to be filled
        # then cropped to only include land
        # start cropping to only fill dry areas
        Popen([GMT, 'pscoast', '-J', '-R', '-D%s' % (res), \
                '-Gc', '-K', '-O'], \
                stdout = self.psf, cwd = self.wd).wait()
        # fill land and water to prevent segment artifacts
        Popen([GMT, 'pscoast', '-J', '-R', '-G%s' % (fill), \
                '-D%s' % (res), '-K', '-O', '-S%s' % (fill)], \
                stdout = self.psf, cwd = self.wd).wait()
        # crop (-Q) wet area off to show only land
        Popen([GMT, 'pscoast', '-J', '-R', '-Q', '-K', '-O'], \
                stdout = self.psf, cwd = self.wd).wait()

    def topo(self, topo_file, topo_file_illu = None, cpt = 'gray'):
        """
        Creates a topography surface using topo files and a colour palette.
        topo_file: file containing topography data
        topo_file: file containing illumination data corresponding to topo_file
            usually the same filename ending with '_i5'
            if not given then the above rule is assumed
        cpt: colour palette to use to display height
        """
        topo_file = os.path.abspath(topo_file)
        # assume illumination file if not explicitly given
        # assuming the last part of the file is a file extention
        if topo_file_illu == None:
            parts = topo_file.split('.')
            parts[-2] += '_i5'
            topo_file_illu = '.'.join(parts)

        # Q here makes NaN transparent
        Popen([GMT, 'grdimage', topo_file, '-I%s' % (topo_file_illu), \
                '-C%s' % (cpt), '-J', '-R', '-K', '-O', '-Q'], \
                stdout = self.psf, cwd = self.wd).wait()

    def basemap(self, land = 'darkgreen', water = 'lightblue', \
                topo = TOPO_HIGH, topo_cpt = 'green-brown', \
                coastlines = 'auto', \
                highway = 'auto', highway_colour = 'yellow', \
                road = 'auto', road_colour = 'white', \
                waternet = None, waternet_colour = 'darkblue'):
        """
        Adds land/water/features to map.
        highway: thickness of highway paths or None
        highway_colour: colour of highway paths
        road: thickness of road paths or None
        road_colour: colour of road paths
        """
        # auto sizing factor calculation
        region = map(float, self.history('R').split('/'))
        km = geo.ll_dist(region[0], region[2], region[1], region[3])
        size = mapproject(region[1], region[3], wd = self.wd, unit = 'inch')
        inch = sqrt(sum(np.power(size, 2)))
        refs = inch / (km * 0.618)

        if land != None:
            self.land(fill = land)
        if topo != None:
            if topo_cpt == 'green-brown':
                topo_cpt = CPTS['nztopo-green-brown']
            self.topo(topo, cpt = topo_cpt)
        if water != None:
            self.water(colour = water)
        if road != None:
            if road == 'auto':
                road = '%sp' % (refs * 2)
            self.path(LINZ_ROAD, width = road, colour = road_colour)
        if highway != None:
            if highway == 'auto':
                highway = '%sp' % (refs * 4)
            self.path(LINZ_HWY, width = highway, colour = highway_colour)
        if waternet != None:
            if waternet == 'auto':
                waternet = '%sp' % (refs * 0.1)
            self.path(CHCH_WATER, width = waternet, colour = waternet_colour)
        if coastlines != None:
            if coastlines == 'auto':
                coastlines = '%sp' % (refs * 3)
            self.coastlines(width = coastlines)

    def coastlines(self, width = 0.3, colour = 'black', res = '150k'):
        """
        Draws outline of land.
        width: thickness of line
        colour: colour of line
        res: resolution of coastlines
        """
        # LINZ correct high res option
        if len(res) > 1:
            Popen([GMT, 'psxy', '-J', '-R', '-K', '-O', \
                    '-W%s,%s' % (width, colour), LINZ_COAST[res]], \
                    stdout = self.psf, cwd = self.wd).wait()
            return

        # internal GMT GSHHG rough traces
        Popen([GMT, 'pscoast', '-J', '-R', '-D%s' % (res), '-K', '-O', \
                '-W%s,%s' % (width, colour)], \
                stdout = self.psf, cwd = self.wd).wait()

    def ticks(self, major = '60m', minor = '30m', sides = 'ws'):
        """
        Draws map ticks around the edge.
        Note if map doesn't have a left or bottom margin, these will be cut.
        Also part of the map outline may be drawn over by land and/or water.
        It is advisable therefore that ticks are added after area is finished.
        major: these increments have a longer tick
        minor: these increments have a short tick only
        sides: major increments on these sides are labeled with text
        """
        # add sides which aren't wanted as all have to be present
        sides = sides.upper()
        for direction in ['N', 'E', 'S', 'W']:
            if direction not in sides:
                sides = '%s%s' % (sides, direction.lower())

        p = Popen([GMT, 'psbasemap', '-J', '-R', '-K', '-O', \
                '-Ba%sf%s%s' % (major, minor, sides)], \
                stdout = self.psf, cwd = self.wd).wait()

    def points(self, in_data, is_file = True, shape = 't', size = 0.08, \
            fill = None, line = 'white', line_thickness = '0.8p', \
            cpt = None, cols = None, header = 0):
        """
        Adds points to map.
        in_data: file or text containing '\n' separated x, y positions to plot
        is_file: whether in_data is a filepath (True) or a string (False)
        shape: shape to plot at positions
        size: size of shape, skip or just units to read from data column
        fill: fill colour of shape (default transparent)
        line: line colour of shape
        line_thickness: how thick the outline is
        cpt: fill using cpt (input has 3 columns, xyv)
        cols: override columns to be used as specified by GMT '-i'
        header: number of input rows to skip
        """
        # check if input file actually exists
        if is_file and not os.path.exists(in_data):
            print('WARNING: %s not found, won\'t be plotted.' % (in_data))
            return

        if size == None:
            shaping = '-S%s' % (shape)
        else:
            shaping = '-S%s%s' % (shape, size)
        # build command based on optional fill and thickness
        cmd = [GMT, 'psxy', '-J', '-R', \
                shaping, '-K', '-O']
        if fill != None:
            cmd.append('-G%s' % (fill))
        elif cpt != None:
            cmd.append('-C%s' % (cpt))
        if line != None:
            cmd.append('-W%s,%s' % (line_thickness, line))
        if cols != None:
            cmd.append('-i%s' % (cols))
        if header > 0:
            cmd.append('-hi%d' % (header))

        if is_file:
            cmd.append(os.path.abspath(in_data))
            Popen(cmd, stdout = self.psf, cwd = self.wd).wait()
        else:
            p = Popen(cmd, stdin = PIPE, stdout = self.psf, cwd = self.wd)
            p.communicate(in_data)
            p.wait()

    def path(self, in_data, is_file = True, close = False, \
            width = '0.4p', colour = 'black', split = None, \
            straight = False, fill = None, cols = None):
        """
        Draws a path between points.
        in_data: either a filepath to file containing x, y points
                    or a string containing the x, y points
        is_file: whether in_data is a filepath (True) or a string (False)
        close: whether to close the path by joining the first and last points
        width: thickness of line
        colour: colour of line
        split: None continuous, '-' dashes, '.' dots
        straight: lines appear straight, do not use great circle path
        fill: fill inside area with this colour
        cols: override columns to be used as specified by GMT '-i'
        """
        # build command based on parameters
        cmd = [GMT, 'psxy', '-J', '-R', '-K', '-O']
        if width != None and colour != None:
            pen = '-W%s,%s' % (width, colour)
            if split != None:
                pen = '%s,%s' % (pen, split)
            cmd.append(pen)
        if close:
            cmd.append('-L')
        if straight:
            cmd.append('-A')
        if fill != None:
            cmd.append('-G%s' % fill)
        if cols != None:
            cmd.append('-i%s' % cols)

        if is_file:
            cmd.append(os.path.abspath(in_data))
            Popen(cmd, stdout = self.psf, cwd = self.wd).wait()
        else:
            p = Popen(cmd, stdin = PIPE, stdout = self.psf, cwd = self.wd)
            p.communicate(in_data)
            p.wait()

    def seismo(self, src, time, fmt = 'time', \
            width = '1p', colour = 'red', straight = True):
        """
        Plots seismograms on map.
        Note grep '--no-group-separator' only works in GNU GREP
        src: file contaning the seismogram data
        time: draw the seismogram up to this reading
        fmt: format of the src file
            'inc' values are read sequentially
            'time' values are read by time
        width: width of the seismo line
        colour: colour of the seismo line
        straight: don't draw great circle arcs -
                True for straight lon/lat line projections such as Mercator
                False if using other projecitons such as Transverse Merc.
        """
        src = os.path.abspath(src)
        # grep much faster than python
        # wd same as for GMT for consistency
        if fmt == 'time':
            gp = Popen(['grep', src, '-e', '^>TS%d ' % (time), \
                    '-A%d' % (time + 1)], stdout = PIPE, cwd = self.wd)
        elif fmt == 'inc':
            gp = Popen(['grep', src, '-e', '^>', '--no-group-separator', \
                    '-A%d' % (time + 1)], stdout = PIPE, cwd = self.wd)
        gmt_in = gp.communicate()[0]
        gp.wait()

        cmd = [GMT, 'psxy', '-J', '-R', '-N', '-K', '-O',
                '-W%s,%s' % (width, colour)]
        if straight:
            cmd.append('-A')
        sp = Popen(cmd, stdin = PIPE, stdout = self.psf, cwd = self.wd)
        sp.communicate(gmt_in)
        sp.wait()

    def dist_scale(self, x, y, length, pos = 'map', slat = None, \
                align = None, dx = 0, dy = 0, label = None, label_pos = None, \
                fancy = False):
        """
        Create a distance scale on map.
        x: x position
        y: y position
        length: length of scale (default in km or append GMT symbol)
        pos: x, y position style
        align: justification of scale
        slat: latitude at which scale is accurate
        dx: offset x by distance
        dy: offset y by distance
        label: label on scale (seems to only work with fancy = True)
        label_pos: show label on (t)op | (b)elow | (l)eft | (r)ight
        fancy: fancy scale has black and white strips, simple is a line
        """

        if slat == None:
            region = map(float, self.history('R').split('/'))
            # TODO: fix geographic midpoint calculation (make a function)
            slat = (region[3] + region[2]) / 2.

        cmd = [GMT, 'psbasemap', '-J', '-R', '-K', '-O']
        if GMT_MAJOR == 5 and GMT_MINOR < 2:
            # convert longitude, latitude location to offset
            if pos == 'map':
                x, y = mapproject(x, y, wd = self.wd)
            elif pos != 'plot':
                print('GMT < v5.2 DOES NOT SUPPORT THIS POSITIONING')
                return
            x += dx
            y += dy
            # old style positioning
            pos_spec = '-L%sx%s/%s/%s/%s' % ('f' * fancy, x, y, slat, length)
            if align != None:
                pos_spec = '%s+j%s' % (pos_spec, align)
            if label != None:
                pos_spec = '%s+l%s' % (pos_spec, label)
            cmd.append(pos_spec)
        else:
            # new style positioning
            pos_spec = '-L%s%s%s%s+c%s+w%s+o%s/%s' % (GMT52_POS[pos], x, \
                    '/' * (pos[:3] != 'rel'), y, slat, length, dx, dy)
            if align != None:
                pos_spec = '%s+j%s' % (pos_spec, align)
            if fancy:
                pos_spec = '%s+f' % (pos_spec)
            if label != None:
                pos_spec = '%s+l%s' % (pos_spec, label)
            if label_pos != None:
                pos_spec = '%s+a%s' % (pos_spec, label_pos.lower())
            cmd.append(pos_spec)

        Popen(cmd, stdout = self.psf, cwd = self.wd).wait()

    def cpt_scale(self, x, y, cpt, major, minor, label = None, \
            length = 5.0, thickness = 0.15, horiz = True, \
            arrow_f = True, arrow_b = False, log = False, \
            pos = 'plot', align = None, dx = 0, dy = 0, cross_tick = None):
        """
        Draws a colour palette legend.
        x: x position to place scale
        y: y position to place scale
        cpt: cpt to make scale for
        major: major tick increment (labeled)
        minor: minor tick increment (not labeled)
        label: text label next to scale
        length: how long to draw the scale
        thickness: how thick the scale should be drawn
        horiz: whether to make it horizontal (True) or vertical (False)
        arrow_f: show the forwards continuation arrow (above range)
        arrow_b: show the backwards continuation arrow (below range)
        pos: x and y position system; 'map' for user/mapping coords,
                'plot' for plot coords in distance units,
                'norm' for normalised (0-1) coords,
                'rel' for 2 char position (x, y) as with align
                'rel_out' as above but default align is opposite to this
                only 'plot' is available on GMT <5.2
        align: justification: 'L'eft 'C'entre 'R'ight, 'B'ottom 'M'iddle 'T'op
        dx: offset x position by distance units
        dy: offset y position by distance units
        cross_tick: tick increment through the colour bar
        #TODO: option for major and minor = 'auto' or None
        """
        # if the source is a file, make sure path isn't relative because cwd
        if os.path.exists(cpt):
            cpt = os.path.abspath(cpt)

        cmd = [GMT, 'psscale', '-C%s' % (cpt), '-K', '-O']

        # build command based on parameters
        if GMT_MINOR < 2:
            pos_spec = '-D%s/%s/%s/%s%s' % \
                    (x + dx, y + dy, length, thickness, 'h' * horiz)
            if arrow_f or arrow_b:
                cmd.append('-E%s%s' % ('f' * arrow_f, 'b' * arrow_b))
        else:
            if pos != 'plot':
                cmd.extend(['-R', '-J'])
            # mimic 5.1 default behaviour
            if align == None and pos == 'plot':
                if horiz:
                    align = 'CT'
                else:
                    align = 'LM'
            pos_spec = '-D%s%s%s%s+w%s/%s%s+o%s/%s' % \
                    (GMT52_POS[pos], x, '/' * (pos[:3] != 'rel'), y, \
                    length, thickness, '+h' * horiz, dx, dy)
            if arrow_f or arrow_b:
                pos_spec = '%s+e%s%s' % \
                        (pos_spec, 'f' * arrow_f, 'b' * arrow_b)
            if align != None:
                pos_spec = '%s+j%s' % (pos_spec, align)
        cmd.append(pos_spec)

        # TODO: fix annotation on log scales (if even possible)
        annotation = '-Ba%sf%s' % (major, minor)
        if cross_tick != None:
            annotation = '%sg%s' % (annotation, cross_tick)
        if label != None:
            if GMT_MINOR < 2:
                annotation = '%s:%s:' \
                        % (annotation, label.replace(':', ''))
            else:
                annotation = '%s+l%s' % (annotation, label)
        cmd.append(annotation)
        if log:
            cmd.append('-Q')

        Popen(cmd, stdout = self.psf, cwd = self.wd).wait()

    def overlay(self, xyv_file, cpt, dx = '1k', dy = '1k', \
            min_v = None, max_v = None, crop_grd = None, \
            custom_region = None, transparency = 40, climit = 1.0, \
            limit_low = None, limit_high = None, contours = None, \
            acontours = None, annot_back = 'white@40', \
            contour_thickness = 0.2, contour_colour = 'black', \
            contour_apl = 1, contour_mindist = None, cols = None, \
            land_crop = False, binary = True, font_size = '9p', \
            header = None):
        """
        Plot a GMT overlay aka surface.
        xyv_file: file containing x, y and amplitude values
        cpt: cpt to use to visualise data, None if only wanting contours
        dx: x resolution of the surface grid (lower = better quality)
        dy: y resolution of the surface grid
            default unit is longitude/latitude, k: kilometre, e: metre
        min_v: (aka low-cut) crop anything below this value (set to NaN)
        max_v: (aka high-cut) crop anything above this value
            if min_v > max_v set, crop area max_v -> min_v only
        crop_grd: GMT grd file containing wanted area = 1
        custom_region: grd area region, tuple(x_min, x_max, y_min, y_max)
                speedup is achieved by using a smaller region
        transparency: 0 opaque through 100 invisible
        climit: convergence limit: increasing can drastically improve speed
                if iteration diff is lower than this then result is kept
        limit_low: values below this will be equal to this
        limit_high: values abave this will be equal to this
                limits are one way to make sure values fit in CPT range
                it may be faster to use Numpy pre-processing
        contours: display contour lines every set value or None
        contour_thickness: thickness of contour lines
        contour_colour: colour of contour lines
        contour_apl: annotations per contour line
        contour_mindist: minimum distance between annotations
        cols: override columns to use, eg: '0,1,3'
        land_crop: crop overlay to land area
        font_size: size of font for contour annotations
        """
        # make sure paths aren't relative because work dir may change
        xyv_file = os.path.abspath(xyv_file)
        # name of intermediate file being worked on
        temp_grd = '%s/%s_temp.grd' % (self.wd, os.path.basename(xyv_file))

        # because we allow setting '-R', backup history file to reset after
        if custom_region != None:
            write_history(False, wd = self.wd)
            region = '-R%s/%s/%s/%s' % custom_region
        else:
            region = '-R'

        # create surface grid
        # TODO: use separate function
        if xyv_file[-4:] != '.grd':
            cmd = [GMT, 'surface', xyv_file, '-G%s' % (temp_grd), \
                    '-T0.0', '-I%s/%s' % (dx, dy), \
                    '-C%s' % (climit), region, '-fg']
            if binary:
                cmd.append('-bi3f')
            if limit_low != None:
                cmd.append('-Ll%s' % (limit_low))
            if limit_high != None:
                cmd.append('-Lu%s' % (limit_high))
            if cols != None:
                cmd.append('-i%s' % (cols))
            if header != None:
                cmd.append('-hi%d' % (header))
            # ignore stderr: usually because no data in area
            # algorithm in 'surface' is known to fail (no output) seen in 5.1
            for attempt in xrange(5):
                # stderr = self.sink
                Popen(cmd, cwd = self.wd).wait()
                if os.path.exists(temp_grd):
                    break
                else:
                    print('creating overlay grd attempt %d failed. trying again.' \
                            % (attempt + 1))
            if not os.path.exists(temp_grd):
                print('failed to create grd from %s. no overlay produced.' \
                        % (os.path.basename(xyv_file)))
                return
        else:
            copyfile(xyv_file, temp_grd)

        # crop to path area by grd file
        if crop_grd != None:
            Popen([GMT, 'grdmath', temp_grd, crop_grd, 'MUL', '=', temp_grd], \
                    cwd = self.wd).wait()

        # crop minimum/maximum/area values
        if min_v != None or max_v != None:
            if max_v == None or min_v < max_v:
                # values below min_v -> NaN
                cut = '-Sb%s/NaN' % (min_v)
            elif min_v == None or min_v < max_v:
                # values above max_v -> NaN
                cut = '-Sa%s/NaN' % (max_v)
            else:
                # values between max_v to min_v -> NaN
                cut = '-Si%s/%s/NaN' % (max_v, min_v)
            # ignore stderr: usually because no data in area
            Popen([GMT, 'grdclip', temp_grd, '-G%s' % (temp_grd), \
                    cut], stderr = self.sink, \
                    cwd = self.wd).wait()

        # restore '-R' if changed
        if custom_region != None:
            write_history(True, wd = self.wd)

        # clip path for land to crop overlay
        if land_crop:
            Popen([GMT, 'pscoast', '-J', '-R', '-Df', '-Gc', \
                    '-K', '-O'], stdout = self.psf, cwd = self.wd).wait()

        if cpt != None:
            # cpt may be internal or a file
            if os.path.exists(cpt):
                cpt = os.path.abspath(cpt)
            # add resulting grid onto map
            # here '-Q' will make NaN transparent
            cmd = [GMT, 'grdimage', temp_grd, '-J', '-R', '-C%s' % (cpt), \
                    '-t%s' % (transparency), '-Q', '-K', '-O']
            # ignore stderr: usually because no data in area
            Popen(cmd, stdout = self.psf, stderr = self.sink, \
                    cwd = self.wd).wait()

        # add contours
        if contours != None or acontours != None:
            cmd = [GMT, 'grdcontour', '-J', '-R', temp_grd, '-K', '-O', \
            '-W%s,%s' % (contour_thickness, contour_colour)]
            if contours != None:
                cmd.append('-C%s+f%s' % (contours, font_size))
            if acontours != None:
                annot_spec = '-A%s+f%s' % (acontours, font_size)
                if annot_back != None:
                    annot_spec = '%s+g%s' % (annot_spec, annot_back)
                cmd.append(annot_spec)
                if contour_mindist == None:
                    # assuming distance in points (default)
                    contour_mindist = '%sp' % \
                            (float(str(font_size).rstrip('cip')) * 3)
                cmd.append('-Gn%s/%s' % (contour_apl, contour_mindist))
            Popen(cmd, stdout = self.psf, stderr = self.sink, \
                    cwd = self.wd).wait()

        # apply land clip path
        if land_crop:
            Popen([GMT, 'pscoast', '-J', '-R', '-Q', '-K', '-O'], \
                    stdout = self.psf, cwd = self.wd).wait()

        # grd file not needed anymore, prevent clutter
        os.remove(temp_grd)

    def fault(self, in_path, is_srf = False, \
            hyp_shape = 'a', hyp_size = 0.35, \
            plane_width = '1p', plane_colour = 'black', \
            top_width = '2p', top_colour = 'black', \
            hyp_width = '1p', hyp_colour = 'black'):
        """
        Plot SRF fault plane onto map.
        Requires shared_srf.py, replaces addStandardFaultPlane.sh
        in_path: location of input file
        is_srf: if True, input is SRF file. if False, is Corners file.
        hyp_shape: shape to plot at hypocentre 'a' for a star
        hyp_size: size of hypocentre shape
        plane_width: width of line making up fault planes
        plane_colour: colour of line making up fault planes
        top_width: as above for the top edge
        top_colour: as above for the top edge
        hyp_width: as above for hyp_shape outline
        hyp_colour: as above for hyp_shape outline
        """
        if is_srf:
            # use SRF library to retrieve info
            bounds = get_bounds(in_path)
            hypocentre = get_hypo(in_path)

            # process for input into GMT
            gmt_bounds = [['%s %s' % tuple(corner) for corner in plane] \
                    for plane in bounds]
            top_edges = '\n>\n'.join(['\n'.join(corners[:2]) \
                    for corners in gmt_bounds])
            all_edges = '\n>\n'.join(['\n'.join(corners) \
                    for corners in gmt_bounds])
            hypocentre = '%s %s' % tuple(hypocentre)
        else:
            # standard corners file
            # XXX: don't think this works
            bounds = []
            corners = []
            with open(in_path) as cf:
                for line in cf:
                    if line[0] != '>':
                        # not a comment
                        corners.append(line)
                    elif len(corners):
                        # break in long lat stream
                        bounds.append(corners)
                        corners = []
                bounds.append(corners)

            # process for input into GMT
            hypocentre = bounds[0][0]
            top_edges = '>\n'.join([''.join(c[:2]) for c in bounds[1:]])
            all_edges = '>\n'.join([''.join(c) for c in bounds[1:]])

        # plot planes
        planep = Popen([GMT, 'psxy', '-J', '-R', '-L', '-K', '-O', \
                '-W%s,%s,-' % (plane_width, plane_colour)], \
                stdin = PIPE, stdout = self.psf, cwd = self.wd)
        planep.communicate(all_edges)
        planep.wait()
        # plot top edges
        topp = Popen([GMT, 'psxy', '-J', '-R', '-K', '-O', \
                '-W%s,%s' % (top_width, top_colour)], \
                stdin = PIPE, stdout = self.psf, cwd = self.wd)
        topp.communicate(top_edges)
        topp.wait()
        # hypocentre
        hypp = Popen([GMT, 'psxy', '-J', '-R', '-K', '-O', \
                '-W%s,%s' % (hyp_width, hyp_colour), \
                '-S%s%s' % (hyp_shape, hyp_size)], \
                stdin = PIPE, stdout = self.psf, cwd = self.wd)
        hypp.communicate(hypocentre)
        hypp.wait()

    def beachballs(self, data, fmt = 'c', is_file = False, scale = 0.5, \
            colour = 'black', extensive = 'white', text_under = False, \
            header = 0, depths = None):
        """
        Plots focal mechanisms (beachballs).
        data: as defined by psmeca -S:
            gmt.soest.hawaii.edu/doc/5.1.0/supplements/meca/psmeca.html
        fmt: format of data (which -S format is used)
        is_file: whether data is a filepath (True) or string (False)
        scale: radius of a magnitude 5 beachball
        colour: colour of compressional quadrants
        extensive: colour of extensive quadrants
        text_under: True will place optional text under instead of above
        header: number of lines in data to skip
        depths: None to plot all beachballs or
            a tuple (depth_min, depth_max) to only plot a subset
        """
        cmd = [GMT, 'psmeca', '-J', '-R', '-K', '-O', \
                '-S%s%s%s' % (fmt, scale, 'u' * text_under), \
                '-G%s' % (colour), '-E%s' % (extensive), \
                '-hi%d' % header]
        if depths != None:
            cmd.append('-D%s/%s' % (depths))

        if is_file:
            cmd.append(os.path.abspath(data))
            Popen(cmd, stdout = self.psf, cwd = self.wd)
        else:
            meca = Popen(cmd, stdin = PIPE, stdout = self.psf, cwd = self.wd)
            meca.communicate(data)
            meca.wait()

    def image(self, x, y, image_path, width = '2i', align = None, \
            transparent = None, pos = 'map', dx = 0, dy = 0):
        """
        Place image or EPS file on map.
        x: x position in 'pos' based units
        y: y position in 'pos' based units
        image_path: path to image to overlay (png and jpg tested on hypocentre)
            supported formats depend on GDAL linking
        width: result width of image to overlay
        align: justification: 'L'eft 'C'entre 'R'ight, 'B'ottom 'M'iddle 'T'op
        transparent: define colour to replace with transparency
        pos: x and y position system; 'map' for user/mapping coords,
                'plot' for plot coords in distance units,
                'norm' for normalised (0-1) coords,
                'rel' for 2 char position (x, y) as with align
                'rel_out' as above but default align is opposite to this
                only 'map' and 'plot' are available on GMT 5.1
        dx: offset x position by distance units
        dy: offset y position by distance units
        """
        # base commands for all GMT versions
        cmd = [GMT, 'psimage', os.path.abspath(image_path), '-K', '-O']

        if GMT_MAJOR == 5 and GMT_MINOR < 2:
            # convert longitude, latitude location to offset
            if pos == 'map':
                x, y = mapproject(x, y, wd = self.wd)
            elif pos != 'plot':
                print('GMT < v5.2 DOES NOT SUPPORT THIS POSITIONING')
                return
            x += dx
            y += dy
            # old style positioning
            # potentially either -W (width) or -E (input DPI)
            if align != None:
                pos_spec = '-C%s/%s/%s' % (x, y, align)
            else:
                pos_spec = '-C%s/%s' % (x, y)
            cmd.extend(['-W%s' % (width), pos_spec])
        else:
            # new style positioning
            if pos != 'plot':
                cmd.extend(['-J', '-R'])
            pos_spec = '-D%s%s%s%s+w%s+o%s/%s' % (GMT52_POS[pos], x, \
                    '/' * (pos[:3] != 'rel'), y, width, dx, dy)
            if align != None:
                pos_spec = '%s+j%s' % (pos_spec, align)
            cmd.append(pos_spec)
        # replace a colour with transparency
        if transparent != None:
            cmd.append('-Gt%s' % (transparent))
        # run GMT
        Popen(cmd, stdout = self.psf, cwd = self.wd).wait()

    def finalise(self):
        """
        Finalises the postscript.
        """
        # finalisation by running a GMT command without '-K'
        Popen([GMT, 'psxy', '-J', '-R', '-O', '-T'], \
                stdout = self.psf, cwd = self.wd).wait()
        # no more modifications allowed
        self.psf.close()

    def leave(self):
        """
        Alternative to finalise where the file is only closed.
        Useful if this file is opened later.
        """
        self.psf.close()

    def enter(self):
        """
        Only used after leave. Opens file again to continue editing.
        Useful if file is to be externally modified in-between.
        """
        self.psf = open(self.pspath, 'a')

    def png(self, out_dir = None, dpi = 96, clip = True, portrait = False):
        """
        Renders a PNG from the PS.
        Unfortunately relatively slow.
        Could be modified for more formats if needed.
        out_dir: folder to put output in (name as input, different extention)
        dpi: pixels per inch
        clip: whether to crop all whitespace
        portrait: rotate page right way up
        """
        # default to output in same directory
        if out_dir == None:
            out_dir = os.path.dirname(self.pspath)

        # A pspath only containing a filename would result in ''
        if out_dir == '':
            out_dir = '.'

        cmd = [GMT, psconvert, self.pspath, '-TG', \
                '-E%s' % (dpi), '-D%s' % (out_dir)]
        if clip:
            cmd.append('-A')
        if portrait:
            cmd.append('-P')
        call(cmd)

