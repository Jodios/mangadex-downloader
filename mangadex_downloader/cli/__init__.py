import sys

from .update import check_update
from .args_parser import get_args
from .utils import (
    close_network_object,
    setup_logging,
    setup_proxy,
    register_keyboardinterrupt_handler
)
from .auth import login_with_err_handler, logout_with_err_handler
from .download import download


def _main(argv):
    # Signal handler
    register_keyboardinterrupt_handler()

    # Get command-line arguments
    args = get_args(argv)

    # Setup logging
    log = setup_logging('mangadex_downloader', args.verbose)

    # Add checking before log in
    if args.start_chapter is not None and args.end_chapter is not None:
        if args.start_chapter > args.end_chapter:
            log.error("--start-chapter cannot be more than --end-chapter")
            return 1

    # Setup proxy
    setup_proxy(args.proxy, args.proxy_env)

    # Login
    login_with_err_handler(args)

    # Download the manga
    download(args)

    # Logout when it's finished
    logout_with_err_handler(args)

    # Check update
    check_update()

    # Cleaning up
    close_network_object()

    # We're done here
    return 0

def main(argv=None):
    if argv is None:
        exit_code = _main(sys.argv[1:])
    else:
        exit_code = _main(argv)
    sys.exit(exit_code)