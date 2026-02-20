#!/bin/bash
set -e

echo "Building Lambda package..."

rm -rf build lambda_function.zip
mkdir -p build
cp -r src build/
pip install -r requirements.txt -t build/ \
  --platform manylinux2014_x86_64 \
  --python-version 3.11 \
  --implementation cp \
  --only-binary=:all: \
  --quiet
cd build && zip -r ../lambda_function.zip . -q && cd ..
rm -rf build

echo "Package ready: $(du -h lambda_function.zip | cut -f1)"
echo ""
echo "Deploying infrastructure..."

cd terraform
terraform init -input=false
terraform apply -input=false -auto-approve
cd ..

# Force-push code directly — Terraform's source_code_hash can miss changes when
# the zip is rebuilt between applies. This guarantees both Lambdas always run the
# current code regardless of Terraform state.
echo ""
echo "Pushing code to Lambdas..."
PROJECT=$(cd terraform && terraform output -raw lambda_function_name | sed 's/-email-analyzer//')
aws lambda update-function-code \
  --function-name "${PROJECT}-email-analyzer" \
  --zip-file fileb://lambda_function.zip \
  --region us-east-1 \
  --query 'LastModified' --output text
aws lambda update-function-code \
  --function-name "${PROJECT}-api" \
  --zip-file fileb://lambda_function.zip \
  --region us-east-1 \
  --query 'LastModified' --output text

echo ""
echo "Done."
