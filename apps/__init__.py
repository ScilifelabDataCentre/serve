"""
apps package.

Keep this module side-effect free so Django startup (AppConfig.ready) controls
when background tasks are registered.
"""
