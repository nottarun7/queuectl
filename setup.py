from setuptools import setup, find_packages
import os

# Read README with proper encoding
readme_path = os.path.join(os.path.dirname(__file__), "README.md")
with open(readme_path, "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="queuectl",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "click>=8.1.0",
        "tabulate>=0.9.0",
    ],
    entry_points={
        "console_scripts": [
            "queuectl=queuectl.cli:main",
        ],
    },
    python_requires=">=3.7",
    author="QueueCTL",
    description="A CLI-based background job queue system",
    long_description=long_description,
    long_description_content_type="text/markdown",
)
