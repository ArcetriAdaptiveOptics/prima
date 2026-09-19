"""File paths for Ekarus telemetry products."""

from pathlib import Path
from typing import Optional, Union

from arte.dataelab.base_file_walker import AbstractFileNameWalker


class EkarusFileWalker(AbstractFileNameWalker):
    def __init__(self, root_dir: Optional[Union[str, Path]] = None):
        if root_dir is None:
            raise ValueError('EkarusFileWalker requires root_dir')
        self._root_dir = Path(root_dir)

    def walker_root_dir(self) -> Path:
        return self._root_dir

    def snapshot_dir(self, tag: Union[str, Path]) -> Path:
        """Return the directory containing products for a telemetry tag."""
        tag_string = str(tag)
        if '/' in tag_string:
            day, time = tag_string.split('/', 1)
        elif '_' in tag_string:
            day, time = tag_string.split('_', 1)
        else:
            raise ValueError(f"Cannot parse tag '{tag_string}'")
        time = time.replace('_', '')
        if len(day) < 8 or len(time) < 6:
            raise ValueError(f"Cannot parse tag '{tag_string}'")
        snapshot_tag = f'{day[:8]}_{time[:6]}'
        date_dir = f'{day[:4]}_{day[4:6]}_{day[6:8]}'
        return self._root_dir / date_dir / snapshot_tag

    def _product_file(self, tag: Union[str, Path], product: str) -> Path:
        supplied_path = Path(str(tag))
        if supplied_path.exists() and supplied_path.is_file():
            return supplied_path
        tag_string = str(tag)
        if '/' in tag_string:
            day, time = tag_string.split('/', 1)
        elif '_' in tag_string:
            day, time = tag_string.split('_', 1)
        else:
            raise ValueError(f"Cannot parse tag '{tag_string}'")
        time = time.replace('_', '')
        if len(day) < 8 or len(time) < 6:
            raise ValueError(f"Cannot parse tag '{tag_string}'")
        snapshot_tag = f'{day[:8]}_{time[:6]}'
        date_dir = f'{day[:4]}_{day[4:6]}_{day[6:8]}'
        return self._root_dir / date_dir / snapshot_tag / f'{snapshot_tag}_{product}.npy'

    def telemetry_file(self, tag: Optional[Union[str, Path]] = None) -> Path:
        if tag is None:
            raise ValueError('tag is required')
        return self._product_file(tag, 'loop_data')

    def wfs_intensity_file(self, tag: Optional[Union[str, Path]] = None) -> Path:
        if tag is None:
            raise ValueError('tag is required')
        return self._product_file(tag, 'wfs_intensity')

    def cblue_file(self, tag: Optional[Union[str, Path]] = None) -> Path:
        if tag is None:
            raise ValueError('tag is required')
        return self._product_file(tag, 'cblue_data')

    def orca_file(self, tag: Optional[Union[str, Path]] = None) -> Path:
        if tag is None:
            raise ValueError('tag is required')
        return self._product_file(tag, 'orca_data')

    def dm468_influence_functions_file(self) -> Path:
        """Return the calibrated DM468 influence-functions cube."""
        local_path = self._root_dir / 'inputs' / 'dm468' / 'IF_zonal_cube.npy'
        if local_path.exists():
            return local_path
        return self._root_dir.parent / 'inputs' / 'dm468' / 'IF_zonal_cube.npy'