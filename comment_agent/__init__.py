import logging

# Attach a no-op handler so backend modules can log during import/tests without
# emitting output or "No handlers could be found" warnings. Entry points call
# comment_agent.logging_config.configure_logging() to install real handlers.
logging.getLogger("comment_agent").addHandler(logging.NullHandler())
