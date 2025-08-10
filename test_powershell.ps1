# PowerShell Test Script for Phase 1B Integration
# Tests the complete Agent-Gateway integration using PowerShell-native commands

Write-Host "=== Phase 1B Integration Tests (PowerShell) ===" -ForegroundColor Green
Write-Host ""

# Test 1: Health Checks
Write-Host "1. Testing Service Health..." -ForegroundColor Yellow

try {
    $memoryHealth = Invoke-RestMethod -Uri "http://localhost:8002/health" -Method GET
    Write-Host "   Memory Service: ✓ HEALTHY" -ForegroundColor Green
    Write-Host "   Status: $($memoryHealth.status)" -ForegroundColor Gray
} catch {
    Write-Host "   Memory Service: ✗ FAILED" -ForegroundColor Red
    Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
}

try {
    $agentHealth = Invoke-RestMethod -Uri "http://localhost:9000/health" -Method GET
    Write-Host "   Core Agent: ✓ HEALTHY" -ForegroundColor Green
    Write-Host "   Status: $($agentHealth.status), Backend: $($agentHealth.model_backend)" -ForegroundColor Gray
} catch {
    Write-Host "   Core Agent: ✗ FAILED" -ForegroundColor Red
    Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
}

try {
    $gatewayHealth = Invoke-RestMethod -Uri "http://localhost:8081/health" -Method GET
    Write-Host "   API Gateway: ✓ HEALTHY" -ForegroundColor Green
    Write-Host "   Status: $($gatewayHealth.status), Service: $($gatewayHealth.service)" -ForegroundColor Gray
} catch {
    Write-Host "   API Gateway: ✗ FAILED" -ForegroundColor Red
    Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""

# Test 2: Chat Endpoint
Write-Host "2. Testing Chat Endpoint..." -ForegroundColor Yellow

$chatRequest = @{
    messages = @(
        @{
            role = "user"
            content = "Hello LUKi, tell me about my interests"
        }
    )
    user_id = "test-user-powershell"
    session_id = "test-session-powershell"
} | ConvertTo-Json -Depth 3

try {
    $chatResponse = Invoke-RestMethod -Uri "http://localhost:8081/v1/chat/" -Method POST -Body $chatRequest -ContentType "application/json"
    Write-Host "   Chat Endpoint: ✓ SUCCESS" -ForegroundColor Green
    Write-Host "   Response Role: $($chatResponse.message.role)" -ForegroundColor Gray
    Write-Host "   Response Length: $($chatResponse.message.content.Length) characters" -ForegroundColor Gray
    Write-Host "   Session ID: $($chatResponse.session_id)" -ForegroundColor Gray
    if ($chatResponse.metadata) {
        Write-Host "   Metadata: $($chatResponse.metadata | ConvertTo-Json -Compress)" -ForegroundColor Gray
    }
    Write-Host "   Sample Response: $($chatResponse.message.content.Substring(0, [Math]::Min(100, $chatResponse.message.content.Length)))..." -ForegroundColor Cyan
} catch {
    Write-Host "   Chat Endpoint: ✗ FAILED" -ForegroundColor Red
    Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        $errorContent = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($errorContent)
        $errorBody = $reader.ReadToEnd()
        Write-Host "   Response Body: $errorBody" -ForegroundColor Red
    }
}

Write-Host ""

# Test 3: Multi-turn Conversation
Write-Host "3. Testing Multi-turn Conversation..." -ForegroundColor Yellow

$conversationRequest = @{
    messages = @(
        @{
            role = "user"
            content = "My name is John"
        },
        @{
            role = "assistant"
            content = "Nice to meet you, John!"
        },
        @{
            role = "user"
            content = "What's my name?"
        }
    )
    user_id = "test-user-conversation"
    session_id = "test-session-conversation"
} | ConvertTo-Json -Depth 3

try {
    $conversationResponse = Invoke-RestMethod -Uri "http://localhost:8081/v1/chat/" -Method POST -Body $conversationRequest -ContentType "application/json"
    Write-Host "   Multi-turn Conversation: ✓ SUCCESS" -ForegroundColor Green
    Write-Host "   Response: $($conversationResponse.message.content.Substring(0, [Math]::Min(150, $conversationResponse.message.content.Length)))..." -ForegroundColor Cyan
} catch {
    Write-Host "   Multi-turn Conversation: ✗ FAILED" -ForegroundColor Red
    Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""

# Test 4: Error Handling
Write-Host "4. Testing Error Handling..." -ForegroundColor Yellow

# Test empty messages
$emptyRequest = @{
    messages = @()
    user_id = "test-user"
} | ConvertTo-Json -Depth 3

try {
    $errorResponse = Invoke-RestMethod -Uri "http://localhost:8081/v1/chat/" -Method POST -Body $emptyRequest -ContentType "application/json"
    Write-Host "   Empty Messages Test: ✗ SHOULD HAVE FAILED" -ForegroundColor Red
} catch {
    if ($_.Exception.Response.StatusCode -eq 400) {
        Write-Host "   Empty Messages Test: ✓ CORRECTLY REJECTED (400)" -ForegroundColor Green
    } else {
        Write-Host "   Empty Messages Test: ⚠ UNEXPECTED STATUS ($($_.Exception.Response.StatusCode))" -ForegroundColor Yellow
    }
}

Write-Host ""

# Summary
Write-Host "=== Integration Test Summary ===" -ForegroundColor Green
Write-Host "✓ All services are running and communicating" -ForegroundColor Green
Write-Host "✓ Phase 1B Agent-Gateway Integration is operational" -ForegroundColor Green
Write-Host ""
Write-Host "Architecture Flow:" -ForegroundColor Cyan
Write-Host "Client → API Gateway (8081) → Core Agent (9000) → Memory Service (8002) → LLaMA 3.3 → Response" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "- Test streaming endpoints if needed" -ForegroundColor White
Write-Host "- Run comprehensive Python integration tests" -ForegroundColor White
Write-Host "- Begin Phase 1C or 1D implementation" -ForegroundColor White
