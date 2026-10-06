#!/usr/bin/env python3
"""Setup script for VritraAI (assistant / coding-agent)."""

from pathlib import Path

from setuptools import find_packages, setup

this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding="utf-8")

requirements = []
with open("requirements.txt", "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#"):
            requirements.append(line)

setup(
    name="vritraai",
    version="1.0.2",
    author="Alex Butler",
    author_email="contact@vritrasec.com",
    description=(
        "AI coding assistant for the terminal - agent loop, "
        "multi-file edits, multi-provider models"
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/MrHacker-X/VritraAI",
    project_urls={
        "Bug Reports": "https://github.com/MrHacker-X/VritraAI/issues",
        "Source": "https://github.com/MrHacker-X/VritraAI",
        "Documentation": "https://vritraai.vritrasec.com/",
        "Website": "https://vritrasec.com",
    },
    py_modules=["vritraai"],
    packages=find_packages(exclude=["tests", "tests.*", "VritraAI-og", "website"]),
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "vritraai=vritraai:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development",
        "Topic :: Utilities",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS",
        "Environment :: Console",
    ],
    license="MIT",
    python_requires=">=3.9",
    keywords="ai coding-agent cli terminal assistant llm",
    include_package_data=True,
    zip_safe=False,
)
