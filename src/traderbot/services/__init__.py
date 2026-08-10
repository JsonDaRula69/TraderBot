"""TraderBot always-on daemon service package (DD-016, DD-022).

Contains the service templates (systemd, launchd, Windows Task Scheduler)
and the Python logic to resolve binary paths and deploy/remove the daemon
service. Templates use ``{placeholder}`` syntax substituted at install time
with Python ``str.format`` — no shell scripts.
"""
