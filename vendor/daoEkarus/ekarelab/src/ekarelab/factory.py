"""Factories for configuring an Ekarus offline data root."""

import logging
from pathlib import Path
from typing import Optional


class Factory:
    """Base factory for configuring an Ekarus telemetry data root."""

    def __init__(self, data_root_dir: Optional[Path | str] = None,
                 log_level: Optional[str | int] = None):
        self._data_root = Path.cwd() if data_root_dir is None else Path(data_root_dir)
        self._setup_logging(log_level)

    def data_root_dir(self) -> Path:
        """Return the configured telemetry data root."""
        return Path(self._data_root)

    def _setup_logging(self, log_level: Optional[str | int] = None):
        if log_level is None:
            level = logging.INFO
        elif isinstance(log_level, str):
            level = getattr(logging, log_level.upper(), logging.INFO)
        else:
            level = int(log_level)

        root = logging.getLogger()
        if not root.handlers:
            logging.basicConfig(
                level=level,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            )
        root.setLevel(level)
        self._logger = logging.getLogger(self.__class__.__name__)
        self._logger.info('Factory initialized: %s', self.__class__.__name__)
        self._logger.info('Data root: %s', self.data_root_dir())

    def file_walker(self):
        from ekarelab.ekarus_file_walker import EkarusFileWalker
        return EkarusFileWalker(self.data_root_dir())

    def analyzer(self, tag, *args, **kwargs):
        """Create an analyzer resolved against this factory's data root."""
        from ekarelab.ekarus_analyzer import EkarusAnalyzer
        return EkarusAnalyzer(tag, *args, file_walker=self.file_walker(), **kwargs)


class FactoryDefault(Factory):
    """Default factory using the current working directory as data root."""


class FactoryLaptopLorenzo(Factory):
    """Factory configured for Lorenzo's local Ekarus data root."""

    def __init__(self, **kwargs):
        root = Path('/Users/lbusoni/Library/CloudStorage/GoogleDrive-lorenzo.busoni@inaf.it/Drive condivisi/EKARUS/Ekarus public folder/Data/')
        super().__init__(data_root_dir=root, **kwargs)


class FactoryDaoRtc(Factory):
    """Factory for direct access on the DAO real-time computer."""

    def __init__(self, **kwargs):
        super().__init__(data_root_dir=Path('/home/daouser/DAODATA/telemetry'), **kwargs)


def get_factory(config='default', **kwargs):
    """Return a factory for ``default``, ``daortc``, or ``lorenzo``."""
    factories = {
        'default': FactoryDefault,
        'daortc': FactoryDaoRtc,
        'lorenzo': FactoryLaptopLorenzo,
    }
    if config not in factories:
        raise ValueError(
            f'Unknown factory config: {config}. Available: {list(factories)}')
    return factories[config](**kwargs)