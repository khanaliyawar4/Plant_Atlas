# Plant Bioengineering Atlas — PMC screening and extraction pipeline

Extract structured plant-bioengineering records from PMC plain-text articles using an OpenAI-compatible model server. The pipeline prepares article bodies, applies a regex pre-filter and LLM gate, extracts records, checks supporting quotations, and writes a TSV plus audit logs.

This repository downloads and screens articles from the public PMC Open Access AWS bucket, then extracts structured records with the configured language model. It contains acquisition, screening and extraction software, retained analysis scripts, release tables, a reporting profile and supplementary material. Atlas creation is not included.

## Contents

- `analysis/`: optional analyses requiring the external inputs described below.
- `data/`: release tables and release notes.
- `reporting_profile/`: reporting schema and examples.
- `supplementary_data/`: supplementary workbook.
- `screening/pmc_batch_download_filter.py`: public PMC AWS download and batch screening.
- `screening/plant_bioeng_filter/`: original article-screening rules and local screening tool.

- `extraction/src/`: article preparation, prompts, schemas, model client, evidence checks, output and resume support.
- `extraction/config/default.yaml`: model, input/output paths, generation and filtering settings.
- `extraction/hpc/run_extraction.sbatch`: optional SLURM job that starts vLLM and runs extraction.
- `environment/setup_extraction_env.sh`: Linux GPU environment setup and pinned model download.
- `requirements/`: client, GPU server and test dependencies.


## Requirements and inputs

Use Python 3.11. Download article text using the PMC command below, or supply local article files. A model server is also required; model weights are not included. Place UTF-8 text files directly in `inputs/TXT_files/`, named `PMC1234567.1.txt` (PMCID, version, `.txt`). Other filenames and nested folders are ignored. Text should preserve section headings and, when available, DOI and article-type metadata. A run selects one version per PMCID in sorted filename order.

The default model is Qwen3-32B-AWQ served as `qwen3-32b` at `http://127.0.0.1:8000/v1`. The supplied GPU setup uses Linux, CUDA and two NVIDIA GPUs with sufficient memory for this model and context length. An existing compatible server lets you run the Python client without installing vLLM locally. Native Windows users can use that client route; the supplied server and batch scripts require Linux (or a compatible Linux environment).

## Install the extraction client

From this repository's root, in an activated Python environment:

```bash
python -m pip install -r requirements/client.txt -r requirements/screening.txt
python -m pip install -e ./screening
```

Edit `server` in `extraction/config/default.yaml` to match your endpoint, served model name and API key. The server must support the request options used by `extraction/src/llm_client.py`, including guided JSON when enabled. For an endpoint without guided decoding, set `extraction.use_guided_json: false`; other model-specific options may require client changes.

## Download and screen PMC articles

With the Python environment activated, run from the repository root:

```bash
python screening/pmc_batch_download_filter.py --output inputs/TXT_files --tmp-dir tmp/pmc --num-shards 1 --shard 0
```

This connects anonymously to `s3://pmc-oa-opendata/`; AWS credentials are not required. It lists available article-version folders, downloads text and XML in temporary batches, applies the original rule-based screening, and retains selected files in `inputs/TXT_files/`. Extraction reads the retained `.txt` files; the accompanying XML preserves source metadata. Use a dedicated temporary directory: completed batch folders are deleted after screening. The first bucket listing and full scan can take substantial time, network traffic and disk space. This command scans the full available bucket; it does not reproduce a fixed historical corpus.

Screening checks text length, article type/review language, primary-research sections, plant vocabulary, non-plant bias and bioengineering vocabulary. It does not use the model. The subsequent extraction stage applies its pre-filter, model eligibility gate and quotation verification, using the existing Qwen configuration.

For parallel independent downloads, use the same `--num-shards` on each worker and a distinct `--shard` index, starting at zero. The command above explicitly selects one shard to cover the entire listing. Optional `--workers` and `--batch-size` control download concurrency and batch size. Keep the cached prefix list, shard configuration, batch size and completion manifests unchanged when resuming. Re-running the command uses these to skip completed batches; use new directories for a fresh scan. Decision reports and completion files are generated during the run and are not published dataset statistics.

If articles have already been downloaded in nested `PMC<id>.<version>/` directories, screen them locally instead:

```bash
python -m plant_bioeng_filter --pmc-root /path/to/pmc/text --output inputs/TXT_files
```

After download/screening finishes, start the model server and run extraction as described below. These are separate commands; the downloader does not launch the model or extractor automatically.

## Start the supplied model locally (Linux GPU)

The optional setup script creates an environment and downloads the model at revision `0499c3ac83fdef8810b907a23894ba91e95eddd8`:

```bash
export PBA_PROJECT_ROOT=/absolute/path/to/runtime
bash environment/setup_extraction_env.sh
source "$PBA_PROJECT_ROOT/PMC_extraction/venv_pmc/bin/activate"

vllm serve "$PBA_PROJECT_ROOT/PMC_extraction/pmc_extractor/models/Qwen3-32B-AWQ" \
  --served-model-name qwen3-32b \
  --host 127.0.0.1 --port 8000 \
  --tensor-parallel-size 2 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.92 \
  --dtype auto --kv-cache-dtype auto \
  --enable-prefix-caching --reasoning-parser qwen3 --enforce-eager
```

The setup script replaces an existing environment at `$PBA_PROJECT_ROOT/PMC_extraction/venv_pmc`. Choose a dedicated runtime directory. `requirements/extraction.txt` also lists the server dependencies for manual installation; CUDA/PyTorch compatibility must match the host.

## Run extraction

Keep the model server running. From the repository root, activate the client environment, then:

```bash
cd extraction
python -m src.extract --config config/default.yaml --limit 5 -v
```

The default paths are relative to the current working directory: run from `extraction/` as shown. Remove `--limit 5` to process the full input folder. Set `--concurrency 1` for sequential processing, or choose another positive value to override the default concurrency.

To use other locations:

```bash
python -m src.extract --config config/default.yaml \
  --input-dir /absolute/path/to/TXT_files \
  --output-tsv /absolute/path/to/output/records.tsv \
  --log-file /absolute/path/to/output/run.jsonl -v
```

## Outputs and resuming

With the default configuration, outputs are written to `outputs/` at the repository root:

- `plant_bioeng_table.tsv`: accepted records with plant species, genes, modification type, engineering type, gene construct, phenotype, mechanism, DOI and PMCID.
- `plant_bioeng_table.tsv.evidence.jsonl`: evidence quotations and check outcomes.
- `plant_bioeng_table.tsv.progress`: completed PMCIDs used for resume.
- `extraction_run.jsonl`: structured run and article events.

Run the same command with the same output paths to resume; completed PMCIDs are skipped. Existing outputs are appended to. For a fresh run, choose new TSV and log paths so that the evidence and progress files are also new. Changing settings while reusing the progress file does not reprocess completed articles. Keep outputs together. Article quotations remain subject to their source licenses.

## Optional SLURM execution

Edit partition, account, GPU and memory requests in `extraction/hpc/run_extraction.sbatch` for your cluster. This job uses a separate runtime layout: input articles at `$PBA_PROJECT_ROOT/plant_bioengineering/TXT_files`, and environment, model and outputs under `$PBA_PROJECT_ROOT/PMC_extraction`. Edit the script's paths if your layout differs. From the repository root:

```bash
export PBA_PROJECT_ROOT=/absolute/path/to/runtime
cd extraction
sbatch hpc/run_extraction.sbatch
```

The job starts the model server and extractor, writes scheduler `.out`/`.err` files in the submission directory and model/runtime logs in `PMC_extraction`, and can resubmit itself after timeout or a long-running failure. It resumes using the progress file.

## Optional analyses

Install `requirements/analysis.txt` separately to use the retained analyses. These are optional and are not part of downloading, screening or extraction.

The atlas builder and annotation caches are not included. Analyses that need them require externally supplied inputs: `PBA_PORTAL_HTML` identifies an existing portal export and `PBA_ATLAS` identifies an external annotation directory. `PBA_INPUTS` identifies the input directory; `PBA_RESULTS`, `PBA_OUTPUTS` and `PBA_FIGURES` select analysis output locations. Existing annotated exports can be placed under `PBA_RESULTS` as expected by the scripts. The release tables alone do not replace every annotation or source input.

Time-split analysis supports a cutoff year and evaluates all available later years. Predictions must be regenerated with the current script before evaluation; outputs from a different script version are rejected.

The release record table contains extracted fields and derived annotations. The export script preserves that schema. Source text, decision tables and other external inputs must be supplied for analyses that read them. Analysis results and totals are computed from those inputs when scripts run.

## License and citation

Code is MIT licensed; see `LICENSE`. Citation metadata is in `CITATION.cff`. Generated scientific results depend on the supplied corpus, model, configuration and any subsequent curation.
