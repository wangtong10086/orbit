"""Training configuration."""

from dataclasses import dataclass, field


@dataclass
class TrainConfig:
    """Configuration for SFT training runs."""

    # Model
    model_name: str = "Qwen/Qwen3-32B"
    max_seq_length: int = 4096

    # Training hyperparams
    per_device_train_batch_size: int = 2
    gradient_accumulation_steps: int = 8
    num_train_epochs: int = 1
    learning_rate: float = 1e-4
    warmup_ratio: float = 0.03
    weight_decay: float = 0.01
    max_grad_norm: float = 0.3
    bf16: bool = True
    packing: bool = True

    # LoRA / QLoRA
    use_qlora: bool = True
    lora_r: int = 64
    lora_alpha: int = 128
    lora_dropout: float = 0.05
    lora_target_modules: str = "q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj"

    # Saving
    save_steps: int = 100
    save_total_limit: int = 3
    logging_steps: int = 10
    output_dir: str = "/root/checkpoints"

    # Backup
    backup_interval_minutes: int = 15
    hf_backup_repo: str = ""

    def to_train_script(self, dataset_path: str) -> str:
        """Generate the complete training Python script.

        Includes:
        - QLoRA 4-bit training with LoRA
        - HuggingFace auto-upload callback (every checkpoint save)
        - Robust error handling for Targon instability
        """
        return f'''#!/usr/bin/env python3
"""Auto-generated SFT training script with HF auto-backup."""
import os
import sys
import json
import time
import subprocess
import torch
import traceback
from datasets import load_dataset
from transformers import (
    AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig,
    TrainerCallback,
)
from trl import SFTTrainer, SFTConfig
from peft import LoraConfig

# Status file for HTTP monitoring (written to health server directory)
STATUS_FILE = "/tmp/health/status.json"

def write_status(phase, **kwargs):
    """Write training status to health server directory for HTTP monitoring."""
    status = {{"phase": phase, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **kwargs}}
    try:
        with open(STATUS_FILE, "w") as f:
            json.dump(status, f)
    except Exception:
        pass

write_status("init", msg="Training script started")

# Reduce CUDA memory fragmentation
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

# Multi-GPU: detect number of GPUs
NUM_GPUS = torch.cuda.device_count()
IS_DISTRIBUTED = int(os.environ.get("WORLD_SIZE", "1")) > 1
LOCAL_RANK = int(os.environ.get("LOCAL_RANK", "0"))
IS_MAIN = LOCAL_RANK == 0

MODEL_NAME = "{self.model_name}"
DATASET_PATH = "{dataset_path}"
OUTPUT_DIR = "{self.output_dir}"
MAX_SEQ_LEN = {self.max_seq_length}
HF_REPO = os.getenv("HF_BACKUP_REPO", "{self.hf_backup_repo}")
HF_TOKEN = os.getenv("HF_TOKEN", "")

def _subprocess_hf_upload(task_json_path):
    """Run HF upload in isolated subprocess via JSON task file.
    Avoids state corruption from long-running training process."""
    try:
        result = subprocess.run(
            [sys.executable, "-c", _HF_UPLOAD_WORKER_CODE, task_json_path],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            print(f"[HF] Subprocess failed: {{result.stderr[-500:]}}")
        elif result.stdout.strip():
            print(result.stdout.strip())
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("[HF] Upload subprocess timed out (300s)")
        return False
    except Exception as e:
        print(f"[HF] Subprocess error: {{e}}")
        return False

# Worker code run in isolated subprocess — reads JSON task file
_HF_UPLOAD_WORKER_CODE = """
import sys, json, os, time, tempfile
task = json.load(open(sys.argv[1]))
from huggingface_hub import HfApi
api = HfApi(token=task["token"])
repo = task["repo_id"]
action = task["action"]

if action == "checkpoint":
    api.upload_folder(
        folder_path=task["folder"], repo_id=repo,
        path_in_repo=task["path_in_repo"], repo_type="model",
    )
    status = task["status"]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(status, f, indent=2)
        tmp = f.name
    api.upload_file(path_or_fileobj=tmp, path_in_repo="training_status.json",
                    repo_id=repo, repo_type="model")
    os.unlink(tmp)
    print(f"[HF Backup] {{task['path_in_repo']}} uploaded")

elif action == "log":
    log_path = task.get("log_path")
    if log_path and os.path.exists(log_path):
        api.upload_file(path_or_fileobj=log_path, path_in_repo="training.log",
                        repo_id=repo, repo_type="model")
    log_json = task.get("log_json_path")
    if log_json and os.path.exists(log_json):
        api.upload_file(path_or_fileobj=log_json, path_in_repo="training_log.json",
                        repo_id=repo, repo_type="model")
    print(f"[Log Upload] step {{task.get('step', '?')}} uploaded")

elif action == "folder":
    api.upload_folder(folder_path=task["folder"], repo_id=repo, repo_type="model")
    if "status" in task:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(task["status"], f, indent=2)
            tmp = f.name
        api.upload_file(path_or_fileobj=tmp, path_in_repo="training_status.json",
                        repo_id=repo, repo_type="model")
        os.unlink(tmp)
    print(f"[HF] Folder upload complete")
"""

def _write_task_and_upload(task):
    """Write task JSON and run subprocess upload."""
    import tempfile as _tf
    with _tf.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(task, f)
        task_path = f.name
    try:
        return _subprocess_hf_upload(task_path)
    finally:
        try:
            os.unlink(task_path)
        except OSError:
            pass

# === HuggingFace Auto-Upload Callback (subprocess-isolated) ===
class HFUploadCallback(TrainerCallback):
    """Upload checkpoints to HuggingFace via isolated subprocess on each save."""

    def __init__(self, repo_id, token):
        self.repo_id = repo_id
        self.token = token

    def on_save(self, args, state, control, **kwargs):
        step = state.global_step
        checkpoint_dir = os.path.join(args.output_dir, f"checkpoint-{{step}}")
        if not os.path.isdir(checkpoint_dir):
            return
        print(f"[HF Backup] Uploading checkpoint-{{step}} via subprocess...")
        _write_task_and_upload({{
            "action": "checkpoint",
            "token": self.token,
            "repo_id": self.repo_id,
            "folder": checkpoint_dir,
            "path_in_repo": f"checkpoint-{{step}}",
            "status": {{
                "global_step": step,
                "epoch": state.epoch,
                "loss": state.log_history[-1].get("loss") if state.log_history else None,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "model": MODEL_NAME,
                "dataset": DATASET_PATH,
            }},
        }})

    def on_train_end(self, args, state, control, **kwargs):
        self.on_save(args, state, control, **kwargs)


class LogUploadCallback(TrainerCallback):
    """Periodically upload training logs to HuggingFace via subprocess."""

    def __init__(self, repo_id, token, log_path="/root/training.log", upload_every_n_logs=5):
        self.repo_id = repo_id
        self.token = token
        self.log_path = log_path
        self.upload_every = upload_every_n_logs
        self.log_count = 0

    def on_log(self, args, state, control, logs=None, **kwargs):
        # Always update local status file for HTTP monitoring
        loss = logs.get("loss") if logs else None
        write_status("training", step=state.global_step, epoch=state.epoch, loss=loss)
        self.log_count += 1
        if self.log_count % self.upload_every != 0:
            return
        self._upload(state, logs)

    def on_train_end(self, args, state, control, **kwargs):
        self._upload(state, {{}})

    def _upload(self, state, logs):
        log_json_path = "/tmp/hf_training_log.json"
        log_data = {{
            "global_step": state.global_step,
            "epoch": state.epoch,
            "log_history": state.log_history[-20:] if state.log_history else [],
            "current_logs": logs or {{}},
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        }}
        with open(log_json_path, "w") as f:
            json.dump(log_data, f, indent=2)

        _write_task_and_upload({{
            "action": "log",
            "token": self.token,
            "repo_id": self.repo_id,
            "log_path": self.log_path,
            "log_json_path": log_json_path,
            "step": state.global_step,
        }})

# === Main Training ===
if IS_MAIN:
    print(f"=== Affine Forge Training ===")
    print(f"Model: {{MODEL_NAME}}")
    print(f"Dataset: {{DATASET_PATH}}")
    print(f"Output: {{OUTPUT_DIR}}")
    print(f"HF Backup: {{HF_REPO}}")
    print(f"GPUs: {{NUM_GPUS}}, Distributed: {{IS_DISTRIBUTED}}")
    print()

try:
    # Load model
    write_status("loading_tokenizer")
    print("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    write_status("loading_model", msg="Downloading model (pre-quantized ~18GB)")
    print("Loading model...")

    # Multi-GPU DDP: each process loads model on its own GPU
    if IS_DISTRIBUTED:
        device_map = {{"": LOCAL_RANK}}
        if IS_MAIN:
            print(f"Multi-GPU DDP: {{NUM_GPUS}} GPUs, local_rank={{LOCAL_RANK}}")
    else:
        device_map = "auto"

    # Use pre-quantized 4-bit model (smaller download, no runtime quantization)
    PRE_QUANT = "unsloth/Qwen3-32B-bnb-4bit"
    print(f"Using pre-quantized model: {{PRE_QUANT}}")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        PRE_QUANT,
        quantization_config=bnb_config,
        device_map=device_map,
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )
    if IS_MAIN:
        print(f"Model loaded. GPUs: {{NUM_GPUS}}, device_map: {{device_map}}")
    write_status("model_loaded", gpus=NUM_GPUS)

    # Load dataset
    print(f"Loading dataset...")
    if DATASET_PATH.endswith(".jsonl"):
        dataset = load_dataset("json", data_files=DATASET_PATH, split="train")
    else:
        dataset = load_dataset(DATASET_PATH, split="train")
    print(f"Dataset: {{len(dataset)}} samples")

    # LoRA config
    peft_config = LoraConfig(
        r={self.lora_r},
        lora_alpha={self.lora_alpha},
        lora_dropout={self.lora_dropout},
        target_modules={self.lora_target_modules.split(",")},
        bias="none",
        task_type="CAUSAL_LM",
    )

    # Clear VRAM before training
    torch.cuda.empty_cache()
    import gc; gc.collect()

    # Training parameters
    training_args = SFTConfig(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size={self.per_device_train_batch_size},
        gradient_accumulation_steps={self.gradient_accumulation_steps},
        num_train_epochs={self.num_train_epochs},
        learning_rate={self.learning_rate},
        warmup_steps=int({self.warmup_ratio} * (len(dataset) // ({self.per_device_train_batch_size} * {self.gradient_accumulation_steps}))),
        weight_decay={self.weight_decay},
        max_grad_norm={self.max_grad_norm},
        bf16={self.bf16},
        logging_steps={self.logging_steps},
        save_steps={self.save_steps},
        save_total_limit={self.save_total_limit},
        max_length=MAX_SEQ_LEN,
        packing={self.packing},
        report_to="none",
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={{"use_reentrant": False}},
    )

    # Callbacks
    callbacks = []
    if HF_REPO and HF_TOKEN:
        callbacks.append(HFUploadCallback(HF_REPO, HF_TOKEN))
        callbacks.append(LogUploadCallback(HF_REPO, HF_TOKEN, upload_every_n_logs=5))
        print(f"HF auto-backup enabled (subprocess): every checkpoint -> {{HF_REPO}}")
        print(f"Log upload enabled: every 5 logging steps -> {{HF_REPO}}/training_log.json")

    # Training
    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        peft_config=peft_config,
        args=training_args,
        processing_class=tokenizer,
        callbacks=callbacks,
    )

    # === Checkpoint Resume: download latest from HF if available ===
    resume_checkpoint = None
    if HF_REPO and HF_TOKEN:
        write_status("checking_resume", msg="Looking for existing checkpoints on HF")
        print("Checking HF for existing checkpoints to resume from...")
        try:
            from huggingface_hub import HfApi as _HfApi, snapshot_download as _snap_dl
            _api = _HfApi(token=HF_TOKEN)
            _files = list(_api.list_repo_tree(HF_REPO, repo_type="model"))
            # Find checkpoint-* directories
            _ckpt_names = set()
            for f in _files:
                if f.path.startswith("checkpoint-") and "/" not in f.path:
                    _ckpt_names.add(f.path)
                elif "/" in f.path and f.path.split("/")[0].startswith("checkpoint-"):
                    _ckpt_names.add(f.path.split("/")[0])
            _ckpts = sorted(_ckpt_names, key=lambda p: int(p.split("-")[-1]))
            if _ckpts:
                _latest = _ckpts[-1]
                _step = int(_latest.split("-")[-1])
                print(f"Found {{len(_ckpts)}} checkpoint(s) on HF, latest: {{_latest}} (step {{_step}})")
                # Download checkpoint dir using snapshot_download
                _dl_dir = _snap_dl(
                    HF_REPO, repo_type="model", token=HF_TOKEN,
                    allow_patterns=f"{{_latest}}/*",
                    local_dir="/tmp/hf_resume",
                )
                # snapshot_download preserves directory structure
                _ckpt_src = os.path.join(_dl_dir, _latest)
                _ckpt_dst = os.path.join(OUTPUT_DIR, _latest)
                if os.path.isdir(_ckpt_src):
                    import shutil
                    if os.path.exists(_ckpt_dst):
                        shutil.rmtree(_ckpt_dst)
                    shutil.copytree(_ckpt_src, _ckpt_dst)
                    # Verify key files exist
                    _required = ["trainer_state.json", "optimizer.pt", "scheduler.pt"]
                    _missing = [r for r in _required if not os.path.exists(os.path.join(_ckpt_dst, r))]
                    if _missing:
                        print(f"WARNING: Missing files in checkpoint: {{_missing}}, starting fresh")
                    else:
                        resume_checkpoint = _ckpt_dst
                        print(f"Checkpoint downloaded to {{_ckpt_dst}}, will resume from step {{_step}}")
                        for _f in os.listdir(_ckpt_dst):
                            _sz = os.path.getsize(os.path.join(_ckpt_dst, _f))
                            print(f"  {{_f}}: {{_sz/1024/1024:.1f}} MB")
                        write_status("resuming", checkpoint=_latest, step=_step)
                else:
                    print(f"Download dir {{_ckpt_src}} not found, starting fresh")
            else:
                print("No existing checkpoints found, starting fresh")
        except Exception as _e:
            print(f"Checkpoint resume check failed (starting fresh): {{_e}}")
            import traceback; traceback.print_exc()

    write_status("training_starting", samples=len(dataset), resuming=resume_checkpoint is not None)
    if resume_checkpoint:
        print(f"\\n=== Resuming Training from {{resume_checkpoint}} ===")
    else:
        print("\\n=== Starting Training ===")
    start_time = time.time()
    try:
        trainer.train(resume_from_checkpoint=resume_checkpoint)
    except Exception as _resume_err:
        if resume_checkpoint:
            print(f"Resume failed: {{_resume_err}}")
            print("Falling back to fresh training...")
            write_status("resume_failed_fresh_start", error=str(_resume_err))
            trainer.train()
        else:
            raise
    elapsed = time.time() - start_time
    write_status("completed", elapsed_hours=elapsed/3600, total_steps=trainer.state.global_step,
                 final_loss=trainer.state.log_history[-1].get("loss") if trainer.state.log_history else None)
    print(f"\\n=== Training Complete ({{elapsed/3600:.1f}}h) ===")

    # Save final model
    final_dir = os.path.join(OUTPUT_DIR, "final")
    print(f"Saving final model to {{final_dir}}...")
    trainer.save_model(final_dir)
    tokenizer.save_pretrained(final_dir)

    # Final upload (also subprocess-isolated)
    if HF_REPO and HF_TOKEN:
        print(f"Final upload to {{HF_REPO}} via subprocess...")
        _write_task_and_upload({{
            "action": "folder",
            "token": HF_TOKEN,
            "repo_id": HF_REPO,
            "folder": final_dir,
            "status": {{
                "status": "completed",
                "elapsed_hours": elapsed / 3600,
                "total_steps": trainer.state.global_step,
                "final_loss": trainer.state.log_history[-1].get("loss") if trainer.state.log_history else None,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            }},
        }})

    print("\\nDONE.")

except Exception as e:
    write_status("failed", error=str(e))
    print(f"\\n=== TRAINING FAILED ===")
    print(f"Error: {{e}}")
    traceback.print_exc()

    # Emergency upload existing checkpoints (subprocess-isolated)
    if HF_REPO and HF_TOKEN:
        try:
            import glob
            checkpoints = sorted(glob.glob(os.path.join(OUTPUT_DIR, "checkpoint-*")))
            if checkpoints:
                latest = checkpoints[-1]
                print(f"Emergency upload: {{latest}}")
                _write_task_and_upload({{
                    "action": "checkpoint",
                    "token": HF_TOKEN,
                    "repo_id": HF_REPO,
                    "folder": latest,
                    "path_in_repo": "emergency-checkpoint",
                    "status": {{
                        "status": "failed",
                        "error": str(e),
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                    }},
                }})
        except Exception as e2:
            print(f"Emergency upload also failed: {{e2}}")

    sys.exit(1)
'''

    def to_dpo_script(self, dataset_path: str, sft_adapter: str = "") -> str:
        """Generate DPO training script.

        Args:
            dataset_path: Path to DPO JSONL (prompt/chosen/rejected format)
            sft_adapter: HF repo or local path to SFT LoRA adapter to initialize from.
                         If empty, trains DPO from base model.
        """
        load_adapter_block = ""
        if sft_adapter:
            load_adapter_block = f'''
    # Load SFT adapter as starting point
    from peft import PeftModel
    print("Loading SFT adapter: {sft_adapter}")
    model = PeftModel.from_pretrained(model, "{sft_adapter}", is_trainable=True)
    model = model.merge_and_unload()
    print("SFT adapter merged into base model")
'''

        return f'''#!/usr/bin/env python3
"""Auto-generated DPO training script with HF auto-backup."""
import os
import sys
import json
import time
import subprocess
import torch
import traceback
from datasets import load_dataset
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from trl import DPOTrainer, DPOConfig
from peft import LoraConfig

NUM_GPUS = torch.cuda.device_count()
IS_DISTRIBUTED = int(os.environ.get("WORLD_SIZE", "1")) > 1
LOCAL_RANK = int(os.environ.get("LOCAL_RANK", "0"))
IS_MAIN = LOCAL_RANK == 0

MODEL_NAME = "{self.model_name}"
DATASET_PATH = "{dataset_path}"
OUTPUT_DIR = "{self.output_dir}"
HF_REPO = os.getenv("HF_BACKUP_REPO", "{self.hf_backup_repo}")
HF_TOKEN = os.getenv("HF_TOKEN", "")
DPO_BETA = 0.1

def _subprocess_hf_upload(task_json_path):
    try:
        result = subprocess.run(
            [sys.executable, "-c", _HF_UPLOAD_WORKER_CODE, task_json_path],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            print(f"[HF] Subprocess failed: {{result.stderr[-500:]}}")
        elif result.stdout.strip():
            print(result.stdout.strip())
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("[HF] Upload subprocess timed out (300s)")
        return False
    except Exception as e:
        print(f"[HF] Subprocess error: {{e}}")
        return False

_HF_UPLOAD_WORKER_CODE = """
import sys, json, os, time, tempfile
task = json.load(open(sys.argv[1]))
from huggingface_hub import HfApi
api = HfApi(token=task["token"])
repo = task["repo_id"]
action = task["action"]

if action == "checkpoint":
    api.upload_folder(
        folder_path=task["folder"], repo_id=repo,
        path_in_repo=task["path_in_repo"], repo_type="model",
    )
    status = task["status"]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(status, f, indent=2)
        tmp = f.name
    api.upload_file(path_or_fileobj=tmp, path_in_repo="training_status.json",
                    repo_id=repo, repo_type="model")
    os.unlink(tmp)
    print(f"[HF Backup] {{task['path_in_repo']}} uploaded")

elif action == "folder":
    api.upload_folder(folder_path=task["folder"], repo_id=repo, repo_type="model")
    if "status" in task:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(task["status"], f, indent=2)
            tmp = f.name
        api.upload_file(path_or_fileobj=tmp, path_in_repo="training_status.json",
                        repo_id=repo, repo_type="model")
        os.unlink(tmp)
    print(f"[HF] Folder upload complete")
"""

def _write_task_and_upload(task):
    import tempfile as _tf
    with _tf.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(task, f)
        task_path = f.name
    try:
        return _subprocess_hf_upload(task_path)
    finally:
        try:
            os.unlink(task_path)
        except OSError:
            pass

from transformers import TrainerCallback

class HFUploadCallback(TrainerCallback):
    def __init__(self, repo_id, token):
        self.repo_id = repo_id
        self.token = token

    def on_save(self, args, state, control, **kwargs):
        step = state.global_step
        checkpoint_dir = os.path.join(args.output_dir, f"checkpoint-{{step}}")
        if not os.path.isdir(checkpoint_dir):
            return
        print(f"[HF Backup] Uploading checkpoint-{{step}} via subprocess...")
        _write_task_and_upload({{
            "action": "checkpoint",
            "token": self.token,
            "repo_id": self.repo_id,
            "folder": checkpoint_dir,
            "path_in_repo": f"checkpoint-{{step}}",
            "status": {{
                "global_step": step,
                "epoch": state.epoch,
                "loss": state.log_history[-1].get("loss") if state.log_history else None,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "model": MODEL_NAME,
                "dataset": DATASET_PATH,
                "method": "DPO",
                "beta": DPO_BETA,
            }},
        }})

    def on_train_end(self, args, state, control, **kwargs):
        self.on_save(args, state, control, **kwargs)


if IS_MAIN:
    print(f"=== Affine Forge DPO Training ===")
    print(f"Model: {{MODEL_NAME}}")
    print(f"Dataset: {{DATASET_PATH}}")
    print(f"Output: {{OUTPUT_DIR}}")
    print(f"HF Backup: {{HF_REPO}}")
    print(f"Beta: {{DPO_BETA}}")
    print(f"GPUs: {{NUM_GPUS}}, Distributed: {{IS_DISTRIBUTED}}")
    print()

try:
    print("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print("Loading model with QLoRA (4-bit)...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    if IS_DISTRIBUTED:
        device_map = {{"": LOCAL_RANK}}
    else:
        device_map = "auto"

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        quantization_config=bnb_config,
        device_map=device_map,
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )
{load_adapter_block}
    if IS_MAIN:
        print(f"Model loaded. GPUs: {{NUM_GPUS}}, device_map: {{device_map}}")

    # Load DPO dataset
    print(f"Loading DPO dataset...")
    dataset = load_dataset("json", data_files=DATASET_PATH, split="train")
    print(f"Dataset: {{len(dataset)}} preference pairs")

    # LoRA config
    peft_config = LoraConfig(
        r={self.lora_r},
        lora_alpha={self.lora_alpha},
        lora_dropout={self.lora_dropout},
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        bias="none",
        task_type="CAUSAL_LM",
    )

    # DPO training args
    training_args = DPOConfig(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=1,
        gradient_accumulation_steps={self.gradient_accumulation_steps},
        num_train_epochs={self.num_train_epochs},
        learning_rate=5e-6,
        warmup_ratio=0.1,
        weight_decay={self.weight_decay},
        max_grad_norm={self.max_grad_norm},
        bf16={self.bf16},
        logging_steps={self.logging_steps},
        save_steps={self.save_steps},
        save_total_limit={self.save_total_limit},
        beta=DPO_BETA,
        max_length={self.max_seq_length},
        max_prompt_length={self.max_seq_length // 2},
        report_to="none",
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={{"use_reentrant": False}},
    )

    # Callbacks
    callbacks = []
    if HF_REPO and HF_TOKEN:
        callbacks.append(HFUploadCallback(HF_REPO, HF_TOKEN))
        print(f"HF auto-backup enabled: every checkpoint -> {{HF_REPO}}")

    # Train
    trainer = DPOTrainer(
        model=model,
        train_dataset=dataset,
        peft_config=peft_config,
        args=training_args,
        processing_class=tokenizer,
        callbacks=callbacks,
    )

    print("\\n=== Starting DPO Training ===")
    start_time = time.time()
    trainer.train()
    elapsed = time.time() - start_time
    print(f"\\n=== DPO Training Complete ({{elapsed/3600:.1f}}h) ===")

    # Save final model
    final_dir = os.path.join(OUTPUT_DIR, "final")
    print(f"Saving final model to {{final_dir}}...")
    trainer.save_model(final_dir)
    tokenizer.save_pretrained(final_dir)

    if HF_REPO and HF_TOKEN:
        print(f"Final upload to {{HF_REPO}} via subprocess...")
        _write_task_and_upload({{
            "action": "folder",
            "token": HF_TOKEN,
            "repo_id": HF_REPO,
            "folder": final_dir,
            "status": {{
                "status": "completed",
                "method": "DPO",
                "elapsed_hours": elapsed / 3600,
                "total_steps": trainer.state.global_step,
                "final_loss": trainer.state.log_history[-1].get("loss") if trainer.state.log_history else None,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            }},
        }})

    print("\\nDONE.")

except Exception as e:
    print(f"\\n=== DPO TRAINING FAILED ===")
    print(f"Error: {{e}}")
    traceback.print_exc()

    if HF_REPO and HF_TOKEN:
        try:
            import glob
            checkpoints = sorted(glob.glob(os.path.join(OUTPUT_DIR, "checkpoint-*")))
            if checkpoints:
                latest = checkpoints[-1]
                print(f"Emergency upload: {{latest}}")
                _write_task_and_upload({{
                    "action": "checkpoint",
                    "token": HF_TOKEN,
                    "repo_id": HF_REPO,
                    "folder": latest,
                    "path_in_repo": "emergency-checkpoint",
                    "status": {{
                        "status": "failed",
                        "method": "DPO",
                        "error": str(e),
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                    }},
                }})
        except Exception as e2:
            print(f"Emergency upload also failed: {{e2}}")

    sys.exit(1)
'''
