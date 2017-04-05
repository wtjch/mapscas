from setuptools import setup
from os import path

here = path.abspath(path.dirname(__file__))


def readme():
    with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
        return f.read()


setup(name='mapscas',
      version='0.1',
      description='MAPS CAS API Package',
      url='http://url',
      author='Wesley Jinks',
      author_email='c-wesley.jinks@charter.com',
      license='Proprietary',
      packages=['mapscas'],
      include_package_data=True,
      zip_safe=False)