#!/bin/bash

# DrugForge AI - System Test Script
# Tests both frontend and backend functionality

echo "🧪 Running DrugForge AI System Tests"
echo "====================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test configuration
FRONTEND_URL="http://localhost:3000"
BACKEND_URL="http://localhost:5001"
TEST_SMILES="CC(=O)OC1=CC=CC=C1C(=O)O"

# Function to check if service is running
check_service() {
    local url=$1
    local name=$2
    
    echo -n "Testing $name connection... "
    if curl -s -f "$url" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Connected${NC}"
        return 0
    else
        echo -e "${RED}❌ Failed${NC}"
        return 1
    fi
}

# Function to test API endpoint
test_api_endpoint() {
    local endpoint=$1
    local name=$2
    
    echo -n "Testing $name API... "
    
    response=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"smiles\":\"$TEST_SMILES\"}" \
        "$BACKEND_URL$endpoint" \
        --max-time 10)
    
    if [[ $? -eq 0 && $response == *"Predicted"* ]]; then
        echo -e "${GREEN}✅ Working${NC}"
        return 0
    else
        echo -e "${RED}❌ Failed${NC}"
        echo "Response: $response"
        return 1
    fi
}

# Start tests
echo ""
echo "🔍 Testing Service Connectivity"
echo "================================"

# Test backend health
check_service "$BACKEND_URL/health" "Backend Health"
backend_status=$?

# Test frontend
check_service "$FRONTEND_URL" "Frontend"
frontend_status=$?

if [[ $backend_status -ne 0 ]]; then
    echo -e "${RED}❌ Backend not running. Please start with: cd backendML && python app.py${NC}"
    exit 1
fi

if [[ $frontend_status -ne 0 ]]; then
    echo -e "${YELLOW}⚠️ Frontend not running. Start with: npm start${NC}"
fi

echo ""
echo "🧬 Testing Prediction APIs"
echo "=========================="

# Test each prediction endpoint
declare -A endpoints=(
    ["/predict/bbbp"]="BBBP"
    ["/predict/cyp3a4"]="CYP3A4"
    ["/predict/half-life"]="Half-Life"
    ["/predict/cox2"]="COX2"
    ["/predict/hepg2"]="HEPG2"
    ["/predict/ace2"]="ACE2"
    ["/predict/solubility"]="Solubility"
    ["/predict/toxicity"]="Toxicity"
)

failed_tests=0
total_tests=0

for endpoint in "${!endpoints[@]}"; do
    test_api_endpoint "$endpoint" "${endpoints[$endpoint]}"
    if [[ $? -ne 0 ]]; then
        ((failed_tests++))
    fi
    ((total_tests++))
done

echo ""
echo "📊 Testing SMILES Validation"
echo "============================"

# Test invalid SMILES
echo -n "Testing invalid SMILES handling... "
invalid_response=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -d '{"smiles":"INVALID_SMILES"}' \
    "$BACKEND_URL/predict/bbbp" \
    --max-time 10)

if [[ $invalid_response == *"error"* ]]; then
    echo -e "${GREEN}✅ Properly handled${NC}"
else
    echo -e "${RED}❌ Not handled${NC}"
    ((failed_tests++))
fi
((total_tests++))

# Test empty SMILES
echo -n "Testing empty SMILES handling... "
empty_response=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -d '{"smiles":""}' \
    "$BACKEND_URL/predict/bbbp" \
    --max-time 10)

if [[ $empty_response == *"error"* ]]; then
    echo -e "${GREEN}✅ Properly handled${NC}"
else
    echo -e "${RED}❌ Not handled${NC}"
    ((failed_tests++))
fi
((total_tests++))

echo ""
echo "🔍 Testing Frontend Components"
echo "==============================="

if [[ $frontend_status -eq 0 ]]; then
    # Test if React app loads
    echo -n "Testing React app load... "
    if curl -s "$FRONTEND_URL" | grep -q "DrugForge\|root"; then
        echo -e "${GREEN}✅ Loaded${NC}"
    else
        echo -e "${RED}❌ Failed${NC}"
        ((failed_tests++))
    fi
    ((total_tests++))
    
    # Test prediction page routes
    prediction_routes=("/bbbp" "/cyp3a4-predictor" "/half-life" "/cox2" "/hepg2")
    for route in "${prediction_routes[@]}"; do
        echo -n "Testing route $route... "
        if curl -s "$FRONTEND_URL$route" | grep -q "DrugForge\|root"; then
            echo -e "${GREEN}✅ Accessible${NC}"
        else
            echo -e "${YELLOW}⚠️ May need frontend restart${NC}"
        fi
        ((total_tests++))
    done
else
    echo -e "${YELLOW}⚠️ Skipping frontend tests (service not running)${NC}"
fi

echo ""
echo "📈 Test Summary"
echo "==============="

passed_tests=$((total_tests - failed_tests))
success_rate=$((passed_tests * 100 / total_tests))

echo "Total Tests: $total_tests"
echo -e "Passed: ${GREEN}$passed_tests${NC}"
echo -e "Failed: ${RED}$failed_tests${NC}"
echo "Success Rate: $success_rate%"

if [[ $failed_tests -eq 0 ]]; then
    echo ""
    echo -e "${GREEN}🎉 All tests passed! System is working correctly.${NC}"
    echo ""
    echo "✨ Ready for development!"
    echo "  Frontend: $FRONTEND_URL"
    echo "  Backend:  $BACKEND_URL"
    echo "  API Docs: $BACKEND_URL/health"
    exit 0
else
    echo ""
    echo -e "${RED}❌ Some tests failed. Please check the issues above.${NC}"
    echo ""
    echo "🔧 Troubleshooting:"
    echo "  1. Make sure backend is running: cd backendML && python app.py"
    echo "  2. Make sure frontend is running: npm start"
    echo "  3. Check for any error messages in the console"
    echo "  4. Verify all dependencies are installed"
    exit 1
fi
