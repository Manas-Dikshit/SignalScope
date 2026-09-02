"""SignalScope DSP core.

Offline, explainable RF signal analysis for authorized .IQ / .wav recordings.
Every estimate carries a source (metadata / user_supplied / measured / estimated
/ hypothesis) and a confidence in [0, 1]. Nothing is ever reported as an exact
measurement unless it actually came from file metadata or a user-supplied value.
"""

__version__ = "0.1.0-mvp"
