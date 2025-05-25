#!/bin/bash

echo "🚀 JobMatch Deployment Script"
echo "=============================="

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found. Installing..."
    npm install -g @railway/cli
fi

# Clean repository
echo "🧹 Cleaning repository..."
if [ -f "cleanup_repository.sh" ]; then
    chmod +x cleanup_repository.sh
    ./cleanup_repository.sh
else
    echo "⚠️  cleanup_repository.sh not found, skipping cleanup"
fi

# Check for required files
echo "📋 Checking required files..."
required_files=("main_simple.py" "requirements.txt" "Procfile" "runtime.txt")
for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file found"
    else
        echo "❌ $file missing"
        exit 1
    fi
done

# Deploy to Railway
echo "🚂 Deploying to Railway..."
echo "Please make sure you're logged in to Railway (railway login)"
read -p "Press Enter to continue with deployment..."

# Initialize Railway project if not already done
if [ ! -f "railway.json" ]; then
    echo "🔧 Initializing Railway project..."
    railway init
fi

# Deploy
echo "📤 Deploying to Railway..."
railway up

echo "🎉 Deployment complete!"
echo ""
echo "📋 Next steps:"
echo "1. Set environment variables in Railway dashboard:"
echo "   - OPENAI_API_KEY=your_key_here"
echo "   - ALLOWED_ORIGINS=chrome-extension://*"
echo "2. Update extension files with your Railway URL"
echo "3. Package and submit extension to Chrome Web Store"
echo ""
echo "🔗 Railway Dashboard: https://railway.app/dashboard" 