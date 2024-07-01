import numpy as np
import sys
import time
import pyuvdata
import multiprocessing
from newcal import calibration_optimization, caldata


def calibration_per_pol(
    data_file_path,
    model_file_path,
    data_use_column="DATA",
    model_use_column="MODEL_DATA",
    gain_init_calfile=None,
    gain_init_to_vis_ratio=True,
    gain_init_stddev=0.0,
    N_feed_pols=None,
    feed_polarization_array=None,
    min_cal_baseline_m=None,
    max_cal_baseline_m=None,
    min_cal_baseline_lambda=None,
    max_cal_baseline_lambda=None,
    lambda_val=100,
    xtol=1e-6,
    maxiter=100,
    get_crosspol_phase=True,
    parallel=True,
    max_processes=40,
    verbose=False,
    log_file_path=None,
):
    """
    Top-level wrapper for running calibration per polarization. Function creates
    a CalData object, updates the gains attribute, and returns a pyuvdata UVCal
    object containing the calibration solutions. Here the XX and YY visibilities
    are calibrated individually and the cross-polarization phase is applied from
    the XY and YX visibilities after the fact. Option to parallelize calibration
    across frequency.

    Parameters
    ----------
    data_file_path : str
        Path to the ms or uvfits file containing the data visibilities.
    model_file_path : str
        Path to the ms or uvfits file containing the model visibilities.
    data_use_column : str
        Column in an ms file to use for the data visibilities. Used only if
        data_file_path points to an ms file. Default "DATA".
    model_use_column : str
        Column in an ms file to use for the model visibilities. Used only if
        data_file_path points to an ms file. Default "MODEL_DATA".
    gain_init_calfile : str or None
        Default None. If not None, provides a path to a pyuvdata-formatted
        calfits file containing gains values for calibration initialization.
    gain_init_to_vis_ratio : bool
        Used only if gain_init_calfile is None. If True, initializes gains
        to the median ratio between the amplitudes of the model and data
        visibilities. If False, the gains are initialized to 1. Default
        True.
    gain_init_stddev : float
        Default 0.0. Standard deviation of a random complex Gaussian
        perturbation to the initial gains.
    N_feed_pols : int
        Default min(2, N_vis_pols). Number of feed polarizations, equal to
        the number of gain values to be calculated per antenna.
    feed_polarization_array : array of int or None
        Feed polarizations to calibrate. Shape (N_feed_pols,). Options are
        -5 for X or -6 for Y. Default None. If None, feed_polarization_array
        is set to ([-5, -6])[:N_feed_pols].
    min_cal_baseline_m : float or None
        Minimum baseline length, in meters, to use in calibration. If both
        min_cal_baseline_m and min_cal_baseline_lambda are None, arbitrarily
        short baselines are used. Default None.
    max_cal_baseline_m : float or None
        Maximum baseline length, in meters, to use in calibration. If both
        max_cal_baseline_m and max_cal_baseline_lambda are None, arbitrarily
        long baselines are used. Default None.
    min_cal_baseline_lambda : float or None
        Minimum baseline length, in wavelengths, to use in calibration. If
        both min_cal_baseline_m and min_cal_baseline_lambda are None,
        arbitrarily short baselines are used. Default None.
    max_cal_baseline_lambda : float or None
        Maximum baseline length, in wavelengths, to use in calibration. If
        both max_cal_baseline_m and max_cal_baseline_lambda are None,
        arbitrarily long baselines are used. Default None.
    lambda_val : float
        Weight of the phase regularization term; must be positive. Default
        100.
    xtol : float
        Accuracy tolerance for optimizer. Default 1e-6.
    maxiter : int
        Maximum number of iterations for the optimizer. Default 100.
    get_crosspol_phase : bool
        If True, crosspol phase is calculated. Default True.
    parallel : bool
        Set to True to parallelize across frequency with multiprocessing.
        Default True if Nfreqs > 1.
    max_processes : int or None
        Maximum number of multithreaded processes to use. Applicable only if
        parallel is True. If None, uses the multiprocessing default. Default 40.
    verbose : bool
        Set to True to print optimization outputs. Default False.
    log_file_path : str or None
        Path to the log file. Default None.
    Returns
    -------
    uvcal : pyuvdata UVCal object
    """

    if log_file_path is not None:
        stdout_orig = sys.stdout
        stderr_orig = sys.stderr
        sys.stdout = sys.stderr = log_file_new = open(log_file_path, "w")

    start_time = time.time()

    if parallel:  # Start multiprocessing pool
        if max_processes is None:
            pool = multiprocessing.Pool()
        else:
            pool = multiprocessing.Pool(processes=max_processes)

    if verbose:
        print("Reading data...")
        sys.stdout.flush()
        data_read_start_time = time.time()

    # Read data
    data = pyuvdata.UVData()
    if data_file_path.endswith(".ms"):
        data.read_ms(data_file_path, data_column=data_use_column)
    elif data_file_path.endswith(".uvfits"):
        data.read_uvfits(data_file_path)
    else:
        print(f"ERROR: Unsupported file type for data file {data_file_path}. Exiting.")
        sys.exit(1)
    model = pyuvdata.UVData()
    if model_file_path.endswith(".ms"):
        model.read_ms(model_file_path, data_column=model_use_column)
    elif model_file_path.endswith(".uvfits"):
        model.read_uvfits(model_file_path)
    else:
        print(
            f"ERROR: Unsupported file type for model file {model_file_path}. Exiting."
        )

    if verbose:
        print(
            f"Done. Data read time {(time.time() - data_read_start_time)/60.} minutes."
        )
        print("Formatting data...")
        sys.stdout.flush()
        data_format_start_time = time.time()

    caldata_obj = caldata.CalData()
    caldata_obj.load_data(
        data,
        model,
        gain_init_calfile=gain_init_calfile,
        gain_init_to_vis_ratio=gain_init_to_vis_ratio,
        gain_init_stddev=gain_init_stddev,
        N_feed_pols=N_feed_pols,
        feed_polarization_array=feed_polarization_array,
        min_cal_baseline_m=min_cal_baseline_m,
        max_cal_baseline_m=max_cal_baseline_m,
        min_cal_baseline_lambda=min_cal_baseline_lambda,
        max_cal_baseline_lambda=max_cal_baseline_lambda,
        lambda_val=lambda_val,
    )

    if caldata_obj.Nfreqs < 2:
        parallel = False
        pool.close()
        pool.join()

    if verbose:
        print(
            f"Done. Data formatting time {(time.time() - data_format_start_time)/60.} minutes."
        )
        print("Running calibration optimization...")
        sys.stdout.flush()

    calibrate_caldata_per_pol(
        caldata_obj,
        xtol=xtol,
        maxiter=maxiter,
        get_crosspol_phase=get_crosspol_phase,
        parallel=parallel,
        verbose=verbose,
        pool=pool,
    )

    # Convert to UVCal object
    uvcal = caldata_obj.convert_to_uvcal()

    if verbose:
        print(f"Total processing time {(time.time() - start_time)/60.} minutes.")
        sys.stdout.flush()

    if log_file_path is not None:
        sys.stdout = stdout_orig
        sys.stderr = stderr_orig
        log_file_new.close()

    return uvcal


def calibrate_caldata_per_pol(
    caldata_obj,
    xtol=1e-6,
    maxiter=100,
    get_crosspol_phase=True,
    parallel=True,
    verbose=False,
    pool=None,
):
    """
    Run calibration per polarization. Updates the gains attribute of caldata_obj
    with calibrated values. Here the XX and YY visibilities are calibrated
    individually and the cross-polarization phase is applied fromthe XY and YX
    visibilities after the fact. Option to parallelize calibration across frequency.

    Parameters
    ----------
    caldata_obj : CalData
        CalData object containing the data and model visibilities for calibration.
    xtol : float
        Accuracy tolerance for optimizer. Default 1e-6.
    maxiter : int
        Maximum number of iterations for the optimizer. Default 100.
    get_crosspol_phase : bool
        If True, crosspol phase is calculated. Default True.
    parallel : bool
        Set to True to parallelize across frequency with multiprocessing.
        Default True if Nfreqs > 1.
    verbose : bool
        Set to True to print optimization outputs. Default False.
    pool : multiprocessing.pool.Pool or None
        Pool for multiprocessing. Must not be None if parallel=True.
    """

    if np.max(caldata_obj.visibility_weights) == 0.0:
        print("ERROR: All data flagged.")
        sys.stdout.flush()
        caldata_obj.gains[:, :, :] = np.nan + 1j * np.nan
    else:

        # Expand CalData object into per-frequency objects
        caldata_list = caldata_obj.expand_in_frequency()

        optimization_start_time = time.time()

        if parallel:
            args_list = []
            for freq_ind in range(caldata_obj.Nfreqs):
                args = (
                    caldata_list[freq_ind],
                    xtol,
                    maxiter,
                    verbose,
                    get_crosspol_phase,
                    True,
                )
                args_list.append(args)
            result = pool.starmap(
                calibration_optimization.run_calibration_optimization_per_pol_single_freq,
                args_list,
            )
            pool.close()
            for freq_ind in range(caldata_obj.Nfreqs):
                caldata_obj.gains[:, [freq_ind], :] = result[freq_ind]
            pool.join()
        else:
            for freq_ind in range(caldata_obj.Nfreqs):
                calibration_optimization.run_calibration_optimization_per_pol_single_freq(
                    caldata_list[freq_ind],
                    xtol,
                    maxiter,
                    verbose=verbose,
                    get_crosspol_phase=get_crosspol_phase,
                )
                caldata_obj.gains[:, [freq_ind], :] = caldata_list[freq_ind].gains[
                    :, [0], :
                ]

        if verbose:
            print(
                f"Done. Optimization time: {caldata_obj.Nfreqs} frequency channels in {(time.time() - optimization_start_time)/60.} minutes"
            )
            sys.stdout.flush()


def absolute_calibration(
    data,
    model,
    data_use_column="DATA",
    model_use_column="MODEL_DATA",
    N_feed_pols=None,
    feed_polarization_array=None,
    min_cal_baseline_m=None,
    max_cal_baseline_m=None,
    min_cal_baseline_lambda=None,
    max_cal_baseline_lambda=None,
    xtol=1e-10,
    maxiter=100,
    verbose=False,
    log_file_path=None,
):
    """
    Top-level wrapper for running absolute calibration ("abscal").

    Parameters
    ----------
    data : str or UVData
        Path to the pyuvdata-readable file containing the relatively calibrated
        data visibilities or a pyuvdata UVData object.
    model : str or UVData
        Path to the pyuvdata-readable file containing the model visibilities
        or a pyuvdata UVData object.
    data_use_column : str
        Column in an ms file to use for the data visibilities. Used only if
        data_file_path points to an ms file. Default "DATA".
    model_use_column : str
        Column in an ms file to use for the model visibilities. Used only if
        data_file_path points to an ms file. Default "MODEL_DATA".
    N_feed_pols : int
        Default min(2, N_vis_pols). Number of feed polarizations, equal to
        the number of gain values to be calculated per antenna.
    feed_polarization_array : array of int or None
        Feed polarizations to calibrate. Shape (N_feed_pols,). Options are
        -5 for X or -6 for Y. Default None. If None, feed_polarization_array
        is set to ([-5, -6])[:N_feed_pols].
    min_cal_baseline_m : float or None
        Minimum baseline length, in meters, to use in calibration. If both
        min_cal_baseline_m and min_cal_baseline_lambda are None, arbitrarily
        short baselines are used. Default None.
    max_cal_baseline_m : float or None
        Maximum baseline length, in meters, to use in calibration. If both
        max_cal_baseline_m and max_cal_baseline_lambda are None, arbitrarily
        long baselines are used. Default None.
    min_cal_baseline_lambda : float or None
        Minimum baseline length, in wavelengths, to use in calibration. If
        both min_cal_baseline_m and min_cal_baseline_lambda are None,
        arbitrarily short baselines are used. Default None.
    max_cal_baseline_lambda : float or None
        Maximum baseline length, in wavelengths, to use in calibration. If
        both max_cal_baseline_m and max_cal_baseline_lambda are None,
        arbitrarily long baselines are used. Default None.
    xtol : float
        Accuracy tolerance for optimizer. Default 1e-10.
    maxiter : int
        Maximum number of iterations for the optimizer. Default 100.
    verbose : bool
        Set to True to print optimization outputs. Default False.
    log_file_path : str or None
        Path to the log file. Default None.
    Returns
    -------
    abscal_params : array of float
        Shape (3, Nfreqs, N_feed_pols). abscal_params[0, :, :] are the overall amplitudes,
        abscal_params[1, :, :] are the x-phase gradients in units 1/m, and abscal_params[2, :, :]
        are the y-phase gradients in units 1/m.
    """

    if log_file_path is not None:
        stdout_orig = sys.stdout
        stderr_orig = sys.stderr
        sys.stdout = sys.stderr = log_file_new = open(log_file_path, "w")

    start_time = time.time()

    if verbose:
        print("Reading data...")
        sys.stdout.flush()
        data_read_start_time = time.time()

    print_data_read_time = False
    if isinstance(data, str):  # Read data
        print_data_read_time = True
        data_file_path = np.copy(data)
        data = pyuvdata.UVData()
        if data_file_path.endswith(".ms"):
            data.read_ms(data_file_path, data_column=data_use_column)
        else:
            data.read(data_file_path)
    if isinstance(model, str):  # Read model
        print_data_read_time = True
        model_file_path = np.copy(model)
        model = pyuvdata.UVData()
        if model_file_path.endswith(".ms"):
            model.read_ms(model_file_path, data_column=model_use_column)
        else:
            model.read(model_file_path)

    if verbose and print_data_read_time:
        print(
            f"Done. Data read time {(time.time() - data_read_start_time)/60.} minutes."
        )
        sys.stdout.flush()
    if verbose:
        print("Formatting data...")
        sys.stdout.flush()
        data_format_start_time = time.time()

    caldata_obj = caldata.CalData()
    caldata_obj.load_data(
        data,
        model,
        N_feed_pols=N_feed_pols,
        feed_polarization_array=feed_polarization_array,
        min_cal_baseline_m=min_cal_baseline_m,
        max_cal_baseline_m=max_cal_baseline_m,
        min_cal_baseline_lambda=min_cal_baseline_lambda,
        max_cal_baseline_lambda=max_cal_baseline_lambda,
    )

    if verbose:
        print(
            f"Done. Data formatting time {(time.time() - data_format_start_time)/60.} minutes."
        )
        print("Running calibration optimization...")
        sys.stdout.flush()

    # Expand CalData object into per-frequency objects
    caldata_list = caldata_obj.expand_in_frequency()

    optimization_start_time = time.time()

    for freq_ind in range(caldata_obj.Nfreqs):
        calibration_optimization.run_abscal_optimization_single_freq(
            caldata_list[freq_ind],
            xtol,
            maxiter,
            verbose=verbose,
        )
        caldata_obj.abscal_params[:, [freq_ind], :] = caldata_list[
            freq_ind
        ].abscal_params[:, [0], :]

    if verbose:
        print(
            f"Done. Optimization time: {caldata_obj.Nfreqs} frequency channels in {(time.time() - optimization_start_time)/60.} minutes"
        )
        print(f"Total processing time {(time.time() - start_time)/60.} minutes.")
        sys.stdout.flush()

    if log_file_path is not None:
        sys.stdout = stdout_orig
        sys.stderr = stderr_orig
        log_file_new.close()

    return caldata_obj.abscal_params


def apply_abscal(uvdata, abscal_params, feed_polarization_array, inplace=False):
    """
    Apply absolute calibration solutions to data.

    Parameters
    ----------
    uvdata : pyuvdata UVData object
        pyuvdata UVData object containing the data.
    abscal_params : array of float
        Shape (3, Nfreqs, N_feed_pols). abscal_params[0, :, :] are the overall amplitudes,
        abscal_params[1, :, :] are the x-phase gradients in units 1/m, and abscal_params[2, :, :]
        are the y-phase gradients in units 1/m.
    feed_polarization_array : array of int
        Shape (N_feed_pols). Array of polarization integers. Indicates the
        ordering of the polarization axis of the gains. X is -5 and Y is -6.
    inplace : bool
        If True, updates uvdata. If False, returns a new UVData object.

    Returns
    -------
    uvdata_new : pyuvdata UVData object
        Returned only if inplace is False.
    """

    if not inplace:
        uvdata_new = uvdata.copy()

    # Get antenna locations
    # Create gains expand matrices
    gains_exp_mat_1 = np.zeros((uvdata.Nblts, len(uvdata.antenna_numbers)), dtype=int)
    gains_exp_mat_2 = np.zeros((uvdata.Nblts, len(uvdata.antenna_numbers)), dtype=int)
    for baseline in range(uvdata.Nblts):
        gains_exp_mat_1[
            baseline,
            np.where(uvdata.antenna_numbers == uvdata.ant_1_array[baseline]),
        ] = 1
        gains_exp_mat_2[
            baseline,
            np.where(uvdata.antenna_numbers == uvdata.ant_2_array[baseline]),
        ] = 1
    antpos_ecef = (
        uvdata.antenna_positions + uvdata.telescope_location
    )  # Get antennas positions in ECEF
    antpos_enu = pyuvdata.utils.ENU_from_ECEF(
        antpos_ecef, *uvdata.telescope_location_lat_lon_alt
    )  # Convert to topocentric (East, North, Up or ENU) coords.
    antpos_en = antpos_enu[:, :2]
    ant1_positions = np.matmul(gains_exp_mat_1, antpos_en)
    ant2_positions = np.matmul(gains_exp_mat_2, antpos_en)

    for vis_pol_ind, vis_pol in enumerate(uvdata.polarization_array):
        if vis_pol == -5:
            pol1 = pol2 = np.where(feed_polarization_array == -5)[0][0]
        elif vis_pol == -6:
            pol1 = pol2 = np.where(feed_polarization_array == -6)[0][0]
        elif vis_pol == -7:
            pol1 = np.where(feed_polarization_array == -5)[0][0]
            pol2 = np.where(feed_polarization_array == -6)[0][0]
        elif vis_pol == -8:
            pol1 = np.where(feed_polarization_array == -6)[0][0]
            pol2 = np.where(feed_polarization_array == -5)[0][0]
        else:
            print(f"ERROR: Polarization {vis_pol} not recognized.")
            sys.exit(1)

        amp_term = (
            abscal_params[0, :, pol1] * abscal_params[0, :, pol2]
        )  # Shape (Nfreqs,)
        phase_correction = np.exp(
            1j
            * (
                abscal_params[1, np.newaxis, :, pol1] * ant1_positions[:, np.newaxis, 0]
                - abscal_params[1, np.newaxis, :, pol2]
                * ant2_positions[:, np.newaxis, 0]
                + abscal_params[2, np.newaxis, :, pol1]
                * ant1_positions[:, np.newaxis, 1]
                - abscal_params[2, np.newaxis, :, pol2]
                * ant2_positions[:, np.newaxis, 1]
            )
        )  # Shape (Nbls, Nfreqs,)

        if inplace:
            uvdata.data_array[:, :, :, vis_pol_ind] *= (
                amp_term[np.newaxis, np.newaxis, :] * phase_correction[:, np.newaxis, :]
            )
        else:
            uvdata_new.data_array[:, :, :, vis_pol_ind] *= (
                amp_term[np.newaxis, np.newaxis, :] * phase_correction[:, np.newaxis, :]
            )

    if not inplace:
        return uvdata_new


def get_dwcal_weights_from_delay_spectra(
    caldata,
    delay_spectrum_variance,
    bl_length_bin_edges,
    delay_axis,
    oversample_factor=128,
):
    """
    This function calculates the matrix that captures delay weighting (or frequency
    covariance). The input is an array of expected variances as a function of baseline
    length and delay.

    Parameters
    ----------
    caldata : CalData object
    delay_spectrum_variance : array of float
        Array containing the expected variance as a function of baseline length and delay.
        Shape (Nbins, Ndelays,).
    bl_length_bin_edges : array of float
        Defines the baseline length axis of delay_spectrum_variance. Values correspond to
        limits of each baseline length bin. Shape (Nbins+1,).
    delay_axis : array of float
        Defines the delay axis of delay_spectrum_variance. Shape (Ndelays,).
    oversample_factor : int
        Factor by which to oversample the delay axis. Setting > 1 reduces Fourier aliasing
        effects. Default 128.
    """

    bl_lengths = np.sqrt(np.sum(caldata.uv_array**2.0, axis=1))
    delay_array_use = np.fft.fftfreq(
        caldata.Nfreqs * int(oversample_factor), d=caldata.channel_width
    )
    dwcal_variance_use = np.zeros(
        (
            caldata.Nbls,
            caldata.Nfreqs * int(oversample_factor),
        ),
        dtype=float,
    )
    for bl_ind, bl_length in enumerate(bl_lengths):
        bin_ind = np.max(np.where(bl_length_bin_edges <= bl_length)[0])
        if (bin_ind == len(bl_length_bin_edges) - 1) or (
            not bl_length_bin_edges[bin_ind + 1] > bl_length
        ):
            print(
                f"WARNING: Baseline length range does not cover baseline of length {bl_length} m. Skipping."
            )
            continue
        dwcal_variance_use[bl_ind, :] = np.interp(
            delay_array_use, delay_axis, delay_spectrum_variance[bin_ind, :]
        )

    freq_weighting = np.fft.ifft(1.0 / dwcal_variance_use, axis=1)
    freq_weighting = freq_weighting[
        :, : caldata.Nfreqs
    ]  # Truncate frequency axis to remove oversampling
    weight_mat = np.zeros((caldata.Nbls, caldata.Nfreqs, caldata.Nfreqs), dtype=complex)
    for freq_ind1 in range(caldata.Nfreqs):
        for freq_ind2 in range(caldata.Nfreqs):
            if freq_ind1 < freq_ind2:
                weight_mat[:, freq_ind1, freq_ind2] = np.conj(
                    freq_weighting[:, np.abs(freq_ind1 - freq_ind2)]
                )
            else:
                weight_mat[:, freq_ind1, freq_ind2] = freq_weighting[
                    :, np.abs(freq_ind1 - freq_ind2)
                ]

    # Make normalization match that of the identity matrix
    normalization_factor = (
        caldata.Nfreqs * caldata.Nbls / np.sum(np.trace(weight_mat, axis1=1, axis2=2))
    )
    weight_mat *= normalization_factor

    caldata.dwcal_inv_covariance = np.repeat(
        np.repeat(weight_mat[np.newaxis, :, :, :, np.newaxis], caldata.Ntimes, axis=0),
        caldata.N_vis_pols,
        axis=4,
    )  # Use the same matrix for all times and polarizations


def dw_absolute_calibration(
    data,
    model,
    delay_spectrum_variance,
    bl_length_bin_edges,
    delay_axis,
    data_use_column="DATA",
    model_use_column="MODEL_DATA",
    initial_abscal_params=None,
    N_feed_pols=None,
    feed_polarization_array=None,
    min_cal_baseline_m=None,
    max_cal_baseline_m=None,
    min_cal_baseline_lambda=None,
    max_cal_baseline_lambda=None,
    xtol=1e-10,
    maxiter=100,
    verbose=False,
    log_file_path=None,
):
    """
    Top-level wrapper for running absolute calibration ("abscal") with delay weighting.

    Parameters
    ----------
    data : str or UVData
        Path to the pyuvdata-readable file containing the relatively calibrated
        data visibilities or a pyuvdata UVData object.
    model : str or UVData
        Path to the pyuvdata-readable file containing the model visibilities
        or a pyuvdata UVData object.
    delay_spectrum_variance : array of float
        Array containing the expected variance as a function of baseline length and delay.
        Shape (Nbins, Ndelays,).
    bl_length_bin_edges : array of float
        Defines the baseline length axis of delay_spectrum_variance. Values correspond to
        limits of each baseline length bin. Shape (Nbins+1,).
    delay_axis : array of float
        Defines the delay axis of delay_spectrum_variance. Shape (Ndelays,).
    data_use_column : str
        Column in an ms file to use for the data visibilities. Used only if
        data_file_path points to an ms file. Default "DATA".
    model_use_column : str
        Column in an ms file to use for the model visibilities. Used only if
        data_file_path points to an ms file. Default "MODEL_DATA".
    initial_abscal_params : array of float
        Parameters to initialize with. Shape (3, Nfreqs, N_feed_pols). abscal_params[0, :, :]
        are the overall amplitudes, abscal_params[1, :, :] are the x-phase gradients in units
        1/m, and abscal_params[2, :, :] are the y-phase gradients in units 1/m. Currently the
        frequency and polarization axes must match those in the data (this should be fixed).
    N_feed_pols : int
        Default min(2, N_vis_pols). Number of feed polarizations, equal to
        the number of gain values to be calculated per antenna.
    feed_polarization_array : array of int or None
        Feed polarizations to calibrate. Shape (N_feed_pols,). Options are
        -5 for X or -6 for Y. Default None. If None, feed_polarization_array
        is set to ([-5, -6])[:N_feed_pols].
    min_cal_baseline_m : float or None
        Minimum baseline length, in meters, to use in calibration. If both
        min_cal_baseline_m and min_cal_baseline_lambda are None, arbitrarily
        short baselines are used. Default None.
    max_cal_baseline_m : float or None
        Maximum baseline length, in meters, to use in calibration. If both
        max_cal_baseline_m and max_cal_baseline_lambda are None, arbitrarily
        long baselines are used. Default None.
    min_cal_baseline_lambda : float or None
        Minimum baseline length, in wavelengths, to use in calibration. If
        both min_cal_baseline_m and min_cal_baseline_lambda are None,
        arbitrarily short baselines are used. Default None.
    max_cal_baseline_lambda : float or None
        Maximum baseline length, in wavelengths, to use in calibration. If
        both max_cal_baseline_m and max_cal_baseline_lambda are None,
        arbitrarily long baselines are used. Default None.
    xtol : float
        Accuracy tolerance for optimizer. Default 1e-10.
    maxiter : int
        Maximum number of iterations for the optimizer. Default 100.
    verbose : bool
        Set to True to print optimization outputs. Default False.
    log_file_path : str or None
        Path to the log file. Default None.
    Returns
    -------
    abscal_params : array of float
        Shape (3, Nfreqs, N_feed_pols). abscal_params[0, :, :] are the overall amplitudes,
        abscal_params[1, :, :] are the x-phase gradients in units 1/m, and abscal_params[2, :, :]
        are the y-phase gradients in units 1/m.
    """

    if log_file_path is not None:
        stdout_orig = sys.stdout
        stderr_orig = sys.stderr
        sys.stdout = sys.stderr = log_file_new = open(log_file_path, "w")

    start_time = time.time()

    if verbose:
        print("Reading data...")
        sys.stdout.flush()
        data_read_start_time = time.time()

    print_data_read_time = False
    if isinstance(data, str):  # Read data
        print_data_read_time = True
        data_file_path = np.copy(data)
        data = pyuvdata.UVData()
        if data_file_path.endswith(".ms"):
            data.read_ms(data_file_path, data_column=data_use_column)
        else:
            data.read(data_file_path)
    if isinstance(model, str):  # Read model
        print_data_read_time = True
        model_file_path = np.copy(model)
        model = pyuvdata.UVData()
        if model_file_path.endswith(".ms"):
            model.read_ms(model_file_path, data_column=model_use_column)
        else:
            model.read(model_file_path)

    if verbose and print_data_read_time:
        print(
            f"Done. Data read time {(time.time() - data_read_start_time)/60.} minutes."
        )
        sys.stdout.flush()
    if verbose:
        print("Formatting data...")
        sys.stdout.flush()
        data_format_start_time = time.time()

    caldata_obj = caldata.CalData()
    caldata_obj.load_data(
        data,
        model,
        N_feed_pols=N_feed_pols,
        feed_polarization_array=feed_polarization_array,
        min_cal_baseline_m=min_cal_baseline_m,
        max_cal_baseline_m=max_cal_baseline_m,
        min_cal_baseline_lambda=min_cal_baseline_lambda,
        max_cal_baseline_lambda=max_cal_baseline_lambda,
    )

    if initial_abscal_params is not None:
        caldata_obj.abscal_params = initial_abscal_params

    if verbose:
        print(
            f"Done. Data formatting time {(time.time() - data_format_start_time)/60.} minutes."
        )
        print("Calculating delay weighting matrix...")
        sys.stdout.flush()

    get_dwcal_weights_from_delay_spectra(
        caldata_obj,
        delay_spectrum_variance,
        bl_length_bin_edges,
        delay_axis,
    )

    if verbose:
        print(
            f"Done. Time calculating delay weighting matrix {(time.time() - data_format_start_time)/60.} minutes."
        )
        print("Running calibration optimization...")
        sys.stdout.flush()
        optimization_start_time = time.time()

    initial_cost = calibration_optimization.cost_dw_abscal_wrapper(
        caldata_obj.abscal_params.flatten(), caldata_obj
    )
    print(f"Initial cost: {initial_cost}")

    # Perturb abscal parameters
    caldata_obj.abscal_params[0, :, :] += np.random.normal(
        0.0,
        0.1,
        size=(
            caldata_obj.Nfreqs,
            caldata_obj.N_feed_pols,
        ),
    )
    caldata_obj.abscal_params[1:, :, :] += np.random.normal(
        0.0,
        5e-4,
        size=(
            2,
            caldata_obj.Nfreqs,
            caldata_obj.N_feed_pols,
        ),
    )

    calibration_optimization.run_dw_abscal_optimization(
        caldata_obj,
        xtol,
        maxiter,
        verbose=verbose,
    )

    final_cost = calibration_optimization.cost_dw_abscal_wrapper(
        caldata_obj.abscal_params.flatten(), caldata_obj
    )
    print(f"Final cost: {final_cost}")
    final_jac = calibration_optimization.jacobian_dw_abscal_wrapper(
        caldata_obj.abscal_params.flatten(), caldata_obj
    )
    print(f"Final Jacobian: {final_jac}")

    if verbose:
        print(
            f"Done. Optimization time: {caldata_obj.Nfreqs} frequency channels in {(time.time() - optimization_start_time)/60.} minutes"
        )
        print(f"Total processing time {(time.time() - start_time)/60.} minutes.")
        sys.stdout.flush()

    if log_file_path is not None:
        sys.stdout = stdout_orig
        sys.stderr = stderr_orig
        log_file_new.close()

    return caldata_obj.abscal_params
