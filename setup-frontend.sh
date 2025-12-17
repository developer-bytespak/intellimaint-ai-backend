#!/bin/bash

# Frontend Setup Helper Script
# This script helps identify what needs to be changed in your frontend

echo "========================================="
echo "Frontend API Configuration Helper"
echo "========================================="
echo ""

# Get backend URL from user
read -p "Enter your Render backend URL (e.g., https://your-app.onrender.com): " BACKEND_URL

if [ -z "$BACKEND_URL" ]; then
    echo "Error: Backend URL is required"
    exit 1
fi

echo ""
echo "Your backend URL: $BACKEND_URL"
echo ""
echo "========================================="
echo "Environment Variables to Set in Vercel:"
echo "========================================="
echo ""
echo "For Next.js:"
echo "  NEXT_PUBLIC_API_URL=$BACKEND_URL"
echo ""
echo "For Vite/React:"
echo "  VITE_API_URL=$BACKEND_URL"
echo ""
echo "For Create React App:"
echo "  REACT_APP_API_URL=$BACKEND_URL"
echo ""
echo "========================================="
echo "Files to Update in Your Frontend:"
echo "========================================="
echo ""
echo "1. Create/Update .env.production:"
echo "   Add: NEXT_PUBLIC_API_URL=$BACKEND_URL"
echo "   (or VITE_API_URL / REACT_APP_API_URL depending on framework)"
echo ""
echo "2. Update API client configuration:"
echo "   Replace hardcoded 'http://localhost:3000' with environment variable"
echo ""
echo "3. Common locations to check:"
echo "   - src/api/client.ts"
echo "   - src/utils/api.ts"
echo "   - src/config/api.ts"
echo "   - src/services/api.ts"
echo ""
echo "========================================="
echo "Commands to Run in Your Frontend Repo:"
echo "========================================="
echo ""
echo "# Find all localhost references:"
echo "grep -r 'localhost:3000' src/"
echo ""
echo "# Find environment variable usage:"
echo "grep -r 'process.env' src/"
echo ""
echo "========================================="
echo "After updating, remember to:"
echo "========================================="
echo "1. Set environment variables in Vercel dashboard"
echo "2. Rebuild: npm run build"
echo "3. Redeploy to Vercel"
echo "4. Test the connection"
echo ""
echo "See FRONTEND_SETUP_GUIDE.md for detailed instructions"
echo ""

