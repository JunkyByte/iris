import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="iris",
    version="0.0.1",
    author="Adriano Donninelli",
    author_email="adriano.donninelli@hotmail.it",
    description="A command line tool to sync folders and files between local and remote paths",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Junkybyte/iris",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3',
    entry_points={
        'console_scripts': ['iris = iris.iris:main', 'iris-init = iris.iris:init_config']
    }
)
