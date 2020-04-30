# current dir (assume that is the package name)
name=${PWD##*/}

# build and upload to pypi
python setup.py bdist_wheel
python setup.py sdist
python -m twine upload dist/*



