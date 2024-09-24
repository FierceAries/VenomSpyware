# VenomSpyware
This project captures screen recordings, audio logs, keypress logs, and screenshots, and automatically sends the data to specified Discord webhooks. It uses OpenCV, MSS, PyAudio, and Pynput for capturing and logging, and Schedule for automating tasks, providing a comprehensive monitoring tool with periodic data uploads to Discord.

This project demonstrates the implementation of a comprehensive monitoring tool that captures screen recordings, audio logs, keypress logs, and periodic screenshots, automatically sending the captured data to specified Discord webhooks.

Features:
Screen Recording: Records the user's screen and sends the video to a Discord webhook.
Audio Recording: Records audio through the system's microphone and sends the recording.
Keylogger: Logs keypresses, except for certain ignored keys, and sends the log file to Discord.
Scheduled Screenshots: Periodically captures screenshots and uploads them to Discord.
Automation: All tasks (screen/audio recording, keylogging, screenshots) run on a scheduled basis.
Technologies Used:
OpenCV & MSS for screen capture.
PyAudio & Wave for audio recording.
Pynput for keylogging.
Schedule for task automation.
Requests for file uploads to Discord.
This project can be extended for more robust logging and data collection features while integrating with other platforms for monitoring purposes.