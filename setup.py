"""Package setup for the ENTSO-E data collector."""

from setuptools import find_packages, setup

with open("requirements.txt") as f:
    install_requires = [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
    name="entso-e-collector",
    version="0.1.0",
    description="ENTSO-E PEMMDB / PECD data collection, processing, and visualisation package",
    author="",
    python_requires=">=3.10",
    packages=find_packages(exclude=["tests*"]),
    install_requires=install_requires,
    entry_points={
        "console_scripts": [
            "collector-run=collector.main:run",
        ],
    },
)
