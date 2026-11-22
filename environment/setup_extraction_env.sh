#!/usr/bin/env bash
set -uo pipefail

PROJ_ROOT="${PBA_PROJECT_ROOT:-/path/to/PMC_filter}"
EXTR_ROOT="${PROJ_ROOT}/PMC_extraction"
VENV_DIR="${EXTR_ROOT}/venv_pmc"
MODEL_NAME="Qwen/Qwen3-32B-AWQ"
MODEL_REVISION="${PBA_MODEL_REVISION:-0499c3ac83fdef8810b907a23894ba91e95eddd8}"
MODEL_LOCAL="${EXTR_ROOT}/pmc_extractor/models/Qwen3-32B-AWQ"
export MODEL_LOCAL MODEL_REVISION
mkdir -p "${EXTR_ROOT}" "${EXTR_ROOT}/pmc_extractor/models"
cd "${EXTR_ROOT}"

export HF_HOME="${EXTR_ROOT}/.hf_cache"
export HF_HUB_CACHE="${EXTR_ROOT}/.hf_cache"
export HUGGINGFACE_HUB_CACHE="${EXTR_ROOT}/.hf_cache"
export PIP_CACHE_DIR="${EXTR_ROOT}/.pip_cache"
export TMPDIR="/tmp/u${USER}_setup_$$"
mkdir -p "${HF_HOME}" "${PIP_CACHE_DIR}" "${TMPDIR}"

if command -v module >/dev/null 2>&1; then
    module load cuda/12.6.3-binary 2>/dev/null \
        || module load cuda/12.2.0-binary 2>/dev/null \
        || echo "[setup] (no cuda module loaded)"
fi

echo "============================================================"
echo "[setup] venv target : ${VENV_DIR}"
echo "[setup] python      : $(python3 --version)"
echo "[setup] glibc       : $(ldd --version | head -1)"
nvidia-smi -L 2>/dev/null
echo "============================================================"

if [[ -d "${VENV_DIR}" ]]; then
    echo "[setup] removing previous ${VENV_DIR}"
    rm -rf "${VENV_DIR}"
fi

python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip wheel setuptools

echo "[setup] installing vllm==0.11.0 (and its torch dep) ..."
pip install --only-binary :all: "vllm==0.11.0" \
    || { echo "ERROR: vllm install failed"; exit 1; }

echo "[setup] pinning transformers to 4.x (vllm 0.11 incompat with t5.x) ..."
pip install --force-reinstall "transformers>=4.55.2,<5"

echo "[setup] pinning numpy to <2.3 (numba 0.61 incompat with np 2.4) ..."
pip install --force-reinstall "numpy>=2.0,<2.3"

echo "[setup] installing extractor deps ..."
pip install \
    "openai>=1.30" "tenacity>=8.2" "orjson>=3.10" "pyyaml>=6" \
    "tqdm>=4.66" "huggingface_hub[hf_transfer]>=0.24" "regex>=2024.5"

if [[ ! -d "${MODEL_LOCAL}" || -z "$(ls -A ${MODEL_LOCAL} 2>/dev/null)" ]]; then
    echo "[setup] downloading ${MODEL_NAME}@${MODEL_REVISION} -> ${MODEL_LOCAL}"
    export HF_HUB_ENABLE_HF_TRANSFER=1
    huggingface-cli download "${MODEL_NAME}" \
        --revision "${MODEL_REVISION}" \
        --local-dir "${MODEL_LOCAL}" \
        --max-workers 8 \
        || { echo "ERROR: model download failed"; exit 1; }
else
    echo "[setup] model already present at ${MODEL_LOCAL}"
fi
du -sh "${MODEL_LOCAL}"

echo
echo "============================================================"
echo "[verify] full stack sanity"
echo "============================================================"

python - <<'PY'
import sys

import torch
print(f"torch  {torch.__version__:20} cuda {torch.version.cuda}")
if not torch.cuda.is_available():
    print("FAIL: torch.cuda.is_available() == False")
    sys.exit(1)
print(f"       CUDA available: True  ({torch.cuda.device_count()} GPU(s))")

try:
    x = torch.randn(256, 256, device='cuda')
    y = (x @ x.T).sum().item()
    print(f"       GPU matmul: ok (sum={y:.2f})")
except Exception as e:
    print(f"FAIL: GPU op -- {type(e).__name__}: {e}"); sys.exit(2)

import vllm, vllm._C
print(f"vllm   {vllm.__version__}  /  vllm._C loads")

from vllm.model_executor.models.registry import ModelRegistry
need = "Qwen3ForCausalLM"
if need not in ModelRegistry.get_supported_archs():
    print(f"FAIL: {need} not in registry"); sys.exit(3)
print(f"arch   {need}: REGISTERED")

for mod in ("openai","tenacity","orjson","yaml","tqdm","huggingface_hub","regex"):
    __import__(mod)
print("extractor deps: all import cleanly")

from pathlib import Path
import os
mdir = Path(os.environ["MODEL_LOCAL"])
files = list(mdir.glob("*.safetensors"))
cfg = mdir / "config.json"
print(f"model  : {len(files)} safetensors shards, config.json {'present' if cfg.exists() else 'MISSING'}")
if not files or not cfg.exists():
    print("FAIL: model files incomplete"); sys.exit(4)

print()
print("=" * 60)
print(f"READY: vllm {vllm.__version__} + Qwen3-32B-AWQ ({os.environ['MODEL_REVISION']})")
print("=" * 60)
PY

rc=$?
if [[ $rc -ne 0 ]]; then
    echo "[setup] verification FAILED with exit ${rc}. See output above."
    exit ${rc}
fi

echo
echo "[setup] DONE."
echo
echo "Next: submit the extraction job from a login or compute node:"
echo "  cd ${PROJ_ROOT}"
echo "  sbatch pmc_extract.sbatch"
