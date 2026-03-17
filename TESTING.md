# Testing Guide

## Quick Start

### 1. Start Backend Server

```bash
cd /Users/rajatpatel/research/nebius_ai_hack/LabPilot
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8010
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8010
```

### 2. Start Frontend (in a new terminal)

```bash
cd /Users/rajatpatel/research/nebius_ai_hack/labpilot_frontend
npm run dev
```

The frontend should start on `http://localhost:3001` (or next available port).

### 3. Verify Backend Health

Open: `http://127.0.0.1:8010/health`

Should return: `{"status":"ok"}`

---

## Testing Conversation Flow Improvements

### Test 1: Immediate User Message Display

**Steps:**
1. Navigate to `http://localhost:3001/conversations`
2. Create a new conversation (click "New Conversation")
3. Type a message: `"Recommend a simple starter experiment"`
4. Press Enter or click Send

**Expected Behavior:**
- ✅ Your message appears **immediately** (no delay)
- ✅ A "Thinking..." message with spinner appears right after
- ✅ Input field clears immediately
- ✅ No flickering or duplicate messages

### Test 2: Smooth Response Loading

**Steps:**
1. Send a message that triggers a recommendation (e.g., `"What's the next best experiment?"`)
2. Wait for the backend to process (may take 5-10 seconds for LLM + Tavily)

**Expected Behavior:**
- ✅ "Thinking..." indicator shows while waiting
- ✅ When response arrives, "Thinking..." is replaced smoothly with the real response
- ✅ No duplicate messages appear
- ✅ Metadata panel (right side) populates with recommendation/reasoning/literature

### Test 3: No Redundant API Calls

**Steps:**
1. Open browser DevTools → Network tab
2. Send a message
3. Watch the network requests

**Expected Behavior:**
- ✅ Only **one** POST to `/api/conversations/{id}/messages` (the send)
- ✅ Background refresh calls happen **after** response (with ~500ms delay)
- ✅ No immediate duplicate GET requests

### Test 4: Polling Pause During Send

**Steps:**
1. Send a message
2. While it's processing, check the network tab

**Expected Behavior:**
- ✅ No polling requests (GET `/api/conversations/{id}/messages`) while `sending === true`
- ✅ Polling resumes after response completes (every 4 seconds)

### Test 5: Error Handling

**Steps:**
1. Stop the backend server (Ctrl+C)
2. Try to send a message in the frontend

**Expected Behavior:**
- ✅ Error toast appears
- ✅ "Thinking..." message is removed
- ✅ Your input text is restored (you can try again)
- ✅ No broken UI state

### Test 6: Quick Start Button

**Steps:**
1. Open a new/empty conversation
2. Click "Recommend Starter Experiment" button

**Expected Behavior:**
- ✅ "Thinking..." appears immediately
- ✅ Button is disabled while processing
- ✅ Response appears smoothly when ready

### Test 7: Multiple Messages in Sequence

**Steps:**
1. Send: `"Recommend next experiment"`
2. Wait for response
3. Immediately send: `"Tell me more about the literature"`

**Expected Behavior:**
- ✅ Both messages process independently
- ✅ No interference between requests
- ✅ Each gets its own "Thinking..." indicator
- ✅ Responses appear in correct order

---

## What to Look For (Success Criteria)

### ✅ Smooth UX
- Messages appear instantly (no waiting for backend)
- Clear visual feedback during processing
- No flickering or duplicate content
- Input clears immediately on send

### ✅ Performance
- No redundant API calls
- Polling pauses during active sends
- Background refreshes are delayed (not blocking)

### ✅ Reliability
- Error states handled gracefully
- UI never gets stuck in "thinking" state
- Messages persist correctly after refresh

---

## Debugging Tips

### Check Backend Logs
Watch the terminal where `uvicorn` is running for:
- Request timing
- LLM/Tavily API calls
- Any errors

### Check Frontend Console
Open browser DevTools → Console for:
- React errors
- API errors
- State updates

### Check Network Tab
Monitor:
- Request count (should be minimal)
- Response times
- Failed requests

### Common Issues

**"Failed to fetch" error:**
- Backend not running on port 8010
- CORS issue (check backend logs)

**Messages not appearing:**
- Check backend logs for errors
- Verify database is initialized (`backend/db.sqlite` exists)

**"Thinking..." stuck:**
- Backend crashed or timed out
- Check backend logs for LLM/Tavily errors
- Refresh the page to reset state

---

## Manual API Testing (Optional)

You can also test the backend directly:

```bash
# Create a conversation
curl -X POST http://127.0.0.1:8010/api/conversations \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Thread"}'

# Send a message (replace {conversation_id} with ID from above)
curl -X POST http://127.0.0.1:8010/api/conversations/{conversation_id}/messages \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Recommend next experiment",
    "data_path": "data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx",
    "model_path": "artifacts/surrogate_suzuki.joblib",
    "top_k": 5,
    "use_llm": true,
    "use_tavily": true
  }'
```
