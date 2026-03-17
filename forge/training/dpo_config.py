"""DPO training script generation."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from forge.training.config import TrainConfig


def generate_dpo_script(config: "TrainConfig", dataset_path: str, sft_adapter: str = "") -> str:
    """Generate DPO training script.

    Args:
        config: TrainConfig instance with hyperparameters.
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

MODEL_NAME = "{config.model_name}"
DATASET_PATH = "{dataset_path}"
OUTPUT_DIR = "{config.output_dir}"
HF_REPO = os.getenv("HF_BACKUP_REPO", "{config.hf_backup_repo}")
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
        r={config.lora_r},
        lora_alpha={config.lora_alpha},
        lora_dropout={config.lora_dropout},
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        bias="none",
        task_type="CAUSAL_LM",
    )

    # DPO training args
    training_args = DPOConfig(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=1,
        gradient_accumulation_steps={config.gradient_accumulation_steps},
        num_train_epochs={config.num_train_epochs},
        learning_rate=5e-6,
        warmup_ratio=0.1,
        weight_decay={config.weight_decay},
        max_grad_norm={config.max_grad_norm},
        bf16={config.bf16},
        logging_steps={config.logging_steps},
        save_steps={config.save_steps},
        save_total_limit={config.save_total_limit},
        beta=DPO_BETA,
        max_length={config.max_seq_length},
        max_prompt_length={config.max_seq_length // 2},
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
