"""
Shared test fixtures and AWS mock setup
Runs before any source module is imported so module-level boto3 calls are intercepted
"""

import os
import sys
from unittest.mock import MagicMock

# --- environment variables required by both source modules ---
os.environ.setdefault("ANALYSIS_RESULTS_TABLE", "test-analysis")
os.environ.setdefault("BLOCKLIST_TABLE", "test-blocklist")
os.environ.setdefault("FORWARD_TO_EMAIL", "test@example.com")
os.environ.setdefault("SENDER_EMAIL", "noreply@example.com")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

# --- replace boto3 in sys.modules before source modules are imported ---
# This prevents any real AWS calls (and credential errors) during unit tests.
# boto3 uses subpackage imports (boto3.dynamodb.conditions) so we must register
# each submodule separately — a single top-level MagicMock is not enough
_mock_boto3 = MagicMock()
_mock_table = MagicMock()
_mock_boto3.resource.return_value.Table.return_value = _mock_table
sys.modules.setdefault("boto3", _mock_boto3)
sys.modules.setdefault("boto3.dynamodb", MagicMock())
sys.modules.setdefault("boto3.dynamodb.conditions", MagicMock())
