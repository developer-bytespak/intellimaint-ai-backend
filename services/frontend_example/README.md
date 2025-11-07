# Speaker Button Component

This is an example React component that demonstrates how to implement a speaker button with the following features:

1. **Loader**: Shows a spinner when the button is clicked until audio starts playing
2. **Stop Previous Audio**: Automatically stops any currently playing audio when a new speaker button is clicked
3. **Console Logging**: Logs all responses and events to the console

## Usage

### Basic Usage

```tsx
import SpeakerButton from './SpeakerButton';

function App() {
  return (
    <div>
      <SpeakerButton text="Hello, this is a test message" />
    </div>
  );
}
```

### Multiple Speakers (with auto-stop)

```tsx
import SpeakerButton from './SpeakerButton';

function ChatComponent() {
  const messages = [
    { id: 1, text: "First message" },
    { id: 2, text: "Second message" },
    { id: 3, text: "Third message" },
  ];

  return (
    <div>
      {messages.map((msg) => (
        <div key={msg.id}>
          <p>{msg.text}</p>
          <SpeakerButton text={msg.text} />
        </div>
      ))}
    </div>
  );
}
```

### Using the Hook

```tsx
import { useSpeakerManager } from './SpeakerButton';

function CustomComponent() {
  const { playAudio, stopCurrentAudio } = useSpeakerManager();

  const handlePlay = async (text: string) => {
    const response = await fetch('http://localhost:8000/api/v1/asr/synthesize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    await playAudio(url, text);
  };

  return (
    <button onClick={() => handlePlay("Hello world")}>
      Play
    </button>
  );
}
```

## Features

- ✅ Shows loader when clicked
- ✅ Automatically stops previous audio when new one starts
- ✅ Console logs all responses and events
- ✅ Handles errors gracefully
- ✅ Cleanup on unmount

## API Configuration

By default, the component uses `http://localhost:8000/api/v1/asr/synthesize`. You can override this:

```tsx
<SpeakerButton 
  text="Hello" 
  apiUrl="https://your-api.com/api/v1/asr/synthesize" 
/>
```

## Console Logs

The component logs the following to the console:
- `[Speaker] Requesting TTS for text: ...]` - When request starts
- `[Speaker] TTS Response status: ...` - Response status
- `[Speaker] TTS Response headers: ...` - Response headers
- `[Speaker] Audio blob received, size: ...` - Audio blob info
- `[Speaker] Audio loading started` - When audio starts loading
- `[Speaker] Audio playback started` - When playback begins
- `[Speaker] Audio playback ended` - When playback completes
- `[Speaker] Stopping previous audio` - When stopping previous audio

