import argparse

from insarscript._version import __version__

def create_parser():
    parser = argparse.ArgumentParser('insarscript', 
                                     description='InSAR processing pipeline CLI Interface', 
                                     epilog="Use 'mytool.py <command> --help' for more info on a specific command.")
    parser.add_argument("-v", "--version", action='version', version=f'InSAR Script {__version__}')
    parser.add_argument("-c", '--config', metavar='PATH', help='Use config file for full auto process')

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        help="Availiable sub command"
    )

    parser_download = subparsers.add_parser(
        "download", 
        help="Download satellite data"
    )

    parser_download.add_argument(
        "-s", "--satellite",
        metavar="STR",
        default="Sentinel1",
        help="Choose the satellite type"
    )

    parser_download.add_argument(
        "-b", "--bbox",
        nargs=4,
        metavar=('WEST_LON','SOUTH_LAT', 'EAST_LON', 'NORTH_LAT'),
        type=float,
        required=True,
        help="The bounding box of AOI, west_lon, south_lat, east_lon, north_lat"
    )

