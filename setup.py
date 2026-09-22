from setuptools import setup, find_packages

setup(
    name='prima',
    version='0.3.0',
    description='Prima — Drop1 PWFS metrology + Drop2 BMC Multi-DM (DAO)',
    author='INAF Arcetri Adaptive Optics',
    packages=find_packages(include=['prima', 'prima.*', 'daoprima', 'daoprima.*']),
    include_package_data=True,
    package_data={
        'daoprima': ['hw/maps/*.map'],
    },
    install_requires=[
        'numpy',
        'scipy',
        'astropy',
        'scikit-image',
        'PyQt5',
        'pyqtgraph',
        'pyusb',
    ],
    entry_points={
        'console_scripts': [
            'prima-gui=prima.gui.app:main',
            'prima-control=prima.gui.control_launcher:main',
            'prima-dm-gui=prima.gui.dm_panel:main',
            'daodm-bmc-ctrl=daoprima.apps.daodm_bmc_ctrl:main',
        ],
    },
    python_requires='>=3.8',
)
