# Streaming Issues - Diagnosis & Fixes

## ✅ Issue 1: API Key Exposure in Logs - **FIXED**

### Problem:
Deepgram API key was being logged in plaintext in production logs.

### Fix Applied:
Updated [services/app/shared/config.py](services/app/shared/config.py#L22-L26) to mask the API key:
- Before: `Deepgram API Key: sk_1234567890abcdef...`
- After: `Deepgram API Key: ********cdef` (shows only last 4 chars)

---

## 🔍 Issue 2: Repeated Text + Gibberish Response

### Symptoms:
1. User types a message
2. Message gets echoed/repeated back
3. Then AI gives correct response
4. After completion, gibberish appears

### Likely Causes & Solutions:

#### **Cause 1: Frontend Displaying User Message from Stream**
The backend is correctly NOT sending the user's message in the stream. However, your frontend might be:
- Adding the user's message to the chat before receiving stream response
- Then displaying streamed tokens which include something unexpected

**Frontend Check Needed:**
```typescript
// In your frontend chat component
// Make sure you're NOT doing this:
// displayUserMessage(userInput) <- Shows user message immediately
// then also showing streamed response <- Which might also include user input

// Instead, do this:
// 1. Show user message immediately in UI
// 2. Create a NEW message bubble for AI response
// 3. Stream tokens into AI bubble only
```

#### **Cause 2: Multiple SSE Connections**
If multiple connections are open, responses might be mixing.

**Check:**
- Open browser DevTools → Network tab
- Send a message
- Count how many requests to `/api/v1/chat/messages/stream` are made
- Should be exactly **1** per message

**Fix if multiple:**
- Make sure you're closing previous EventSource/fetch connections
- Use AbortController to cancel previous requests

#### **Cause 3: Incorrect Stream Parsing**
The gibberish at the end might be from incorrectly parsing the final SSE event.

**Backend sends:**
```
data: {"token":"Hello","done":false}\n\n
data: {"token":" world","done":false}\n\n
data: {"token":"","done":true,"fullText":"Hello world","tokenUsage":{...}}\n\n
```

**Frontend should parse:**
```typescript
if (chunk.done === false && chunk.token) {
  // Append token to display
  appendToken(chunk.token);
}
if (chunk.done === true) {
  // Stream complete - do NOT display token (it's empty)
  // Use fullText if needed for verification
  onStreamComplete(chunk.tokenUsage);
}
```

#### **Cause 4: Race Condition in Frontend State**
Multiple renders might be displaying stale state.

**Fix:**
```typescript
// Use useRef for accumulating text instead of state
const streamedTextRef = useRef('');

// On each token
streamedTextRef.current += chunk.token;
setDisplayText(streamedTextRef.current);

// Clear on new message
const sendMessage = () => {
  streamedTextRef.current = '';
  // ... send request
};
```

---

## 🔍 Debug Steps

### **Step 1: Check Backend Logs**
Look at your Railway logs for a message:
```
[Gemini API Stream] Response Time: X.XXs | Tokens - Prompt: XXX, Completion: XXX
```

This confirms backend is working correctly.

### **Step 2: Check Network Tab**
In browser DevTools → Network:
1. Find the `messages/stream` request
2. Click it → Response tab
3. You should see:
```
data: {"token":"First","done":false,"fullText":"First","sessionId":"xxx"}\n\n
data: {"token":" chunk","done":false,"fullText":"First chunk","sessionId":"xxx"}\n\n
...
data: {"token":"","done":true,"fullText":"Complete response","sessionId":"xxx","messageId":"xxx","tokenUsage":{...}}\n\n
```

If you see the user's input text in ANY of these events, that's the problem.

### **Step 3: Check Frontend Console**
Add debug logging to your frontend stream handler:
```typescript
for await (const chunk of streamResponse) {
  console.log('RAW CHUNK:', chunk);
  console.log('Token:', chunk.token);
  console.log('Done:', chunk.done);
}
```

---

## 🚀 What to Check in Your Frontend

### **File to Check:** 
Your frontend chat component (likely `WelcomeScreen.tsx` or similar)

### **Look for:**

1. **Are you showing user message before streaming?**
```typescript
// CORRECT
const messages = [...prevMessages, userMessage];
// Then stream AI response into NEW message

// WRONG
const messages = [...prevMessages, userMessage, aiMessage]; // Both at once
```

2. **Are you appending tokens correctly?**
```typescript
// CORRECT
if (!chunk.done && chunk.token) {
  setAiResponse(prev => prev + chunk.token);
}
if (chunk.done) {
  // Don't append chunk.token (it's empty)
  onComplete();
}

// WRONG
setAiResponse(prev => prev + chunk.token); // Appends even when done=true
```

3. **Are you clearing state between messages?**
```typescript
// CORRECT
const sendNewMessage = () => {
  setAiResponse(''); // Clear previous
  startStream();
};

// WRONG
// Not clearing, so old response + new response = gibberish
```

---

## 📋 Expected Flow

### **Correct Sequence:**

1. User types: "Hello"
2. Frontend shows user message immediately in chat
3. Frontend makes POST to `/api/v1/chat/messages/stream`
4. Backend receives "Hello"
5. Backend creates user message in DB
6. Backend streams AI response:
   - `{"token":"Hi","done":false}` → Frontend shows "Hi"
   - `{"token":" there","done":false}` → Frontend shows "Hi there"
   - `{"token":"!","done":false}` → Frontend shows "Hi there!"
   - `{"token":"","done":true,"fullText":"Hi there!"}` → Frontend marks complete
7. Frontend shows final message: "Hi there!"

### **What Should NOT Happen:**
- Backend sending user's "Hello" in stream ❌
- Frontend showing "Hello" twice ❌
- Random characters after response ❌

---

## 🛠️ Quick Fixes

### **Fix 1: Backend API Key** ✅ 
Already fixed - no longer logging plaintext.

### **Fix 2: Frontend Stream Handling**
Share your frontend streaming code and I can help debug it specifically.

### **Fix 3: Clear Browser Cache**
Sometimes old JavaScript is cached:
```
1. Open DevTools
2. Right-click Refresh button
3. Click "Empty Cache and Hard Reload"
```

---

## 📝 Next Steps

1. **Check Railway logs** - confirm backend is working
2. **Check browser Network tab** - see exact SSE events being sent
3. **Share frontend code** - I can debug the exact issue
4. **Test locally** - does it work on localhost:3000?

---

**Last Updated:** December 16, 2025

Need help debugging the frontend? Share:
1. The component that handles streaming
2. Screenshot of Network tab showing the SSE response
3. Screenshot of browser console during streaming
