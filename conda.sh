# current dir (assume that is the package name)
name=${PWD##*/}

# conda skeleton with meta info
conda skeleton pypi $name

# for for each version of python
for pythonversion in 3.6 3.7 3.8; do
    conda-build --python $pythonversion $name
done

# upload osx versions and convert to other architectures (assuming python only)
for path in `find $HOME/anaconda3/conda-bld/osx-64/ -name "$name-[0-9]*.bz2"`; do
    anaconda upload $path
    conda convert --platform all $HOME/anaconda3/conda-bld/osx-64/$name-[0-9]*.bz2 -o outputdir/
done

# upload versios for other architectures
for path in `find outputdir -name '*.bz2'`; do 
    anaconda upload $path
done


