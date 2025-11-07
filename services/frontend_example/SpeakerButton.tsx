import React, { useState, useRef, useEffect } from 'react';

interface SpeakerButtonProps {
  text: string;
  apiUrl?: string;
  className?: string;
}

const SpeakerButton: React.FC<SpeakerButtonProps> = ({ 
  text, 
  apiUrl = 'http://localhost:8000/api/v1/asr/synthesize',
  className = '' 
}) => {
  const [isLoading, setIsLoading] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);

  // Stop any currently playing audio when component unmounts or new audio starts
  useEffect(() => {
    return () => {
      if (currentAudioRef.current) {
        currentAudioRef.current.pause();
        currentAudioRef.current = null;
      }
    };
  }, []);

  const handleSpeakerClick = async () => {
    // Stop any currently playing audio
    if (currentAudioRef.current) {
      console.log('[Speaker] Stopping previous audio');
      currentAudioRef.current.pause();
      currentAudioRef.current.currentTime = 0;
      currentAudioRef.current = null;
      setIsPlaying(false);
    }

    if (!text || text.trim() === '') {
      console.warn('[Speaker] No text provided for TTS');
      return;
    }

    setIsLoading(true);
    console.log('[Speaker] Requesting TTS for text:', text);

    try {
      const response = await fetch(apiUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ text }),
      });

      console.log('[Speaker] TTS Response status:', response.status);
      console.log('[Speaker] TTS Response headers:', Object.fromEntries(response.headers.entries()));

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        console.error('[Speaker] TTS Error:', errorData);
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
      }

      // Get audio blob
      const audioBlob = await response.blob();
      console.log('[Speaker] Audio blob received, size:', audioBlob.size, 'bytes');

      // Create audio URL and play
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      
      // Store reference to current audio
      currentAudioRef.current = audio;
      audioRef.current = audio;

      // Set up event listeners
      audio.onloadstart = () => {
        console.log('[Speaker] Audio loading started');
        setIsLoading(false);
        setIsPlaying(true);
      };

      audio.onplay = () => {
        console.log('[Speaker] Audio playback started');
        setIsLoading(false);
        setIsPlaying(true);
      };

      audio.onended = () => {
        console.log('[Speaker] Audio playback ended');
        setIsPlaying(false);
        URL.revokeObjectURL(audioUrl);
        currentAudioRef.current = null;
      };

      audio.onerror = (error) => {
        console.error('[Speaker] Audio playback error:', error);
        setIsLoading(false);
        setIsPlaying(false);
        URL.revokeObjectURL(audioUrl);
        currentAudioRef.current = null;
      };

      // Start playing
      await audio.play();
      console.log('[Speaker] Audio play() called');

    } catch (error) {
      console.error('[Speaker] Error fetching or playing audio:', error);
      setIsLoading(false);
      setIsPlaying(false);
    }
  };

  return (
    <button
      onClick={handleSpeakerClick}
      disabled={isLoading || !text}
      className={`speaker-button ${className} ${isLoading ? 'loading' : ''} ${isPlaying ? 'playing' : ''}`}
      aria-label="Play audio"
    >
      {isLoading ? (
        <span className="loader">
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="spinner"
          >
            <circle cx="12" cy="12" r="10" opacity="0.25" />
            <path d="M12 2a10 10 0 0 1 10 10" opacity="0.75" />
          </svg>
        </span>
      ) : (
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
          <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07" />
        </svg>
      )}
    </button>
  );
};

// Hook for managing multiple speakers (stops previous when new one starts)
export const useSpeakerManager = () => {
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);

  const playAudio = async (audioUrl: string, text: string) => {
    // Stop any currently playing audio
    if (currentAudioRef.current) {
      console.log('[SpeakerManager] Stopping previous audio');
      currentAudioRef.current.pause();
      currentAudioRef.current.currentTime = 0;
      currentAudioRef.current = null;
    }

    try {
      const audio = new Audio(audioUrl);
      currentAudioRef.current = audio;

      audio.onended = () => {
        console.log('[SpeakerManager] Audio ended');
        currentAudioRef.current = null;
      };

      audio.onerror = (error) => {
        console.error('[SpeakerManager] Audio error:', error);
        currentAudioRef.current = null;
      };

      await audio.play();
      console.log('[SpeakerManager] Playing audio for:', text);
    } catch (error) {
      console.error('[SpeakerManager] Error playing audio:', error);
      currentAudioRef.current = null;
    }
  };

  const stopCurrentAudio = () => {
    if (currentAudioRef.current) {
      console.log('[SpeakerManager] Manually stopping audio');
      currentAudioRef.current.pause();
      currentAudioRef.current.currentTime = 0;
      currentAudioRef.current = null;
    }
  };

  return { playAudio, stopCurrentAudio };
};

export default SpeakerButton;

