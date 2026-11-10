"""Explicit user device authorization entry; no credentials in arguments."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fast_transfer.device_terminal import main
raise SystemExit(main())
