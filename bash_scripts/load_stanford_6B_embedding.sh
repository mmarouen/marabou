#!/bin/bash
cd $PWD
set -e
export file_url=$1
export embedding_file_name=embeddings/stanford_embedding.zip
export embeddings_folder=embeddings

download_data () {
    echo "----> download ongoing"
    wget -q --show-progress -O $embedding_file_name $file_url
    unzip $embedding_file_name -d $embeddings_folder
    rm $embedding_file_name
}

if [ ! -d $embeddings_folder ] # if embeddings folder doesnt exist
then # load data
    mkdir -p $embeddings_folder
    download_data
elif [ ! "$(ls -A $embeddings_folder)" ] # embedings folder exists and is empty
then # load data
    download_data
else
    echo "----> embedding file(s) exists"
fi