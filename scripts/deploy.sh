#!/bin/bash
set -e

echo "Building Lambda package..."

rm -rf build lambda_function.zip
mkdir -p build
cp -r src build/
pip install -r requirements.txt -t build/ --quiet
cd build && zip -r ../lambda_function.zip . -q && cd ..
rm -rf build

echo "Package ready: $(du -h lambda_function.zip | cut -f1)"
echo ""
echo "Deploying infrastructure..."

cd terraform
terraform init -input=false
terraform apply -input=false -auto-approve

echo ""
echo "Done."
