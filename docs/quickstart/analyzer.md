The InSARScript analyzer module provides workflow for InSAR time-series analysis.

- **Import analyzer**

    Import the Analyzer class to access all time-series analysis functionality
```python
from insarscript import Analyzer
```

- **View Available Analyzers**

    List all registered analyzer
```python
Analyzer.available()
```

## Available Analyzers

### Mintpy_SBAS_Base_Analyzer
InSARScript wrapped [Mintpy](https://github.com/insarlab/MintPy) as one of it's analysis backends. The `Mintpy_SBAS_Base_Analyzer` is implemented on top of a reusable base configuration class, which provides the full `smallbaselineApp` logic of Mintpy. Provides users with an experience similar to using MintPy directly, allowing full customization of processing parameters and steps.

::: insarscript.analyzer.mintpy_base.Mintpy_SBAS_Base_Analyzer
    options:
        members: false
        heading_level: 0

#### Usage

- **Create Analyzer with Parameters**

    Initialize a analyzer instance

    ```python
    analyzer = Analyzer.create('Mintpy_SBAS_Base_Analyzer', 
                                workdir="/your/work/dir",
                                load_processor= "hyp3", ....)
    
    ```
    OR
    ```python
    params = {"workdir":"/your/work/dir","load_processor": "hyp3" ....}
    analyzer = Analyzer.create('Mintpy_SBAS_Base_Analyzer', **params)
    ```
    OR

    ```python
    from insarscript.config import Mintpy_SBAS_Base_Config
    cfg = Mintpy_SBAS_Base_Config(workdir="/your/work/dir",
                                  load_processor= "hyp3",
                                  ....)
    analyzer = Analyzer.create('Mintpy_SBAS_Base_Analyzer', config=cfg)
    ```

    The base configure `Mintpy_SBAS_Base_Config` contains all parameters from Mintpy `smallbaselineApp.cfg`. For detailed descriptions and usage of each parameters, please refer to the [official Mintpy config documentation](https://github.com/insarlab/MintPy/blob/054c6010b5e40e98fe16e283121fdd1ae4bc1732/src/mintpy/defaults/smallbaselineApp.cfg). 

    ::: insarscript.config.Mintpy_SBAS_Base_Config
        options:
            members: false
            heading_level: 0

- **Run**  
    Run the Mintpy time-series analysis based on provid configuration

    ```python
    analyzer.run()
    ```

    ::: insarscript.analyzer.Mintpy_SBAS_Base_Analyzer.run
        options:
            members: true
            show_source: false
            heading_level: 5

- **Clean up**

    Remove intermediate processing files generated during the time-series process

    ```python
    analyzer.cleanup()
    ```

    ::: insarscript.analyzer.Mintpy_SBAS_Base_Analyzer.cleanup
        options:
            members: true
            show_source: false
            heading_level: 5

### Hyp3_SBAS
 The `Hyp3_SBAS` is specialized analyzer that extends Mintpy_SBAS_Base_Analyzer, preconfigured specifically for processing Time-series data for Hyp3 InSAR product.

::: insarscript.analyzer.Hyp3_SBAS
    options:
        members: false
        heading_level: 0

#### Usage

- **Create Analyzer with Parameters**

    Initialize a analyzer instance

    ```python
    analyzer = Analyzer.create('Hyp3_SBAS', 
                                workdir="/your/work/dir")
    
    ```
    OR
    ```python
    params = {"workdir":"/your/work/dir"}
    analyzer = Analyzer.create('Hyp3_SBAS', **params)
    ```
    OR

    ```python
    from insarscript.config import Mintpy_SBAS_Base_Config
    cfg = Mintpy_SBAS_Base_Config(workdir="/your/work/dir")
    analyzer = Analyzer.create('Hyp3_SBAS', config=cfg)
    ```

    - **Prepare data**
    Prepare interferogram data download from hyp3 server to mintpy

    ```python
    analyzer.prep_data()
    ```

    ::: insarscript.analyzer.Hyp3_SBAS.prep_data
            options:
                members: false
                heading_level: 5

    - **Run**  
    Run the Mintpy time-series analysis based on provid configuration

    ```python
    analyzer.run()
    ```

    ::: insarscript.analyzer.Hyp3_SBAS.run
        options:
            members: false
            heading_level: 5


    - **Clean up**

    Remove intermediate processing files generated during the time-series process

    ```python
    analyzer.cleanup()
    ```

    ::: insarscript.analyzer.Mintpy_SBAS_Base_Analyzer.cleanup
        options:
            members: true
            show_source: false
            heading_level: 5








    
    