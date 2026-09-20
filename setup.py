from setuptools import setup, find_packages

setup(
    name='prima',
    version='0.2.0',
    description='Prima — Arcetri PWFS metrology + DaoPrima AO on the plico stack',
    author='INAF Arcetri Adaptive Optics',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'numpy',
        'scipy',
        'astropy',
        'scikit-image',
        'PyQt5',
        'pyqtgraph',
        'plico',
        'plico_dm',
        'pysilico',
    ],
    entry_points={
        'console_scripts': [
            'prima-gui=prima.gui.app:main',
            'prima-dm-gui=prima.gui.dm_panel:main',
            'daoprima-gui=daoprima.gui_main:main',
        ],
    },
    python_requires='>=3.8',
)
