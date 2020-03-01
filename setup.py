from setuptools import find_namespace_packages, setup

setup(
    name='arugifa-cms',
    version='0.1.0',
    description='The Python CMS based on Git',
    url='https://github.com/arugifa/cms',
    author='Alexandre Figura',
    license='GNU General Public License v3',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
    ],
    packages=find_namespace_packages(include=['arugifa.*']),
    install_requires=[
        'aiofiles>=0.4',
        'arugifa-cli>=0.1.0',
        'gitdb>=4.0',
        'gitpython>=3.1',
        'sqlalchemy>=1.3',
        'tqdm>=4.43',
    ],
)
