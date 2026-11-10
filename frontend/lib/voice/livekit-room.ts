"use client";

import { Room, RoomEvent, Track } from "livekit-client";
import type { MediaRoom } from "./controller";

/** No provider REST/BYOL credentials belong here. Only a short-lived scoped room token. */
export function createLiveKitRoom(audioContainer: HTMLElement): MediaRoom {
  const room = new Room({
    adaptiveStream: false,
    dynacast: false,
    reconnectPolicy: { nextRetryDelayInMs: ({ retryCount }) => retryCount < 4 ? Math.min(1000 * 2 ** retryCount, 8000) : null },
  });
  const audioElements = new Set<HTMLMediaElement>();
  const attached = (track: Track) => {
    if (track.kind !== Track.Kind.Audio) return;
    const element = track.attach();
    element.setAttribute("aria-label", "Disclosed AI voice audio");
    audioContainer.appendChild(element); audioElements.add(element);
  };
  const detached = (track: Track) => {
    track.detach().forEach(element => { element.remove(); audioElements.delete(element); });
  };
  room.on(RoomEvent.TrackSubscribed, attached);
  room.on(RoomEvent.TrackUnsubscribed, detached);
  return {
    connect: (url, token) => room.connect(url, token, { autoSubscribe: true }),
    disconnect: async () => {
      try { await room.disconnect(true); }
      finally {
        room.removeAllListeners();
        audioElements.forEach(element => { element.pause(); element.srcObject = null; element.remove(); });
        audioElements.clear();
      }
    },
    // LiveKit requests microphone permission only when enabled; camera/screen never requested.
    microphone: async enabled => { await room.localParticipant.setMicrophoneEnabled(enabled); },
    startAudio: () => room.startAudio(),
    subscribe: listener => {
      const connected = () => listener("connected");
      const reconnecting = () => listener("reconnecting");
      const disconnected = () => listener("disconnected");
      const playback = () => { if (!room.canPlaybackAudio) listener("playback-blocked"); };
      const quality = (value: string, participant: { isLocal: boolean }) => { if (participant.isLocal) listener("quality", value); };
      room.on(RoomEvent.Connected, connected).on(RoomEvent.Reconnected, connected)
        .on(RoomEvent.Reconnecting, reconnecting).on(RoomEvent.Disconnected, disconnected)
        .on(RoomEvent.AudioPlaybackStatusChanged, playback).on(RoomEvent.ConnectionQualityChanged, quality);
      return () => {
        room.off(RoomEvent.Connected, connected).off(RoomEvent.Reconnected, connected)
          .off(RoomEvent.Reconnecting, reconnecting).off(RoomEvent.Disconnected, disconnected)
          .off(RoomEvent.AudioPlaybackStatusChanged, playback).off(RoomEvent.ConnectionQualityChanged, quality);
      };
    },
  };
}
