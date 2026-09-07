# Mode R — Recorded Accessible Hardware

Mode R adds physical GPU measurements without pretending that locally recorded traces are hardware-rooted attestation or evidence about GPU classes that were not measured.

The first target is the builder's accessible RTX 3050. Results produced from it must be labeled `RECORDED_REAL` and must not be generalized to H100/H200/B200 service.

## Boundary

```text
RTX 3050
   |
   v
north-standard-cuda-probe
   |
   | gpu-trace/0.1
   | provenance = RECORDED_REAL
   v
healthy calibration captures
   |
   v
gpu-calibration/0.1
   | device/profile/challenge-bound
   v
later recorded capture
   |
   v
normalized challenge evidence
   |
   v
existing Python/C++ verifier
   |
ACCEPT | REJECT | INCONCLUSIVE
   |
   v
recorded campaign metrics
FAR | FRR | IR + Wilson intervals
```

The collector uses only the CUDA runtime in v0.1. It records two deliberately simple microbenchmark primitives:

- repeated per-element FMA work, reported as estimated GFLOP/s;
- a device-memory copy kernel, reported as GB/s.

These are **research probes**, not a standardized GPU benchmark suite.

## Build the optional CUDA probe

The default project build remains CUDA-free so ordinary CI and non-GPU contributors are unaffected.

```bash
cmake -S . -B build-cuda \
  -DNORTH_STANDARD_BUILD_CUDA_PROBE=ON \
  -DBUILD_TESTING=OFF
cmake --build build-cuda --parallel
```

On Windows with a Visual Studio generator, the executable will normally appear under the selected configuration directory, for example `build-cuda/cuda/Release/north-standard-cuda-probe.exe` when building Release.

If `nvcc` is not discoverable, install/configure a CUDA Toolkit first. Having an NVIDIA driver alone is not sufficient to compile the probe.

## Capture a healthy baseline

Start with multiple healthy captures instead of calibrating from one lucky run. Keep the benchmark parameters identical.

Single capture example:

```bash
./build-cuda/cuda/north-standard-cuda-probe \
  --contract-id rtx3050-local-001 \
  --session-id healthy-baseline-001 \
  --capture-id healthy-01 \
  --iterations 12 \
  --output experiments/recorded_traces/healthy-01.json
```

### Windows helper

The repository includes `scripts/capture_recorded.ps1` so a condition can be captured repeatedly without manually creating IDs and filenames.

```powershell
.\scripts\capture_recorded.ps1 `
  -ProbePath .\build-cuda\cuda\Release\north-standard-cuda-probe.exe `
  -OutputDir .\experiments\recorded_traces `
  -Condition healthy_idle `
  -GroundTruth COMPLIANT `
  -Count 5
```

The helper does **not** create load, throttling, thermal stress, or any other condition. It only records the GPU while you place the machine in the intended experiment state. It also emits a campaign-fragment JSON file; that fragment is experiment metadata, never verifier input.

Build the calibration from the healthy captures:

```bash
python experiments/calibrate_recorded.py \
  experiments/recorded_traces/healthy-01.json \
  experiments/recorded_traces/healthy-02.json \
  experiments/recorded_traces/healthy-03.json \
  --calibration-id rtx3050-local-healthy-v0.1 \
  --output experiments/recorded_traces/rtx3050-calibration.json
```

The reference compute and memory values are medians across the explicitly designated healthy captures. The calibration is also bound to:

- device fingerprint;
- CUDA runtime profile;
- benchmark profile;
- challenge element count;
- FMA inner-iteration count;
- warmup count.

A later trace with a different bound challenge shape is rejected before replay.

## Record evaluation conditions

Useful conditions include:

- normal/idle system;
- sustained GPU load/contention;
- naturally occurring thermal or power-limited behavior under legitimate local settings;
- GPU memory pressure;
- host CPU pressure.

Do not damage hardware, disable safety limits, or use unsafe overclock/undervolt settings for the experiment.

The CUDA probe itself does not claim the cause of a slowdown. Ground-truth condition labels belong in the campaign manifest/logbook, outside verifier input.

## Replay one capture through the verifier

```bash
python experiments/replay_recorded.py \
  experiments/recorded_traces/eval-01.json \
  --calibration experiments/recorded_traces/rtx3050-calibration.json \
  --performance-floor 0.80 \
  --output experiments/results/recorded/eval-01-result.json
```

The current research score is:

```text
compute_ratio = observed_compute_gflops / calibration_compute_gflops
memory_ratio  = observed_memory_gbps  / calibration_memory_gbps
score         = min(compute_ratio, memory_ratio)
```

Using the minimum makes the score bottleneck-sensitive. This exact aggregation is experiment-defined and should be treated as an ablation candidate, not as production truth.

## Run a recorded-hardware campaign

Copy `experiments/recorded_campaign.example.json` and replace the example paths with actual trace files. The manifest keeps two things outside the verifier:

- `condition`;
- `ground_truth` (`COMPLIANT` or `BREACH`).

Then run:

```bash
python experiments/run_recorded_campaign.py \
  --manifest experiments/recorded_campaign.json \
  --output-dir experiments/results/recorded/rtx3050-v0.1
```

The campaign writes:

```text
recorded_trials.jsonl
recorded_summary.json
```

The summary reports FAR, FRR, overall/conditioned INCONCLUSIVE rates, and 95% Wilson confidence intervals. It remains explicitly `publication_ready: false` until the campaign is large enough, conditions are documented, and limitations are reviewed.

## Trust and provenance

Mode R v0.1 deliberately says less than production attestation:

- trace provenance: `RECORDED_REAL`;
- collector authentication: `LOCAL_SOFTWARE_ONLY`;
- generated evidence trust tier: `T0`;
- session binding method: `LOCAL_CAPTURE_ARGUMENTS`;
- no claim of hardware-rooted identity;
- no claim of remote-provider non-substitution;
- no claim that RTX 3050 distributions represent H100-class hardware.

The value of Mode R is that the *same verifier and settlement boundary* can consume physical performance observations after synthetic adversarial development, while the evidence's weaker trust assumptions remain visible.
