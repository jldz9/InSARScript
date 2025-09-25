'''
# ---------------------ISCE2 Configuration---------------------
# If choose local processing, ISCE2 is required for Sentinel-1 SLC processing
# If ISCE is proper installed, ISCE_HOME should exist in the environment
# if ISCE_HOME exist, appending ISCE_HOME/applications and ISCE_HOME/bin to sys.path as recommended by MintPy 
# https://github.com/yunjunz/conda-envs/blob/main/README.md#2-install-isce-2-and-mintpy
try: 
    import isce
except ImportError:
    print(f"{Fore.RED}ISCE2 is not installed.")
    sys.exit(1)

if 'ISCE_HOME' not in os.environ:
    print(f"{Fore.RED}Can not find environment variable ISCE_HOME. isce2 is either not installed or installed in customized path.")
    sys.exit(1)
else: 
    isce_home = os.environ['ISCE_HOME']
    application_path = isce_home + '/applications'
    bin_path = isce_home + '/bin'
    os.environ['PATH'] = f"{os.environ.get('PATH','')}{os.pathsep}{application_path}{os.pathsep}{bin_path}"
'''