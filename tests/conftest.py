import os

os.environ["DATABASE_URL"] = "sqlite:///./test_customer_ops.db"
os.environ["AIRTABLE_ENABLED"] = "false"
os.environ["AIRTABLE_API_KEY"] = "replace_me"
os.environ["NVIDIA_NIM_API_KEY"] = "replace_me"
os.environ["ORCHESTRATION_MODE"] = "direct"
