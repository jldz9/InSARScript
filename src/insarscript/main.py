import argparse
from pathlib import Path

from insarscript._version import __version__

def create_parser()-> argparse.ArgumentParser:
    parser = argparse.ArgumentParser('insarscript', 
                                     description='InSAR processing pipeline CLI Interface', 
                                     epilog="Use 'insarscript <command> --help' for more info on a specific command.")
    parser.add_argument("-v", "--version", action='version', version=f'InSAR Script {__version__}')
    parser.add_argument("-c", '--config', metavar='PATH', help='Use config file for full auto process')

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        help="Availiable sub command"
    )
    ## -----------------Sub-parser: search ----------------- ##
    parser_search = subparsers.add_parser(
        "search", 
        help="Download satellite data"
    )

    parser_search.add_argument(
        "-P", "--platform",
        metavar="STR",
        default="Sentinel1",
        help="Choose the satellite type"
    )

    parser_search.add_argument(
        "-b", "--bbox",
        nargs=4,
        metavar=('WEST_LON','SOUTH_LAT', 'EAST_LON', 'NORTH_LAT'),
        type=float,
        required=True,
        help="The bounding box of AOI, west_lon, south_lat, east_lon, north_lat"
    )

    parser_search.add_argument(
        "-sd", "--start-date",
        metavar="DATE",
        type=str,
        help="The start date for data search (YYYY-MM-DD)"
    )

    parser_search.add_argument(
        "-ed", "--end-date",
        metavar="DATE",
        type=str,
        help="The end date for data search (YYYY-MM-DD)"
    )   

    parser_search.add_argument(
        "-fd", "--flight-direction",
        metavar="STR",
        choices=["ASCENDING", "DESCENDING"],
        default="ASCENDING",
        help="The flight direction of satellite"
    )

    parser_search.add_argument(
        "-p", "--path",
        metavar="INT",
        type=int,
        nargs='+',
        help="The path number or a list of satellite orbit"
    )

    parser_search.add_argument(
        "-f", "--frame",
        metavar="INT",
        type=int,
        nargs='+',
        help="The frame number or a list of satellite orbit"
    )

    parser_search.add_argument(
        "-o", "--output-dir",
        metavar="PATH",
        type=str,
        default="./data",
        help="The output directory to save downloaded data"
    )

    parser_search.add_argument(
        "--max-results",
        metavar="INT",
        type=int,
        default=1000,
        help="Maximum number of results to return"
    )

    parser_search.add_argument(
        "-d", "--download",
        action="store_true",
        help="Flag to download the data after search"
    )
    
    parser_search.add_argument(
        "-O", "--download-orbit"
        ,action="store_true",
        help="Flag to download the precise orbit file"
    )

    ## -----------------Sub-parser: process ----------------- ##
    return parser

def search(args):      
    if args.platform == "Sentinel1"  or args.platform in ["Sentinel-1A", "Sentinel-1B", "Sentinel-1C"] or all([plt in ["Sentinel-1A", "Sentinel-1B", "Sentinel-1C"] for plt in list(args.platform) if isinstance(args.platform, list)]):
        from insarscript import S1_SLC
        s1 = S1_SLC(
            platform=args.platform,
            AscendingflightDirection=args.flight_direction=="ASCENDING",
            path = args.path,
            frame = args.frame,
            bbox=args.bbox,
            start = args.start_date,
            end = args.end_date,
            workdir=Path(args.output_dir).expanduser().resolve() if args.output_dir else None,
            download_orbit=args.download_orbit
        )
        s1.footprint(save_path=args.output_dir)
        if args.download:
            s1.download()

def process(args):

    pass

def main():
    parser = create_parser()
    args = parser.parse_args()
    if args.command == "search":
        search(args)


if __name__ == "__main__":
    main()