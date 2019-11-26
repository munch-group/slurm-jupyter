import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="slurm_jupyter", # Replace with your own username
    version="1.0",
    author="Kasper MUnch",
    author_email="kaspermunch@birc.au.dk",
    description="Utility running jupyter on a slurm cluster.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/kaspermunch/slurm_jupyter",
    packages=setuptools.find_packages(),
    scripts=['slurm-jupyter'],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)

# python3 setup.py sdist bdist_wheel
