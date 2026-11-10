"""Published purpose versions; login never grants insurance consent."""

CONSENT_VERSION = "2026-11-04"
VOICE_CONSENT_VERSION = "voice-2026-11-05"
VOICE_REPORT_SPEECH_CONSENT_VERSION = "voice-report-speech-2026-11-09"


def purpose_version(scope: str) -> str:
    """Report export is a separate purpose; old audio/general receipts keep their versions."""
    if scope == "voice_report_speech":
        return VOICE_REPORT_SPEECH_CONSENT_VERSION
    return VOICE_CONSENT_VERSION if scope.startswith("voice_") else CONSENT_VERSION


CONSENT_PURPOSES = {
    "voice_demo": (
        "Run the synthetic no-audio demo and store its session and simulated usage records."
    ),
    "process_comparison": (
        "Process the health and family details you submit for a health-cover comparison."
    ),
    "save_profile": (
        "Save your family profile for future signed-in visits until you withdraw consent."
    ),
    "receive_updates": (
        "Use your account to receive service updates when a delivery channel is configured."
    ),
    "voice_microphone": (
        "Allow this browser to use your microphone for an Assurely voice conversation."
    ),
    "voice_vendor_processing": (
        "Allow the voice provider to process audio and speech during the conversation."
    ),
    "voice_report_speech": (
        "Allow Assurely to send the complete independently reviewed report sentences, "
        "their sources and verification dates to the voice provider for speech during "
        "development. This account-level permission applies to future sessions and "
        "their independently reviewed, bound reports until you withdraw it. Use fictional "
        "staging cases only. This may disclose sensitive insurance information. "
        "Microphone or audio consent alone does not authorize this report sharing."
    ),
    "voice_transcription": (
        "Allow the voice provider to create a transcript for this conversation."
    ),
    "voice_summary": (
        "Allow Assurely to retain a minimized, cited call summary after the conversation."
    ),
}
