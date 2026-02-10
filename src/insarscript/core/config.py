from dataclasses import dataclass, field, asdict
from typing import List, Union, Optional, Any
from pathlib import Path

@dataclass
class ASF_Base_Config:
    '''
    Dataclass containing all configuration options for asf_search.
    
    This class provides a unified interface for configuring ASF (Alaska Satellite Facility) 
    search parameters.
    '''
    type: str = "ASF_Base_Config"
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
    bbox: List[float] | None = None #[west(min)_lon, south(min)_lat, east(max)_lon, north(max)_lat]

    def __post_init__(self):
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir).expanduser().resolve()

@dataclass
class Hyp3_InSAR_Base_Config:
    '''
    Dataclass containing all configuration options for hyp3_sdk insar_gamma jobs.
    '''
    type: str = "Hyp3_InSAR_Base_Config"
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
    output_dir: Path | str = field(default_factory=lambda: Path.cwd())
    saved_job_path : Path | str | None = None
    earthdata_credentials_pool: dict[str, str] | None=None

    def __post_init__(self):
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir).expanduser().resolve()





