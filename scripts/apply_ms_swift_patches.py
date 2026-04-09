#!/usr/bin/env python3
"""Apply ORBIT-maintained patches to an installed ms-swift package."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def _swift_root(explicit_root: str | None) -> Path:
    if explicit_root:
        root = Path(explicit_root).expanduser().resolve()
        if not root.exists():
            raise SystemExit(f"ms-swift path not found: {root}")
        return root
    spec = importlib.util.find_spec("swift")
    if spec is None or spec.origin is None:
        raise SystemExit("Could not locate installed ms-swift package")
    return Path(spec.origin).resolve().parent


def _replace_once(text: str, old: str, new: str, *, path: Path) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f"Patch anchor not found in {path}: {old[:120]!r}")
    return text.replace(old, new, 1)


def _patch_sampling_args(text: str, path: Path) -> str:
    text = _replace_once(
        text,
        "from swift.utils import get_logger\nfrom .base_args import BaseArguments\n",
        "from swift.utils import get_logger\n"
        "from orbit.integrations.ms_swift_offline_topk import (\n"
        "    DEFAULT_TEACHER_RESPONSE_TOKEN_IDS_FIELD,\n"
        "    DEFAULT_TEACHER_TOPK_INDICES_FIELD,\n"
        "    DEFAULT_TEACHER_TOPK_LOGPROBS_FIELD,\n"
        "    DEFAULT_TEACHER_TOPK_STORAGE_DTYPE,\n"
        "    normalize_teacher_topk_storage_dtype,\n"
        ")\n"
        "from .base_args import BaseArguments\n",
        path=path,
    )
    text = _replace_once(
        text,
        "        sampler_type (Literal['sample', 'distill']): The type of sampling to perform. Supported types are 'sample' and\n"
        "            'distill'. Defaults to 'sample'.\n",
        "        sampler_type (Literal['sample', 'distill', 'gkd_topk']): The type of sampling to perform. Supported\n"
        "            types are 'sample', 'distill', and 'gkd_topk'. Defaults to 'sample'.\n",
        path=path,
    )
    text = _replace_once(
        text,
        "    sampler_type: Literal['sample', 'distill'] = 'sample'\n",
        "    sampler_type: Literal['sample', 'distill', 'gkd_topk'] = 'sample'\n",
        path=path,
    )
    text = _replace_once(
        text,
        "    # Vanilla\n    cache_files: List[str] = dataclasses.field(default_factory=list)\n",
        "    # Vanilla\n"
        "    cache_files: List[str] = dataclasses.field(default_factory=list)\n"
        "\n"
        "    # Offline GKD top-k sampling\n"
        "    teacher_model: Optional[str] = None\n"
        "    teacher_model_type: Optional[str] = None\n"
        "    teacher_model_revision: Optional[str] = None\n"
        "    teacher_model_server: Optional[str] = None\n"
        "    gkd_logits_topk: Optional[int] = None\n"
        "    write_batch_size: int = 1\n"
        "    teacher_topk_indices_field: str = DEFAULT_TEACHER_TOPK_INDICES_FIELD\n"
        "    teacher_topk_logprobs_field: str = DEFAULT_TEACHER_TOPK_LOGPROBS_FIELD\n"
        "    teacher_response_token_ids_field: str = DEFAULT_TEACHER_RESPONSE_TOKEN_IDS_FIELD\n"
        "    teacher_topk_storage_dtype: str = DEFAULT_TEACHER_TOPK_STORAGE_DTYPE\n",
        path=path,
    )
    text = _replace_once(
        text,
        "        else:\n            self.engine_kwargs = {}\n\n        super().__post_init__()\n",
        "        else:\n            self.engine_kwargs = {}\n"
        "        self.teacher_topk_storage_dtype = normalize_teacher_topk_storage_dtype(self.teacher_topk_storage_dtype)\n"
        "        if self.sampler_type == 'gkd_topk':\n"
        "            has_teacher_model = bool(self.teacher_model)\n"
        "            has_teacher_server = bool(self.teacher_model_server)\n"
        "            if has_teacher_model == has_teacher_server:\n"
        "                raise ValueError('gkd_topk sampler requires exactly one of teacher_model or teacher_model_server')\n"
        "            if self.gkd_logits_topk is None or self.gkd_logits_topk <= 0:\n"
        "                raise ValueError('gkd_topk sampler requires a positive gkd_logits_topk')\n"
        "            if self.write_batch_size > 0 and self.num_sampling_batch_size == 1:\n"
        "                self.num_sampling_batch_size = self.write_batch_size\n"
        "\n"
        "        super().__post_init__()\n",
        path=path,
    )
    return text


def _patch_sampling(text: str, path: Path) -> str:
    text = _replace_once(
        text,
        "from .distill_sampler import DistillSampler\nfrom .vanilla_sampler import VanillaSampler\n",
        "from .distill_sampler import DistillSampler\nfrom .gkd_topk_sampler import GKDTopkSampler\nfrom .vanilla_sampler import VanillaSampler\n",
        path=path,
    )
    text = _replace_once(
        text,
        "        if self.args.sampler_type == 'sample':\n"
        "            self.sampler = VanillaSampler(self.args)\n"
        "        elif self.args.sampler_type == 'distill':\n"
        "            self.sampler = DistillSampler(self.args)\n"
        "        else:\n"
        "            raise ValueError(f'Unsupported sampler type: {self.args.sampler_type}')\n",
        "        if self.args.sampler_type == 'sample':\n"
        "            self.sampler = VanillaSampler(self.args)\n"
        "        elif self.args.sampler_type == 'distill':\n"
        "            self.sampler = DistillSampler(self.args)\n"
        "        elif self.args.sampler_type == 'gkd_topk':\n"
        "            self.sampler = GKDTopkSampler(self.args)\n"
        "        else:\n"
        "            raise ValueError(f'Unsupported sampler type: {self.args.sampler_type}')\n",
        path=path,
    )
    return text


def _patch_rlhf_args(text: str, path: Path) -> str:
    text = _replace_once(
        text,
        "from swift.utils import get_current_device, get_logger, is_master, is_mp, json_parse_to_dict, set_default_ddp_config\nfrom .sft_args import SftArguments\n",
        "from swift.utils import get_current_device, get_logger, is_master, is_mp, json_parse_to_dict, set_default_ddp_config\n"
        "from orbit.integrations.ms_swift_offline_topk import (\n"
        "    DEFAULT_TEACHER_DATA_MODE,\n"
        "    DEFAULT_TEACHER_RESPONSE_TOKEN_IDS_FIELD,\n"
        "    DEFAULT_TEACHER_TOPK_INDICES_FIELD,\n"
        "    DEFAULT_TEACHER_TOPK_LOGPROBS_FIELD,\n"
        "    DEFAULT_TEACHER_TOPK_STORAGE_DTYPE,\n"
        "    validate_gkd_teacher_mode,\n"
        ")\n"
        "from .sft_args import SftArguments\n",
        path=path,
    )
    text = _replace_once(
        text,
        "    teacher_model_server: Optional[str] = field(\n"
        "        default=None,\n"
        "        metadata={\n"
        "            'help':\n"
        "            'URL of the teacher model server (e.g., http://localhost:8000). '\n"
        "            'When set, teacher logprobs are fetched via API instead of loading a local model.'\n"
        "        })\n",
        "    teacher_model_server: Optional[str] = field(\n"
        "        default=None,\n"
        "        metadata={\n"
        "            'help':\n"
        "            'URL of the teacher model server (e.g., http://localhost:8000). '\n"
        "            'When set, teacher logprobs are fetched via API instead of loading a local model.'\n"
        "        })\n"
        "    teacher_data_mode: Literal['auto', 'local_model', 'teacher_model_server', 'offline_topk'] = DEFAULT_TEACHER_DATA_MODE\n"
        "    teacher_topk_indices_field: str = DEFAULT_TEACHER_TOPK_INDICES_FIELD\n"
        "    teacher_topk_logprobs_field: str = DEFAULT_TEACHER_TOPK_LOGPROBS_FIELD\n"
        "    teacher_response_token_ids_field: str = DEFAULT_TEACHER_RESPONSE_TOKEN_IDS_FIELD\n"
        "    teacher_topk_storage_dtype: Literal['auto', 'float32', 'bfloat16'] = DEFAULT_TEACHER_TOPK_STORAGE_DTYPE\n",
        path=path,
    )
    text = _replace_once(
        text,
        "        # Validate teacher model configuration\n"
        "        if self.teacher_model is None and self.teacher_model_server is None:\n"
        "            raise ValueError('GKD requires either `teacher_model` or `teacher_model_server` to be set.')\n"
        "\n"
        "        if self.teacher_model is not None and self.teacher_model_server is not None:\n"
        "            raise ValueError('GKD requires either `teacher_model` or `teacher_model_server` to be set, not both.')\n"
        "\n"
        "        # When using teacher_model_server, gkd_logits_topk is required (API only returns top-k logprobs)\n"
        "        if self.teacher_model_server is not None:\n"
        "            if self.gkd_logits_topk is None:\n"
        "                raise ValueError('gkd_logits_topk is required when using teacher_model_server')\n"
        "\n"
        "        # Validate gkd_logits_topk\n"
        "        if self.gkd_logits_topk is not None and self.gkd_logits_topk <= 0:\n"
        "            raise ValueError(f'gkd_logits_topk must be a positive integer, got {self.gkd_logits_topk}')\n"
        "\n"
        "        if self.gkd_logits_topk is not None and self.use_liger_kernel:\n"
        "            raise ValueError('gkd_logits_topk is not supported when using liger kernel')\n"
        "\n"
        "        if self.teacher_model_server and self.seq_kd:\n"
        "            raise NotImplementedError('Sequential KD is not supported when using teacher_model_server')\n",
        "        validate_gkd_teacher_mode(\n"
        "            teacher_data_mode=self.teacher_data_mode,\n"
        "            teacher_model=self.teacher_model,\n"
        "            teacher_model_server=self.teacher_model_server,\n"
        "            gkd_logits_topk=self.gkd_logits_topk,\n"
        "            seq_kd=self.seq_kd,\n"
        "            use_liger_kernel=self.use_liger_kernel,\n"
        "        )\n",
        path=path,
    )
    return text


def _patch_train_rlhf(text: str, path: Path) -> str:
    text = _replace_once(
        text,
        "        if self.args.rlhf_type == 'gkd':\n"
        "            if self.args.teacher_deepspeed:\n"
        "                trainer_kwargs['teacher_deepspeed_config'] = self.args.teacher_deepspeed\n"
        "            trainer_kwargs['gkd_logits_topk'] = self.args.gkd_logits_topk\n"
        "            if self.args.teacher_model_server:\n"
        "                trainer_kwargs['teacher_model_server'] = self.args.teacher_model_server\n",
        "        if self.args.rlhf_type == 'gkd':\n"
        "            if self.args.teacher_deepspeed:\n"
        "                trainer_kwargs['teacher_deepspeed_config'] = self.args.teacher_deepspeed\n"
        "            trainer_kwargs['gkd_logits_topk'] = self.args.gkd_logits_topk\n"
        "            trainer_kwargs['teacher_data_mode'] = self.args.teacher_data_mode\n"
        "            trainer_kwargs['teacher_topk_indices_field'] = self.args.teacher_topk_indices_field\n"
        "            trainer_kwargs['teacher_topk_logprobs_field'] = self.args.teacher_topk_logprobs_field\n"
        "            trainer_kwargs['teacher_response_token_ids_field'] = self.args.teacher_response_token_ids_field\n"
        "            trainer_kwargs['teacher_topk_storage_dtype'] = self.args.teacher_topk_storage_dtype\n"
        "            if self.args.teacher_model_server:\n"
        "                trainer_kwargs['teacher_model_server'] = self.args.teacher_model_server\n",
        path=path,
    )
    return text


def _patch_gkd_trainer(text: str, path: Path) -> str:
    text = _replace_once(
        text,
        "from swift.template import TemplateInputs\n",
        "from swift.template import TemplateInputs\n"
        "from orbit.integrations.ms_swift_offline_topk import build_teacher_topk_from_dataset, resolve_teacher_data_mode\n",
        path=path,
    )
    text = _replace_once(
        text,
        "        self.vllm_client = kwargs.pop('vllm_client', None)\n"
        "        self.gkd_logits_topk = kwargs.pop('gkd_logits_topk', None)\n"
        "        teacher_model_server = kwargs.pop('teacher_model_server', None)\n",
        "        self.vllm_client = kwargs.pop('vllm_client', None)\n"
        "        self.gkd_logits_topk = kwargs.pop('gkd_logits_topk', None)\n"
        "        teacher_model_server = kwargs.pop('teacher_model_server', None)\n"
        "        self.teacher_data_mode = kwargs.pop('teacher_data_mode', 'auto')\n"
        "        self.teacher_topk_indices_field = kwargs.pop('teacher_topk_indices_field', 'teacher_topk_indices')\n"
        "        self.teacher_topk_logprobs_field = kwargs.pop('teacher_topk_logprobs_field', 'teacher_topk_logprobs')\n"
        "        self.teacher_response_token_ids_field = kwargs.pop('teacher_response_token_ids_field', 'response_token_ids')\n"
        "        self.teacher_topk_storage_dtype = kwargs.pop('teacher_topk_storage_dtype', 'auto')\n",
        path=path,
    )
    text = _replace_once(
        text,
        "        self.teacher_model_server = teacher_model_server\n"
        "        self.use_teacher_api = teacher_model_server is not None\n",
        "        self.teacher_model_server = teacher_model_server\n"
        "        self.use_teacher_api = teacher_model_server is not None\n"
        "        self.use_offline_topk = False\n",
        path=path,
    )
    text = _replace_once(
        text,
        "        teacher_api_logprobs = inputs.pop('_teacher_api_logprobs', None)\n"
        "        teacher_api_indices = inputs.pop('_teacher_api_indices', None)\n",
        "        teacher_api_logprobs = inputs.pop('_teacher_api_logprobs', None)\n"
        "        teacher_api_indices = inputs.pop('_teacher_api_indices', None)\n",
        path=path,
    )
    text = _replace_once(
        text,
        "        elif self.use_teacher_api:\n"
        "            assert teacher_api_logprobs is not None\n",
        "        elif teacher_api_logprobs is not None and teacher_api_indices is not None:\n",
        path=path,
    )
    text = _replace_once(
        text,
        "            # Mark data source for downstream processing (e.g., conditional SFT loss)\n"
        "            encoded_inputs['_data_source'] = data_source\n"
        "\n"
        "            # Fetch teacher logprobs from API if using external teacher service\n"
        "            if self.use_teacher_api:\n"
        "                teacher_logprobs, teacher_indices = self._fetch_teacher_logprobs_from_api(encoded_inputs)\n"
        "                encoded_inputs['_teacher_api_logprobs'] = teacher_logprobs\n"
        "                encoded_inputs['_teacher_api_indices'] = teacher_indices\n",
        "            # Mark data source for downstream processing (e.g., conditional SFT loss)\n"
        "            encoded_inputs['_data_source'] = data_source\n"
        "\n"
        "            teacher_mode = resolve_teacher_data_mode(\n"
        "                configured_mode=self.teacher_data_mode,\n"
        "                samples=inputs,\n"
        "                teacher_model_server=self.teacher_model_server,\n"
        "                has_local_teacher=hasattr(self, 'teacher_model'),\n"
        "                indices_field=self.teacher_topk_indices_field,\n"
        "                logprobs_field=self.teacher_topk_logprobs_field,\n"
        "                response_ids_field=self.teacher_response_token_ids_field,\n"
        "            )\n"
        "            self.use_offline_topk = teacher_mode == DataSource.DATASET or teacher_mode == 'offline_topk'\n"
        "\n"
        "            if teacher_mode == 'teacher_model_server':\n"
        "                teacher_logprobs, teacher_indices = self._fetch_teacher_logprobs_from_api(encoded_inputs)\n"
        "                encoded_inputs['_teacher_api_logprobs'] = teacher_logprobs\n"
        "                encoded_inputs['_teacher_api_indices'] = teacher_indices\n"
        "            elif teacher_mode == 'offline_topk':\n"
        "                teacher_bundle = build_teacher_topk_from_dataset(\n"
        "                    encoded_inputs,\n"
        "                    inputs,\n"
        "                    indices_field=self.teacher_topk_indices_field,\n"
        "                    logprobs_field=self.teacher_topk_logprobs_field,\n"
        "                    response_ids_field=self.teacher_response_token_ids_field,\n"
        "                    storage_dtype=self.teacher_topk_storage_dtype,\n"
        "                )\n"
        "                encoded_inputs['_teacher_api_logprobs'] = teacher_bundle.logprobs\n"
        "                encoded_inputs['_teacher_api_indices'] = teacher_bundle.indices\n",
        path=path,
    )
    text = _replace_once(
        text,
        "    def prediction_step(self, model, inputs, *args, **kwargs):\n"
        "        # Prediction uses full messages\n"
        "        encoded_inputs = self._prepare_batch_inputs(inputs, encode_prompt_only=False)\n"
        "\n"
        "        # Fetch teacher logprobs from API if using external teacher service (for eval)\n"
        "        if self.use_teacher_api:\n"
        "            teacher_logprobs, teacher_indices = self._fetch_teacher_logprobs_from_api(encoded_inputs)\n"
        "            encoded_inputs['_teacher_api_logprobs'] = teacher_logprobs\n"
        "            encoded_inputs['_teacher_api_indices'] = teacher_indices\n"
        "\n"
        "        with self.template.forward_context(self.model, encoded_inputs):\n"
        "            return super().prediction_step(model, encoded_inputs, *args, **kwargs)\n",
        "    def prediction_step(self, model, inputs, *args, **kwargs):\n"
        "        # Prediction uses full messages\n"
        "        encoded_inputs = self._prepare_batch_inputs(inputs, encode_prompt_only=False)\n"
        "\n"
        "        teacher_mode = resolve_teacher_data_mode(\n"
        "            configured_mode=self.teacher_data_mode,\n"
        "            samples=inputs,\n"
        "            teacher_model_server=self.teacher_model_server,\n"
        "            has_local_teacher=hasattr(self, 'teacher_model'),\n"
        "            indices_field=self.teacher_topk_indices_field,\n"
        "            logprobs_field=self.teacher_topk_logprobs_field,\n"
        "            response_ids_field=self.teacher_response_token_ids_field,\n"
        "        )\n"
        "        if teacher_mode == 'teacher_model_server':\n"
        "            teacher_logprobs, teacher_indices = self._fetch_teacher_logprobs_from_api(encoded_inputs)\n"
        "            encoded_inputs['_teacher_api_logprobs'] = teacher_logprobs\n"
        "            encoded_inputs['_teacher_api_indices'] = teacher_indices\n"
        "        elif teacher_mode == 'offline_topk':\n"
        "            teacher_bundle = build_teacher_topk_from_dataset(\n"
        "                encoded_inputs,\n"
        "                inputs,\n"
        "                indices_field=self.teacher_topk_indices_field,\n"
        "                logprobs_field=self.teacher_topk_logprobs_field,\n"
        "                response_ids_field=self.teacher_response_token_ids_field,\n"
        "                storage_dtype=self.teacher_topk_storage_dtype,\n"
        "            )\n"
        "            encoded_inputs['_teacher_api_logprobs'] = teacher_bundle.logprobs\n"
        "            encoded_inputs['_teacher_api_indices'] = teacher_bundle.indices\n"
        "\n"
        "        with self.template.forward_context(self.model, encoded_inputs):\n"
        "            return super().prediction_step(model, encoded_inputs, *args, **kwargs)\n",
        path=path,
    )
    return text


def _patch_rollout_mixin(text: str, path: Path) -> str:
    text = _replace_once(
        text,
        "from swift.rollout import MultiTurnScheduler, multi_turns\n",
        "",
        path=path,
    )
    text = _replace_once(
        text,
        "        if args.multi_turn_scheduler:\n"
        "            # Get tokenizer for scheduler (needed in colocate mode where infer_engine may be None)\n"
        "            tokenizer = getattr(self, 'processing_class', None)\n"
        "            if isinstance(args.multi_turn_scheduler, str):\n"
        "                assert args.multi_turn_scheduler in multi_turns\n"
        "                multi_turn_scheduler = multi_turns[args.multi_turn_scheduler](\n"
        "                    max_turns=args.max_turns, tokenizer=tokenizer)\n"
        "                self.multi_turn_scheduler: MultiTurnScheduler = multi_turn_scheduler\n"
        "            else:\n"
        "                assert isinstance(args.multi_turn_scheduler, MultiTurnScheduler)\n"
        "                self.multi_turn_scheduler: MultiTurnScheduler = args.multi_turn_scheduler\n",
        "        if args.multi_turn_scheduler:\n"
        "            from swift.rollout import MultiTurnScheduler, multi_turns\n"
        "\n"
        "            # Get tokenizer for scheduler (needed in colocate mode where infer_engine may be None)\n"
        "            tokenizer = getattr(self, 'processing_class', None)\n"
        "            if isinstance(args.multi_turn_scheduler, str):\n"
        "                assert args.multi_turn_scheduler in multi_turns\n"
        "                multi_turn_scheduler = multi_turns[args.multi_turn_scheduler](\n"
        "                    max_turns=args.max_turns, tokenizer=tokenizer)\n"
        "                self.multi_turn_scheduler: MultiTurnScheduler = multi_turn_scheduler\n"
        "            else:\n"
        "                assert isinstance(args.multi_turn_scheduler, MultiTurnScheduler)\n"
        "                self.multi_turn_scheduler: MultiTurnScheduler = args.multi_turn_scheduler\n",
        path=path,
    )
    return text


def _patch_dataset_preprocessor_core(text: str, path: Path) -> str:
    text = _replace_once(
        text,
        "                            'channel',\n"
        "                                'margin',\n"
        "                            ]\n",
        "                            'channel',\n"
        "                                'margin',\n"
        "                                'response_token_ids',\n"
        "                                'teacher_topk_indices',\n"
        "                                'teacher_topk_logprobs',\n"
        "                                'teacher_model_name',\n"
        "                                'teacher_topk',\n"
        "                                'teacher_source',\n"
        "                                'teacher_generated_at',\n"
        "                                'teacher_prompt_template_hash',\n"
        "                                'teacher_topk_storage_dtype',\n"
        "                            ]\n",
        path=path,
    )
    return text


def _write_wrapper(swift_root: Path) -> None:
    wrapper = swift_root / "pipelines" / "sampling" / "gkd_topk_sampler.py"
    content = (
        "# Copyright (c) ModelScope Contributors. All rights reserved.\n"
        "from orbit.integrations.ms_swift_offline_topk import GKDTopkSampler\n"
        "\n"
        "__all__ = ['GKDTopkSampler']\n"
    )
    wrapper.write_text(content, encoding="utf-8")


def apply_patches(swift_root: Path) -> list[Path]:
    targets = {
        swift_root / "arguments" / "sampling_args.py": _patch_sampling_args,
        swift_root / "pipelines" / "sampling" / "sampling.py": _patch_sampling,
        swift_root / "arguments" / "rlhf_args.py": _patch_rlhf_args,
        swift_root / "pipelines" / "train" / "rlhf.py": _patch_train_rlhf,
        swift_root / "rlhf_trainers" / "gkd_trainer.py": _patch_gkd_trainer,
        swift_root / "rlhf_trainers" / "rollout_mixin.py": _patch_rollout_mixin,
        swift_root / "dataset" / "preprocessor" / "core.py": _patch_dataset_preprocessor_core,
    }
    changed: list[Path] = []
    for path, patcher in targets.items():
        text = path.read_text(encoding="utf-8")
        new_text = patcher(text, path)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            changed.append(path)
    _write_wrapper(swift_root)
    changed.append(swift_root / "pipelines" / "sampling" / "gkd_topk_sampler.py")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--swift-root", default=None, help="Path to installed swift package directory")
    args = parser.parse_args()
    root = _swift_root(args.swift_root)
    changed = apply_patches(root)
    print(f"patched ms-swift at {root}")
    for path in changed:
        print(path)


if __name__ == "__main__":
    main()
