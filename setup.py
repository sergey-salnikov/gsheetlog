from setuptools import setup, find_packages

setup(
    name='gsheetlog',
    version='0.1.0',
    description='Extract Google Sheet history',
    author='Sergey Salnikov',
    author_email='serg@salnikov.ru',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
    ],
    packages=find_packages(),
    install_requires=[
        'click',
        'google-api-python-client',
    ],
    entry_points={
        'console_scripts': [
            'gsheetlog=gsheetlog:main',
        ],
    },
)
