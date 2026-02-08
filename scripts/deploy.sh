#!/bin/bash
# Deploy Lambda function

set -e

echo "Creating Lambda deployment package..."

# Clean previous build
rm -rf build lambda_function.zip

# Create build directory
mkdir -p build

# Copy source code
echo "Copying source code..."
cp -r src build/

# Install dependencies to build directory
echo "Installing dependencies..."
pip install boto3 -t build/ --quiet

# Create ZIP package
echo "Creating ZIP..."
cd build
zip -r ../lambda_function.zip . -q
cd ..

# Cleanup
rm -rf build

echo "✓ Deployment package ready: lambda_function.zip"
echo "  Size: $(du -h lambda_function.zip | cut -f1)"
echo ""
echo "Next: cd terraform && terraform apply"
