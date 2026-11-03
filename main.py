import sys
import time
import argparse
import config
from config import logger

from process import check_and_process


def main() -> None:
    # Setup CLI arguments
    parser = argparse.ArgumentParser(
        description="Audio-to-Article WordPress Draft Generator. Monitors Google Drive, transcribes with Gemini, posts to WordPress."
    )
    parser.add_argument(
        '--run-once',
        action='store_true',
        help="Run the file scanner once and exit immediately rather than polling."
    )
    args = parser.parse_args()
    
    logger.info("Initializing Audio-to-Article Generator...")

    if args.run_once:
        logger.info("Running in RUN-ONCE mode.")
        check_and_process()
        logger.info("Finished running. Exiting.")
    else:
        logger.info(f"Running in DAEMON mode (polling every {config.POLL_INTERVAL} seconds).")
        try:
            while True:
                check_and_process()
                logger.info(f"Sleeping for {config.POLL_INTERVAL} seconds before next scan...")
                time.sleep(config.POLL_INTERVAL)
        except KeyboardInterrupt:
            logger.info("Daemon execution interrupted by user. Exiting.")
            sys.exit(0)

if __name__ == '__main__':
    main()

