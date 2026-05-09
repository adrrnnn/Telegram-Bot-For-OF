"""
Prepare PyTorch DLL load order on Windows (frozen + dev).

PyQt must not load before torch/torch.lib or c10.dll can fail with WinError 1114.
"""
from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)


def preload_torch() -> None:
    """Add torch/lib to the DLL path and import torch before Qt."""
    # OpenMP can load multiple runtimes in a single process (PyTorch + sklearn),
    # which can surface as native DLL init failures on some Windows machines.
    # This flag prioritizes stability over parallel throughput.
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("OMP_NUM_THREADS", "1")

    if sys.platform != "win32":
        try:
            import torch  # noqa: F401
        except Exception as e:
            logger.debug("torch unavailable: %s", e)
        return

    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None)
        if base:
            torch_lib = os.path.join(base, "torch", "lib")
            if os.path.isdir(torch_lib):
                try:
                    os.add_dll_directory(torch_lib)
                except (OSError, AttributeError):
                    pass
                os.environ["PATH"] = torch_lib + os.pathsep + os.environ.get("PATH", "")
    else:
        try:
            import torch

            root = os.path.join(os.path.dirname(torch.__file__), "lib")
            if os.path.isdir(root):
                try:
                    os.add_dll_directory(root)
                except (OSError, AttributeError):
                    pass
        except Exception as e:
            logger.debug("torch not installed or path setup skipped: %s", e)
            return

    try:
        import torch  # noqa: F401
    except Exception as e:
        logger.warning(
            "PyTorch could not load (%s). Conversation classifier and NSFW detector will be "
            "disabled. On a fresh Windows install, install the **Visual C++ Redistributable x64** "
            "(search Microsoft VC++ 2015-2022 redistributable).",
            e,
        )
