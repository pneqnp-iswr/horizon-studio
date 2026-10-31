"""A stand-in for horizon-client's --launch-api reply (docs/api/launch-reference.md at Horizon 3c1d4b39)."""
import json
import os
import sys

if sys.argv[1:] == ["--launch-api"]:
    if "FAKE_LAUNCH_REPLY" in os.environ:  # adversarial replies: a list, text, an empty line
        print(os.environ["FAKE_LAUNCH_REPLY"])
        sys.exit(0)
    options = os.environ.get("FAKE_LAUNCH_OPTIONS", "--resources,--game-dir,--home,--width,--height").split(",")
    print(json.dumps({"horizon": "v2026.10.31", "launch_api": os.environ.get("FAKE_LAUNCH_API", "0.1.0"),
                      "minecraft": "26.3", "options": [{"name": name, "value": "X"} for name in options if name]}))
    sys.exit(0)
sys.exit(2)
