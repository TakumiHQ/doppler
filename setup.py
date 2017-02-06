from distutils.core import setup

setup(
    name='Doppler',
    version='0.1dev',
    url='http://github.com/TakumiHQ/doppler',
    author='Jokull Solberg Audunsson',
    packages=['doppler'],
    install_requires=[
        'Flask>=0.10',
        'rpqueue>=0.26.0',
        'requests>=2.13.0',
        'redis>=2.10.5',
    ],
    license='MIT',
    long_description=open('README.md').read(),
)
