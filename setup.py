from setuptools import setup, find_packages

setup(
    name='prima',
    version='0.2.0',
    description='Prima Drop 1 — PWFS absolute metrology (Aravis + direct PI GCS)',
    author='INAF Arcetri Adaptive Optics',
    packages=find_packages(include=['prima', 'prima.*']),
    include_package_data=True,
    install_requires=[
        'numpy',
        'scipy',
        'astropy',
        'scikit-image',
        'PyQt5',
        'pyqtgraph',
    ],
    entry_points={
        'console_scripts': [
            'prima-gui=prima.gui.app:main',
        ],
    },
    python_requires='>=3.8',
)
