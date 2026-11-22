#!/bin/bash
#SBATCH --job-name=pmc_extract
#SBATCH --partition=campus-gpu-bigmem
#SBATCH --account=ACF-UTK0011
#SBATCH --qos=campus-gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=24
#SBATCH --mem=256G
#SBATCH --gres=gpu:2
#SBATCH --time=23:50:00
#SBATCH --signal=B:TERM@1800
#SBATCH --output=pmc_extract_%j.out
#SBATCH --error=pmc_extract_%j.err

set -uo pipefail

PROJ_ROOT="${PBA_PROJECT_ROOT:-/path/to/PMC_filter}"

EXTR_ROOT="${PROJ_ROOT}/PMC_extraction"
EXTRACTOR_DIR="${PBA_EXTRACTOR_DIR:-${SLURM_SUBMIT_DIR:-$(pwd)}}"

INPUT_DIR="${PROJ_ROOT}/plant_bioengineering/TXT_files"
OUTPUT_TSV="${EXTR_ROOT}/plant_bioeng_table.tsv"
LOG_JSONL="${EXTR_ROOT}/extraction_run.jsonl"

MODEL_DIR="${EXTR_ROOT}/pmc_extractor/models/Qwen3-32B-AWQ"

SERVED_NAME="qwen3-32b"
TP_SIZE=2
VLLM_PORT=8000

VENV_PMC="${EXTR_ROOT}/venv_pmc"
CONDA_ENV=""

TICKLE_INTERVAL_S=300

mkdir -p "${EXTR_ROOT}"
cd "${EXTRACTOR_DIR}"

SCRIPT_PATH="$(readlink -f "$0")"
JOB_START_TS=$(date +%s)

export HF_HOME="${EXTR_ROOT}/.hf_cache"
export HF_HUB_CACHE="${EXTR_ROOT}/.hf_cache"
export HUGGINGFACE_HUB_CACHE="${EXTR_ROOT}/.hf_cache"
export VLLM_CACHE_ROOT="${EXTR_ROOT}/.vllm_cache"
export XDG_CACHE_HOME="${EXTR_ROOT}/.xdg_cache"
export TRITON_CACHE_DIR="${EXTR_ROOT}/.triton_cache"
export TORCH_HOME="${EXTR_ROOT}/.torch_cache"
export PIP_CACHE_DIR="${EXTR_ROOT}/.pip_cache"

export TMPDIR="/tmp/u${USER}_${SLURM_JOB_ID:-$$}"

mkdir -p "${HF_HOME}" "${VLLM_CACHE_ROOT}" "${TRITON_CACHE_DIR}" \
         "${TORCH_HOME}" "${PIP_CACHE_DIR}" "${TMPDIR}" "${XDG_CACHE_HOME}"

if (( ${#TMPDIR} > 70 )); then
    echo "ERROR: TMPDIR='${TMPDIR}' is ${#TMPDIR} chars; max 70 for ZMQ IPC sockets."
    echo "       Override TMPDIR before submitting (e.g. /tmp/short)."
    exit 99
fi

export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}

if command -v module >/dev/null 2>&1; then
    module load cuda/12.6.3-binary 2>/dev/null \
        || module load cuda/12.2.0-binary 2>/dev/null \
        || echo "[env] (no cuda module loaded; relying on driver-provided libs)"
fi

if [[ -d "${VENV_PMC}" && -f "${VENV_PMC}/bin/activate" ]]; then
    source "${VENV_PMC}/bin/activate"
    echo "[env] using dedicated venv: ${VENV_PMC}"
elif [[ -n "${CONDA_ENV}" && -d "${CONDA_ENV}" ]]; then
    export PATH="${CONDA_ENV}/bin:${PATH}"
    if command -v conda >/dev/null 2>&1; then
        source "$(conda info --base 2>/dev/null)/etc/profile.d/conda.sh" 2>/dev/null || true
        conda activate "$(basename "${CONDA_ENV}")" 2>/dev/null || true
    fi
    echo "[env] using conda env: ${CONDA_ENV}"
elif [[ -f ./venv/bin/activate ]]; then
    source ./venv/bin/activate
    echo "[env] using legacy ./venv"
else
    echo "ERROR: no Python env found. Run setup_extraction_env.sh first."
    echo "       Expected venv at: ${VENV_PMC}"
    exit 99
fi

echo "============================================================"
echo "Job:     ${SLURM_JOB_ID:-local}"
echo "Host:    $(hostname)"
echo "Start:   $(date -Is)"
echo "PWD:     $(pwd)"
nvidia-smi -L
python --version
python -c "import vllm; print('vllm', vllm.__version__)" 2>&1 | tail -1
echo "Model:   ${MODEL_DIR}"
echo "TP size: ${TP_SIZE}"
echo "Input:   ${INPUT_DIR}"
echo "Output:  ${OUTPUT_TSV}"
echo "HF_HOME: ${HF_HOME}"
echo "============================================================"

[[ -d "${MODEL_DIR}" ]] || { echo "ERROR: model dir missing: ${MODEL_DIR}"; exit 99; }
[[ -d "${INPUT_DIR}"  ]] || { echo "ERROR: input dir missing: ${INPUT_DIR}";  exit 99; }
command -v vllm >/dev/null || { echo "ERROR: vllm CLI not on PATH"; exit 99; }
command -v curl >/dev/null || { echo "ERROR: curl not on PATH"; exit 99; }
python -c "import openai, tenacity, orjson, yaml" \
    || { echo "ERROR: required python deps missing in env"; exit 99; }

python - <<'PY' || exit 99
import sys
import vllm
v = tuple(int(p) for p in vllm.__version__.split('+')[0].split('.')[:3])
if v < (0, 8, 5):
    print(f"ERROR: vllm {vllm.__version__} is too old; need >= 0.8.5", file=sys.stderr)
    print( "       upgrade with:  pip install -U 'vllm>=0.8.5'", file=sys.stderr)
    sys.exit(1)
print(f"vllm  {vllm.__version__}  OK")
PY

python - <<'PY' || exit 99
import sys
try:
    import torch
except Exception as e:
    print(f"ERROR: torch failed to import: {e}", file=sys.stderr); sys.exit(1)
print(f"torch {torch.__version__} | built-for-cuda {torch.version.cuda}")
try:
    ok = torch.cuda.is_available()
except Exception as e:
    print(f"ERROR: torch.cuda.is_available() raised: {e}", file=sys.stderr)
    sys.exit(1)
if not ok:
    print("ERROR: torch reports CUDA NOT available.", file=sys.stderr)
    print("       Most common cause: torch wheel built for a newer CUDA than", file=sys.stderr)
    print("       the host driver supports. Reinstall torch from cu124:", file=sys.stderr)
    print("         pip install --force-reinstall torch torchvision torchaudio \\\\", file=sys.stderr)
    print("             --index-url https://download.pytorch.org/whl/cu124", file=sys.stderr)
    sys.exit(1)
n = torch.cuda.device_count()
if n < 1:
    print(f"ERROR: torch sees {n} GPUs (expected >=1)", file=sys.stderr); sys.exit(1)
print(f"torch CUDA init OK ({n} GPU(s) visible)")
try:
    import vllm._C
    print("vllm._C loads OK against this torch")
except Exception as e:
    print(f"ERROR: vllm._C failed to load: {e}", file=sys.stderr)
    print("HINT : vllm CUDA-extension version mismatch with torch.", file=sys.stderr)
    print("       Either downgrade vllm to a cu12-compiled release:", file=sys.stderr)
    print("           pip install --force-reinstall 'vllm==0.11.0'", file=sys.stderr)
    print("       OR reinstall vllm against your torch backend with uv:", file=sys.stderr)
    print("           uv pip install --force-reinstall vllm --torch-backend=cu126", file=sys.stderr)
    sys.exit(1)
PY

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1}"
export VLLM_USE_FLASHINFER_SAMPLER=0

VLLM_LOG="${EXTR_ROOT}/vllm_${SLURM_JOB_ID:-local}.log"
echo "[serve] launching vLLM (TP=${TP_SIZE}); log -> ${VLLM_LOG}"

vllm serve "${MODEL_DIR}" \
    --served-model-name "${SERVED_NAME}" \
    --host 127.0.0.1 --port "${VLLM_PORT}" \
    --tensor-parallel-size "${TP_SIZE}" \
    --max-model-len 32768 \
    --gpu-memory-utilization 0.92 \
    --dtype auto --kv-cache-dtype auto \
    --enable-prefix-caching \
    --reasoning-parser qwen3 \
    --enforce-eager \
    >"${VLLM_LOG}" 2>&1 &
VLLM_PID=$!

echo "[serve] waiting for http://127.0.0.1:${VLLM_PORT}/v1/models ..."
for i in $(seq 1 180); do
    sleep 5
    if curl -fsS "http://127.0.0.1:${VLLM_PORT}/v1/models" >/dev/null 2>&1; then
        echo "[serve] up after $((i*5))s"
        break
    fi
    if ! kill -0 "${VLLM_PID}" 2>/dev/null; then
        echo "[serve] vLLM died during startup; tail of log:"
        tail -120 "${VLLM_LOG}"
        exit 1
    fi
done
curl -fsS "http://127.0.0.1:${VLLM_PORT}/v1/models" >/dev/null \
    || { echo "[serve] vLLM never came up in 15 min; aborting"; tail -120 "${VLLM_LOG}"; exit 1; }

TICKLE_LOG="${EXTR_ROOT}/gpu_tickle_${SLURM_JOB_ID:-local}.log"
echo "[$(date -Is)] tickle loop starting; interval=${TICKLE_INTERVAL_S}s" > "${TICKLE_LOG}"

gpu_tickle_loop() {
    local i=0
    while true; do
        sleep "${TICKLE_INTERVAL_S}"
        i=$((i + 1))
        local t0 t1 latency_ms
        t0=$(date +%s%N)
        timeout 30 curl -fsS -X POST \
            "http://127.0.0.1:${VLLM_PORT}/v1/completions" \
            -H "Content-Type: application/json" \
            -d "{\"model\":\"${SERVED_NAME}\",\"prompt\":\"ok\",\"max_tokens\":1,\"temperature\":0.0,\"top_p\":1.0}" \
            >/dev/null 2>&1
        local rc=$?
        t1=$(date +%s%N)
        latency_ms=$(( (t1 - t0) / 1000000 ))

        local stats
        stats=$(nvidia-smi --query-gpu=index,utilization.gpu,memory.used,temperature.gpu \
                          --format=csv,noheader,nounits 2>/dev/null | tr '\n' ';')
        printf '[%s] tickle #%d rc=%d %dms gpus=[%s]\n' \
            "$(date -Is)" "${i}" "${rc}" "${latency_ms}" "${stats}" >> "${TICKLE_LOG}"
    done
}
gpu_tickle_loop &
TICKLE_PID=$!
echo "[serve] gpu tickler PID=${TICKLE_PID} (every ${TICKLE_INTERVAL_S}s)"

EXTRACT_PID=""
on_timeout() {
    echo "[trap TERM] wallclock approaching -- saving progress + requeueing"

    if [[ -n "${TICKLE_PID:-}" ]] && kill -0 "${TICKLE_PID}" 2>/dev/null; then
        kill -TERM "${TICKLE_PID}" 2>/dev/null || true
    fi

    if [[ -n "${EXTRACT_PID}" ]] && kill -0 "${EXTRACT_PID}" 2>/dev/null; then
        kill -TERM "${EXTRACT_PID}" 2>/dev/null || true
        for _ in $(seq 1 60); do
            kill -0 "${EXTRACT_PID}" 2>/dev/null || break
            sleep 5
        done
        kill -KILL "${EXTRACT_PID}" 2>/dev/null || true
    fi

    if [[ -n "${VLLM_PID}" ]] && kill -0 "${VLLM_PID}" 2>/dev/null; then
        kill -TERM "${VLLM_PID}" 2>/dev/null || true
        sleep 10
        kill -KILL "${VLLM_PID}" 2>/dev/null || true
    fi

    local processed
    processed=$(wc -l < "${OUTPUT_TSV}.progress" 2>/dev/null || echo 0)
    echo "[trap TERM] processed-so-far: ${processed} PMCIDs"
    echo "[trap TERM] resubmitting self to continue"
    sbatch "${SCRIPT_PATH}"
    exit 0
}
trap on_timeout TERM

echo "[extract] launching extractor against ${INPUT_DIR}"
python -m src.extract \
    --input-dir  "${INPUT_DIR}" \
    --output-tsv "${OUTPUT_TSV}" \
    --log-file   "${LOG_JSONL}" \
    -v &
EXTRACT_PID=$!
wait "${EXTRACT_PID}"
EXTRACT_EXIT=$?

JOB_ELAPSED=$(( $(date +%s) - JOB_START_TS ))
echo "[extract] exit=${EXTRACT_EXIT} elapsed=${JOB_ELAPSED}s"

kill -TERM "${TICKLE_PID}" 2>/dev/null || true
kill -TERM "${VLLM_PID}"   2>/dev/null || true
wait "${TICKLE_PID}" 2>/dev/null || true
wait "${VLLM_PID}"   2>/dev/null || true

if [[ ${EXTRACT_EXIT} -ne 0 && ${JOB_ELAPSED} -lt 300 ]]; then
    echo "[done] extractor crashed in <5 min -- NOT requeueing. Inspect log."
    exit ${EXTRACT_EXIT}
fi
if [[ ${EXTRACT_EXIT} -eq 99 ]]; then
    echo "[done] FATAL exit 99 -- NOT requeueing."
    exit 99
fi

ROWS=$(wc -l < "${OUTPUT_TSV}" 2>/dev/null || echo 0)
PROCESSED=$(wc -l < "${OUTPUT_TSV}.progress" 2>/dev/null || echo 0)
echo "[done] processed PMCIDs : ${PROCESSED}"
echo "[done] TSV rows         : ${ROWS}"

if [[ ${EXTRACT_EXIT} -ne 0 ]]; then
    echo "[done] non-zero exit but ran long; resubmitting to continue"
    sbatch "${SCRIPT_PATH}"
    exit 0
fi

echo "[done] extraction complete -- not requeueing"
