"""Read GPU stats from nvidia-smi (returns None when no NVIDIA GPU is present)."""
import shutil
import subprocess


def gpu_info() -> dict | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip().splitlines()[0]
        name, used, total, util, temp = [x.strip() for x in out.split(",")]
        return {
            "name": name,
            "mem_used_mb": int(used),
            "mem_total_mb": int(total),
            "util_pct": int(util),
            "temp_c": int(temp),
        }
    except (subprocess.SubprocessError, IndexError, ValueError):
        return None
