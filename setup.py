#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import codecs
from setuptools import setup, find_packages


def read(fname):
    file_path = os.path.join(os.path.dirname(__file__), fname)
    return codecs.open(file_path, encoding='utf-8').read()


packages = find_packages(exclude=['tests', 'docs'])

setup(
    name='pytest-dask',
    version='0.1.1',
    author='Marius van Niekerk',
    author_email='marius.v.niekerk@gmail.com',
    maintainer='Marius van Niekerk',
    maintainer_email='marius.v.niekerk@gmail.com',
    license='MIT',
    url='https://github.com/mariusvniekerk/pytest-dasktest',
    description='A plugin to run tests with dask',
    long_description=read('README.rst'),
    packages=packages,
    install_requires=['pytest>=3.1.1'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Framework :: Pytest',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Testing',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
        'Operating System :: OS Independent',
        'License :: OSI Approved :: MIT License',
    ],
    zip_safe=False,
    entry_points={
        'pytest11': [
            'dask = pytest_dask.plugin',
        ],
    },
)
