#!/usr/bin/env python

"""RAD-SMART backend plugin for CARE."""

from setuptools import find_packages, setup

with open("README.md", encoding="utf-8") as readme_file:
    readme = readme_file.read()

requirements = [
    "celery",
    "django",
    "djangorestframework",
    "django-environ",
    "django-filter",
    # The scheduling engine (poc/ in the RAD-SMART repository). In development it
    # is installed in editable mode from the mounted checkout; a deployment
    # installs it from the repository's poc/ subdirectory.
    "radsmart",
]

setup(
    author="RAD-SMART team (Health-a-thon 2026)",
    python_requires=">=3.13",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Framework :: Django",
        "Intended Audience :: Healthcare Industry",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.13",
    ],
    description="Radiotherapy scheduling for CARE: standing slots, live machine status, breakdown triage",
    install_requires=requirements,
    license="MIT license",
    long_description=readme,
    long_description_content_type="text/markdown",
    include_package_data=True,
    keywords="care_radsmart radiotherapy scheduling",
    name="care_radsmart",
    packages=find_packages(include=["care_radsmart", "care_radsmart.*"]),
    url="https://github.com/psraghothamrao8/RAD-SMART",
    version="0.1.0",
    zip_safe=False,
)
