from setuptools import setup
from setuptools import find_packages
import setuptools
from os import path

here = path.abspath(path.dirname(__file__))


def readme():
    with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
        return f.read()


setup(
    name="mapscas",
    version="0.1.2",

    include_package_data=True,
    packages=find_packages('src'),
    package_dir={'':'src'},
    #package_data={'': ['*.dfa', '*.llr', '*.pyd']},
    zip_safe=False,

    data_files=[('../../Scripts', ['src/parsers/MapsClientParser.dfa', 'src/parsers/MapsClientParser.llr'])],

    # Metadata for PyPI
    author="Wesley Jinks",
    author_email="c-wesley.jinks@charter.com",
    description='MAPS CAS API Package',
    url="https://github.com/wtjch/mapscas",
    license="Proprietary"
    )