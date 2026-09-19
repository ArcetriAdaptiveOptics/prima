from setuptools import setup, find_packages

setup(
    name='prima',
    version='0.1.0',
    description='Prima — Arcetri PWFS metrology on the plico stack',
    author='INAF Arcetri Adaptive Optics',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'numpy',
        'PyQt5',
        'pyqtgraph',
        'plico',
        'plico_dm',
        'pysilico',
    ],
    entry_points={
        'console_scripts': [
            'prima-gui=prima.gui.app:main',
        ],
    },
    python_requires='>=3.8',
)
