import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY"]     = "False"
os.environ["POSTHOG_DISABLED"]     = "True"
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"