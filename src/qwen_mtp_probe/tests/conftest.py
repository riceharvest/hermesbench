import sys

try:
    import torch
    import transformers
except ImportError:
    collect_ignore_glob = ["test_*.py"]
