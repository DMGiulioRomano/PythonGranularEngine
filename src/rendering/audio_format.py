# src/rendering/audio_format.py
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioFormat:
    label: str
    extension: str
    sf_format: str
    sf_subtype: str


FORMATS = {
    'aiff': AudioFormat('aiff', '.aif',  'AIFF', 'FLOAT'),
    'aif':  AudioFormat('aiff', '.aif',  'AIFF', 'FLOAT'),
    'wav':  AudioFormat('wav',  '.wav',  'WAV',  'FLOAT'),
    'flac': AudioFormat('flac', '.flac', 'FLAC', 'PCM_24'),
}

DEFAULT_FORMAT = FORMATS['aiff']
