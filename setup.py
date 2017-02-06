from pip.req import parse_requirements
from distutils.core import setup

install_reqs = parse_requirements('requirements.txt', session='hack')

setup(
    name='Doppler',
    version='0.1dev',
    packages=[str(ir.req) for ir in install_reqs],
    license='MIT',
    long_description=open('README.md').read(),
)
