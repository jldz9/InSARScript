from dataclasses import dataclass, field, asdict
from typing import List, Union, Optional, Any
from pathlib import Path
from asf_search import constants
from insarscript import _env

@dataclass
class ASF_Base_Config:
    '''
    Dataclass containing all configuration options for asf_search.
    
    This class provides a unified interface for configuring ASF (Alaska Satellite Facility) 
    search parameters.
    '''
    name: str = "ASF_Base_Config"
    dataset: str | list[str] | None = None
    platform: str | list[str] | None = None
    instrument: str | None = None
    absoluteBurstID: int | list[int] | None = None
    absoluteOrbit: int | list[int] | None = None
    asfFrame: int | list[int] | None = None
    beamMode: str | None = None
    beamSwath: str | list[str] | None = None
    campaign: str | None = None
    maxDoppler: float | None = None
    minDoppler: float | None = None
    maxFaradayRotation: float | None = None
    minFaradayRotation: float | None = None
    flightDirection: str | None = None
    flightLine: str | None = None
    frame: int | list[int] | None = None
    frameCoverage: str | None = None
    fullBurstID: str | list[str] | None = None
    groupID: str | None = None
    jointObservation: bool | None = None
    lookDirection: str | None = None
    offNadirAngle: float | list[float] | None = None
    operaBurstID: str | list[str] | None = None
    polarization: str | list[str] | None = None
    mainBandPolarization: str | list[str] | None = None
    sideBandPolarization: str | list[str] | None = None
    processingLevel: str | None = None
    productionConfiguration: str | list[str] | None = None
    rangeBandwidth: str | list[str] | None = None
    relativeBurstID: str | list[str] | None = None
    relativeOrbit: int | list[int] | None = None
    intersectsWith: str | None = None  
    processingDate: str | None = None
    start: str | None = None
    end: str | None = None
    season: list[int] | None = None
    stack_from_id: str | None = None
    maxResults: int | None = None
    output_dir: Path | str = field(default_factory=lambda: Path.cwd()) 

    def __post_init__(self):
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir).expanduser().resolve()

@dataclass
class S1_SLC_Config(ASF_Base_Config):
    name:str = "S1_SLC_Config"
    dataset: str | list[str] | None =  constants.DATASET.SENTINEL1
    instrument: str | None = constants.INSTRUMENT.C_SAR
    beamMode:str | None = constants.BEAMMODE.IW
    polarization: str|list[str] | None = field(default_factory=lambda: [constants.POLARIZATION.VV, constants.POLARIZATION.VV_VH])
    processingLevel: str | None = constants.PRODUCT_TYPE.SLC

@dataclass
class Hyp3_Base_Config:
    """
    Base configuration for any HyP3 job interaction.
    """
    name: str = "Hyp3_Base_Config"
    output_dir: Path | str = field(default_factory=lambda: Path.cwd())
    saved_job_path: Path | str | None = None
    earthdata_credentials_pool: dict[str, str] | None = None
    skip_existing: bool = True
    submission_chunk_size: int = 200 
    max_workers: int = 4 # Multithreading <8 to avoid overwhelming the API and to be mindful of local resources, also avoid bans from too many requests. 

    def __post_init__(self):
        # Auto-convert string paths to Path objects
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir).expanduser().resolve()
        if self.saved_job_path and isinstance(self.saved_job_path, str):
            self.saved_job_path = Path(self.saved_job_path).expanduser().resolve()


@dataclass
class Hyp3_InSAR_Config(Hyp3_Base_Config):
    '''
    Dataclass containing all configuration options for hyp3_sdk insar_gamma jobs.
    '''
    name: str = "Hyp3_InSAR_Config"
    pairs: list[tuple[str, str]] | None = None
    name_prefix: str | None = 'ifg'
    include_look_vectors:bool=True
    include_los_displacement:bool=False
    include_inc_map:bool=True
    looks:str='20x4'
    include_dem :bool=True
    include_wrapped_phase :bool=False
    apply_water_mask :bool=True
    include_displacement_maps:bool=True
    phase_filter_parameter :float=0.6

@dataclass
class Mintpy_SBAS_Base_Config:
    '''
    Dataclass containing all configuration options for Mintpy SBAS jobs.
    '''
    name: str = "Mintpy_SBAS_Base_Config"
    workdir: Path | str = field(default_factory=lambda: Path.cwd())
    debug: bool = False 

    ## computing resource configuration
    compute_maxMemory : float = _env['memory']
    compute_cluster : str = 'local' # Mintpy's slurm parallel processing is kind of buggy, so we will handle parallel processing with dask instead. Switch to none to turn off parallel processing to save memory.
    compute_numWorker : int = _env['cpu']
    compute_config: str = 'none'

    ## Load data
    load_processor: str = 'auto'
    load_autoPath: str = 'auto' 
    load_updateMode: str = 'auto'
    load_compression: str = 'auto'
    ##---------for ISCE only:
    load_metaFile: str = 'auto'
    load_baselineDir: str = 'auto'
    ##---------interferogram stack:
    load_unwFile: str = 'auto'
    load_corFile: str = 'auto'
    load_connCompFile: str = 'auto'
    load_intFile: str = 'auto'
    load_magFile: str = 'auto'
    ##---------ionosphere stack (optional):
    load_ionUnwFile: str = 'auto'
    load_ionCorFile: str = 'auto'
    load_ionConnCompFile: str = 'auto'
    ##---------offset stack (optional):
    load_azOffFile: str = 'auto'
    load_rgOffFile: str = 'auto'
    load_azOffStdFile: str = 'auto'
    load_rgOffStdFile: str = 'auto'
    load_offSnrFile: str = 'auto'
    ##---------geometry:
    load_demFile: str = 'auto'
    load_lookupYFile: str = 'auto'
    load_lookupXFile: str = 'auto'
    load_incAngleFile: str = 'auto'
    load_azAngleFile: str = 'auto'
    load_shadowMaskFile: str = 'auto'
    load_waterMaskFile: str = 'auto'
    load_bperpFile: str = 'auto'
    ##---------subset (optional):
    subset_yx: str = 'auto'
    subset_lalo: str = 'auto'
    ##---------multilook (optional):
    multilook_method: str = 'auto'
    multilook_ystep: str = 'auto'
    multilook_xstep: str = 'auto'

    # 2. Modify Network
    network_tempBaseMax: str = 'auto'
    network_perpBaseMax: str = 'auto'
    network_connNumMax: str = 'auto'
    network_startDate: str = 'auto'
    network_endDate: str = 'auto'
    network_excludeDate: str = 'auto'
    network_excludeDate12: str = 'auto'
    network_excludeIfgIndex: str = 'auto'
    network_referenceFile: str = 'auto'
    ## 2) Data-driven network modification
    network_coherenceBased: str = 'auto'
    network_minCoherence: str = 'auto'
    ## b - Effective Coherence Ratio network modification = (threshold + MST) by default
    network_areaRatioBased: str = 'auto'
    network_minAreaRatio: str = 'auto'
    ## Additional common parameters for the 2) data-driven network modification
    network_keepMinSpanTree: str = 'auto'
    network_maskFile: str = 'auto'
    network_aoiYX: str = 'auto'
    network_aoiLALO: str = 'auto'

    # 3. Reference Point
    reference_yx: str = 'auto'
    reference_lalo: str = 'auto'
    reference_maskFile: str = 'auto'
    reference_coherenceFile: str = 'auto'
    reference_minCoherence: str = 'auto'

    # 4. Correct Unwrap Error
    unwrapError_method: str = 'auto'
    unwrapError_waterMaskFile: str = 'auto'
    unwrapError_connCompMinArea: str = 'auto'
    ## phase_closure options:
    unwrapError_numSample: str = 'auto'
    ## bridging options:
    unwrapError_ramp: str = 'auto'
    unwrapError_bridgePtsRadius: str = 'auto'

    # 5. Invert Network
    networkInversion_weightFunc: str = 'auto'
    networkInversion_waterMaskFile: str = 'auto'
    networkInversion_minNormVelocity: str = 'auto'
    ## mask options for unwrapPhase of each interferogram before inversion (recommend if weightFunct=no):
    networkInversion_maskDataset: str = 'auto'
    networkInversion_maskThreshold: str = 'auto'
    networkInversion_minRedundancy: str = 'auto'
    ## Temporal coherence is calculated and used to generate the mask as the reliability measure
    networkInversion_minTempCoh: str = 'auto'
    networkInversion_minNumPixel: str = 'auto'
    networkInversion_shadowMask: str = 'auto'

    # 6. Correct SET (Solid Earth Tides)
    solidEarthTides: str = 'auto'

    # 7. Correct Ionosphere
    ionosphericDelay_method: str = 'auto'
    ionosphericDelay_excludeDate: str = 'auto'
    ionosphericDelay_excludeDate12: str = 'auto'

    # 8. Correct Troposphere
    troposphericDelay_method: str = 'auto'
    ## Notes for pyaps:
    troposphericDelay_weatherModel: str = 'auto'
    troposphericDelay_weatherDir: str = 'auto'
    
    ## Notes for height_correlation:
    troposphericDelay_polyOrder: str = 'auto'
    troposphericDelay_looks: str = 'auto'
    troposphericDelay_minCorrelation: str = 'auto'
    ## Notes for gacos:
    troposphericDelay_gacosDir: str = 'auto'

    # 9. Deramp
    deramp: str = 'auto'
    deramp_maskFile: str = 'auto'

    # 10. Correct Topography
    topographicResidual: str = 'auto'
    topographicResidual_polyOrder: str = 'auto'
    topographicResidual_phaseVelocity: str = 'auto'
    topographicResidual_stepDate: str = 'auto'
    topographicResidual_excludeDate: str = 'auto'
    topographicResidual_pixelwiseGeometry: str = 'auto'

    # 11.1 Residual RMS
    residualRMS_maskFile: str = 'auto'
    residualRMS_deramp: str = 'auto'
    residualRMS_cutoff: str = 'auto'

    # 11.2 Reference Date
    reference_date: str = 'auto'

    # 12. Velocity
    timeFunc_startDate: str = 'auto'
    timeFunc_endDate: str = 'auto'
    timeFunc_excludeDate: str = 'auto'
    ## Fit a suite of time functions
    timeFunc_polynomial: str = 'auto'
    timeFunc_periodic: str = 'auto'
    timeFunc_stepDate: str = 'auto'
    timeFunc_exp: str = 'auto'
    timeFunc_log: str = 'auto'
    ## Uncertainty quantification methods:
    timeFunc_uncertaintyQuantification: str = 'auto'
    timeFunc_timeSeriesCovFile: str = 'auto'
    timeFunc_bootstrapCount: str = 'auto'

    # 13.1 Geocode
    geocode: str = 'auto'
    geocode_SNWE: str = 'auto'
    geocode_laloStep: str = 'auto'
    geocode_interpMethod: str = 'auto'
    geocode_fillValue: str = 'auto'

    # 13.2 Google Earth
    save_kmz: str = 'auto'

    # 13.3 HDFEOS5
    save_hdfEos5: str = 'auto'
    save_hdfEos5_update: str = 'auto'
    save_hdfEos5_subset: str = 'auto'

    # 13.4 Plot
    plot: str = 'auto'
    plot_dpi: str = 'auto'
    plot_maxMemory: str = 'auto'

    def __post_init__(self):
        if isinstance(self.workdir, str):
            self.workdir = Path(self.workdir).expanduser().resolve()
    
    def write_mintpy_config(self, outpath: Union[Path, str]):
        """
        Writes the dataclass to a mintpy .cfg file, excluding operational 
        parameters that MintPy doesn't recognize.
        """
        outpath = Path(outpath).expanduser().resolve()
        exclude_fields = ['name', 'workdir', 'debug']

        with open(outpath, 'w') as f:
            f.write("## MintPy Config File Generated via InSARScript\n")

            for key, value in asdict(self).items():
                if key in exclude_fields:
                    continue

                parts = key.split('_')
                if len(parts) > 1:
                    mintpy_key = f"mintpy.{parts[0]}.{'.'.join(parts[1:])}"
                else:
                    mintpy_key = f"mintpy.{parts[0]}"

                f.write(f"{mintpy_key:<40} = {value}\n")

        return Path(outpath).resolve()

      

