#!/bin/bash

# ------------------------------------------------------------
# brew installs 
# ------------------------------------------------------------
brew install python-tk@3.13

echo -e "\033[32mCreating virtual environment...\033[0m"
# create a virtual environment
python -m venv . 
# activate the virtual environment
source bin/activate

pip3 install --upgrade pip setuptools wheel
# install the dependencies
pip3 install -r requirements.txt
# run the script
python3 src/main.py