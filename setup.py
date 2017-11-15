from setuptools import setup, find_packages

setup(
    name='gsheetlog',
    version='0.1.1',
    description='Extract Google Sheet history',
    author='Sergey Salnikov',
    author_email='serg@salnikov.ru',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
    ],
    py_modules=['gsheetlog'],
    install_requires=[
        'click',
        'google-api-python-client',
        'ratelimit',
    ],
    entry_points={
        'console_scripts': [
            'gsheetlog=gsheetlog:main',
        ],
    },
)
