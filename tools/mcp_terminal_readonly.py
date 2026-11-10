"""Launch from a reviewed checkout, without site packages or token arguments."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fast_transfer.mcp_terminal import main
raise SystemExit(main())
