import logging
from logging.handlers import RotatingFileHandler
from PySide6.QtCore import QStandardPaths, QDir


def setup_logger():
    logger = logging.getLogger("VMS")
    logger.setLevel(logging.DEBUG)

    # Create logs directory if it doesn't exist
    logs_dir = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
    QDir().mkpath(logs_dir)
    log_file = QDir(logs_dir).filePath("vms.log")

    # Create file handler
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1024 * 1024,  # 1MB
        backupCount=5
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        "%(levelname)s - %(message)s"
    ))

    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


logger = setup_logger()