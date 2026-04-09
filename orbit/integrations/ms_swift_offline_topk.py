"""Offline top-k teacher helpers for patched ms-swift GKD flows."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Mapping, Sequence

if TYPE_CHECKING:
    import torch

DEFAULT_TEACHER_DATA_MODE = "auto"
DEFAULT_TEACHER_TOPK_INDICES_FIELD = "teacher_topk_indices"
DEFAULT_TEACHER_TOPK_LOGPROBS_FIELD = "teacher_topk_logprobs"
DEFAULT_TEACHER_RESPONSE_TOKEN_IDS_FIELD = "response_token_ids"
DEFAULT_TEACHER_TOPK_STORAGE_DTYPE = "auto"
_VALID_TEACHER_DATA_MODES = {"auto", "local_model", "teacher_model_server", "offline_topk"}
_VALID_STORAGE_DTYPES = {"auto", "float32", "bfloat16"}


def normalize_teacher_data_mode(value: str | None) -> str:
    mode = str(value or DEFAULT_TEACHER_DATA_MODE).strip() or DEFAULT_TEACHER_DATA_MODE
    if mode not in _VALID_TEACHER_DATA_MODES:
        raise ValueError(
            "teacher_data_mode must be one of: "
            + ", ".join(sorted(_VALID_TEACHER_DATA_MODES))
        )
    return mode


def normalize_teacher_topk_storage_dtype(value: str | None) -> str:
    dtype = str(value or DEFAULT_TEACHER_TOPK_STORAGE_DTYPE).strip() or DEFAULT_TEACHER_TOPK_STORAGE_DTYPE
    if dtype not in _VALID_STORAGE_DTYPES:
        raise ValueError(
            "teacher_topk_storage_dtype must be one of: "
            + ", ".join(sorted(_VALID_STORAGE_DTYPES))
        )
    return dtype


def _has_offline_topk_fields(
    sample: Mapping[str, Any] | None,
    *,
    indices_field: str,
    logprobs_field: str,
    response_ids_field: str,
) -> bool:
    if not sample:
        return False
    return (
        sample.get(indices_field) is not None
        and sample.get(logprobs_field) is not None
        and sample.get(response_ids_field) is not None
    )


def resolve_teacher_data_mode(
    *,
    configured_mode: str | None,
    samples: Sequence[Mapping[str, Any]] | None,
    teacher_model_server: str | None,
    has_local_teacher: bool,
    indices_field: str = DEFAULT_TEACHER_TOPK_INDICES_FIELD,
    logprobs_field: str = DEFAULT_TEACHER_TOPK_LOGPROBS_FIELD,
    response_ids_field: str = DEFAULT_TEACHER_RESPONSE_TOKEN_IDS_FIELD,
) -> str:
    mode = normalize_teacher_data_mode(configured_mode)
    if mode != "auto":
        return mode
    if samples:
        first = next((sample for sample in samples if isinstance(sample, Mapping)), None)
        if _has_offline_topk_fields(
            first,
            indices_field=indices_field,
            logprobs_field=logprobs_field,
            response_ids_field=response_ids_field,
        ):
            return "offline_topk"
    if teacher_model_server:
        return "teacher_model_server"
    if has_local_teacher:
        return "local_model"
    raise ValueError(
        "Unable to resolve GKD teacher source automatically. Set teacher_data_mode explicitly or "
        f"provide dataset fields {response_ids_field}, {indices_field}, and {logprobs_field}."
    )


def validate_gkd_teacher_mode(
    *,
    teacher_data_mode: str | None,
    teacher_model: str | None,
    teacher_model_server: str | None,
    gkd_logits_topk: int | None,
    seq_kd: bool,
    use_liger_kernel: bool = False,
) -> None:
    mode = normalize_teacher_data_mode(teacher_data_mode)
    has_teacher_model = bool(str(teacher_model or "").strip())
    has_teacher_server = bool(str(teacher_model_server or "").strip())

    if gkd_logits_topk is not None and gkd_logits_topk <= 0:
        raise ValueError(f"gkd_logits_topk must be a positive integer, got {gkd_logits_topk}")
    if gkd_logits_topk is not None and use_liger_kernel:
        raise ValueError("gkd_logits_topk is not supported when using liger kernel")

    if mode == "local_model":
        if not has_teacher_model:
            raise ValueError("teacher_model is required when teacher_data_mode=local_model")
        if has_teacher_server:
            raise ValueError("teacher_model_server must be unset when teacher_data_mode=local_model")
        return

    if mode == "teacher_model_server":
        if has_teacher_model:
            raise ValueError("teacher_model must be unset when teacher_data_mode=teacher_model_server")
        if not has_teacher_server:
            raise ValueError("teacher_model_server is required when teacher_data_mode=teacher_model_server")
        if gkd_logits_topk is None:
            raise ValueError("gkd_logits_topk is required when teacher_data_mode=teacher_model_server")
        if seq_kd:
            raise NotImplementedError(
                "Sequential KD is not supported when using teacher_model_server"
            )
        return

    if mode == "offline_topk":
        if has_teacher_model or has_teacher_server:
            raise ValueError(
                "teacher_model and teacher_model_server must both be unset when teacher_data_mode=offline_topk"
            )
        if seq_kd:
            raise NotImplementedError("Sequential KD is not supported when teacher_data_mode=offline_topk")
        return

    if has_teacher_model and has_teacher_server:
        raise ValueError(
            "GKD requires either teacher_model or teacher_model_server to be set, not both"
        )
    if has_teacher_server:
        if gkd_logits_topk is None:
            raise ValueError("gkd_logits_topk is required when using teacher_model_server")
        if seq_kd:
            raise NotImplementedError(
                "Sequential KD is not supported when using teacher_model_server"
            )


@dataclass(slots=True)
class OfflineTopkTensorBundle:
    logprobs: torch.Tensor
    indices: torch.Tensor


def _response_positions_from_labels(labels_row: torch.Tensor) -> tuple[list[int], list[int]]:
    positions = (labels_row != -100).nonzero(as_tuple=False).flatten().tolist()
    token_ids = [int(labels_row[pos].item()) for pos in positions]
    return positions, token_ids


def _find_contiguous_subsequence(haystack: list[int], needle: list[int]) -> tuple[int, int] | None:
    if not needle:
        return (0, 0)
    if len(needle) > len(haystack):
        return None
    width = len(needle)
    for start in range(0, len(haystack) - width + 1):
        if haystack[start:start + width] == needle:
            return (start, start + width)
    return None


def build_teacher_topk_from_dataset(
    encoded_inputs: Mapping[str, torch.Tensor],
    raw_inputs: Sequence[Mapping[str, Any]],
    *,
    indices_field: str = DEFAULT_TEACHER_TOPK_INDICES_FIELD,
    logprobs_field: str = DEFAULT_TEACHER_TOPK_LOGPROBS_FIELD,
    response_ids_field: str = DEFAULT_TEACHER_RESPONSE_TOKEN_IDS_FIELD,
    storage_dtype: str = DEFAULT_TEACHER_TOPK_STORAGE_DTYPE,
) -> OfflineTopkTensorBundle:
    import torch

    labels = encoded_inputs["labels"]
    if labels.ndim != 2:
        raise ValueError(f"Expected labels to have shape [batch, seq_len], got {tuple(labels.shape)}")
    batch_size, seq_len = labels.shape
    if batch_size != len(raw_inputs):
        raise ValueError(
            f"Encoded batch size {batch_size} does not match raw input count {len(raw_inputs)}"
        )
    storage = normalize_teacher_topk_storage_dtype(storage_dtype)
    topk: int | None = None
    logprobs = None
    indices = None

    for batch_idx, sample in enumerate(raw_inputs):
        response_token_ids = sample.get(response_ids_field)
        sample_indices = sample.get(indices_field)
        sample_logprobs = sample.get(logprobs_field)
        if response_token_ids is None or sample_indices is None or sample_logprobs is None:
            raise ValueError(
                "offline_topk GKD sample is missing one of the required fields: "
                f"{response_ids_field}, {indices_field}, {logprobs_field}"
            )
        response_token_ids = [int(token_id) for token_id in response_token_ids]
        response_positions, label_token_ids = _response_positions_from_labels(labels[batch_idx])
        aligned_range = _find_contiguous_subsequence(response_token_ids, label_token_ids)
        if aligned_range is None:
            tail_count = min(
                len(response_positions),
                len(response_token_ids),
                len(sample_indices),
                len(sample_logprobs),
            )
            if tail_count <= 0:
                raise ValueError(
                    "offline_topk response_token_ids do not match encoded assistant response token ids"
                )
            response_positions = response_positions[-tail_count:]
            response_token_ids = response_token_ids[-tail_count:]
            sample_indices = sample_indices[-tail_count:]
            sample_logprobs = sample_logprobs[-tail_count:]
            aligned_range = (0, len(response_token_ids))
        start_idx, end_idx = aligned_range
        if start_idx != 0 or end_idx != len(response_token_ids):
            response_token_ids = response_token_ids[start_idx:end_idx]
            sample_indices = sample_indices[start_idx:end_idx]
            sample_logprobs = sample_logprobs[start_idx:end_idx]
        if len(sample_indices) != len(response_token_ids) or len(sample_logprobs) != len(response_token_ids):
            raise ValueError(
                "offline_topk teacher_topk_* lengths must match response_token_ids length"
            )
        if topk is None:
            if not sample_indices:
                raise ValueError("offline_topk teacher_topk_indices cannot be empty")
            topk = len(sample_indices[0])
            logprobs = torch.full(
                (batch_size, seq_len - 1, topk),
                float("-inf"),
                dtype=torch.float32,
                device=labels.device,
            )
            indices = torch.zeros((batch_size, seq_len - 1, topk), dtype=torch.long, device=labels.device)
        for token_pos, row_indices, row_logprobs in zip(response_positions, sample_indices, sample_logprobs):
            if token_pos <= 0:
                raise ValueError("offline_topk assistant response cannot start at token position 0")
            if len(row_indices) != topk or len(row_logprobs) != topk:
                raise ValueError("offline_topk top-k rows must have consistent widths")
            row = token_pos - 1
            indices[batch_idx, row] = torch.tensor(row_indices, dtype=torch.long, device=labels.device)
            lp_tensor = torch.tensor(row_logprobs, device=labels.device)
            if storage == "bfloat16":
                lp_tensor = lp_tensor.to(torch.bfloat16)
            logprobs[batch_idx, row] = lp_tensor.to(torch.float32)

    assert logprobs is not None and indices is not None
    return OfflineTopkTensorBundle(logprobs=logprobs, indices=indices)


def serialize_teacher_logprobs_for_storage(
    values: torch.Tensor,
    *,
    storage_dtype: str = DEFAULT_TEACHER_TOPK_STORAGE_DTYPE,
) -> list[float]:
    import torch

    storage = normalize_teacher_topk_storage_dtype(storage_dtype)
    tensor = values.detach().cpu().to(torch.float32)
    if storage == "bfloat16":
        tensor = tensor.to(torch.bfloat16).to(torch.float32)
    return tensor.tolist()


@lru_cache(maxsize=1)
def _build_teacher_session():
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    retry_strategy = Retry(
        total=5,
        connect=5,
        read=5,
        status=3,
        status_forcelist=[500, 502, 503],
        backoff_factor=2,
        allowed_methods=["POST", "GET"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def fetch_teacher_server_topk(
    base_url: str,
    input_ids: list[list[int]],
    *,
    topk: int,
    timeout: float = 300.0,
) -> tuple[torch.Tensor, torch.Tensor]:
    import logging
    from concurrent.futures import ThreadPoolExecutor
    import torch

    session = _build_teacher_session()
    base_url = base_url.rstrip("/")
    batch_size = len(input_ids)
    max_seq_len = max(len(ids) for ids in input_ids)
    out_len = max_seq_len - 1
    url = f"{base_url}/v1/completions"
    model = "default"
    try:
        resp = session.get(f"{base_url}/v1/models", timeout=10)
        if resp.ok:
            model = resp.json()["data"][0]["id"]
    except Exception:
        pass

    logprobs_out = torch.full((batch_size, out_len, topk), float("-inf"), dtype=torch.float32)
    indices_out = torch.zeros((batch_size, out_len, topk), dtype=torch.long)
    errors: dict[int, Exception] = {}
    logger = logging.getLogger(__name__)

    def _fetch_one(batch_idx: int) -> None:
        payload = {
            "model": model,
            "prompt": input_ids[batch_idx],
            "max_tokens": 1,
            "temperature": 0,
            "prompt_logprobs": topk,
        }
        try:
            resp = session.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
            prompt_logprobs = resp.json()["choices"][0].get("prompt_logprobs", [])
            for raw_pos in range(1, len(prompt_logprobs)):
                pos_lp = prompt_logprobs[raw_pos]
                if pos_lp is None:
                    continue
                out_pos = raw_pos - 1
                if out_pos >= out_len:
                    break
                sorted_items = sorted(pos_lp.items(), key=lambda item: -item[1]["logprob"])[:topk]
                for k, (token_id_str, info) in enumerate(sorted_items):
                    indices_out[batch_idx, out_pos, k] = int(token_id_str)
                    logprobs_out[batch_idx, out_pos, k] = info["logprob"]
        except Exception as exc:
            errors[batch_idx] = exc
            logger.error("Failed to fetch teacher logprobs for sequence %s: %s", batch_idx, exc)

    with ThreadPoolExecutor(max_workers=min(batch_size, 8)) as pool:
        list(pool.map(_fetch_one, range(batch_size)))

    if errors:
        failed = sorted(errors)
        detail = "; ".join(f"seq {idx}: {errors[idx]}" for idx in failed)
        raise RuntimeError(
            f"Failed to fetch teacher logprobs for {len(errors)} sequence(s). Failed indices: {failed}. "
            f"Last errors: {detail}"
        )
    return logprobs_out, indices_out


class GKDTopkSampler:
    """Offline top-k teacher sampler used by patched `swift sample`."""

    def __init__(self, input_args):
        from swift.infer_engine import TransformersEngine
        from swift.pipelines.sampling.vanilla_sampler import VanillaSampler

        self.args = input_args
        self._vanilla_cls = VanillaSampler
        self.processor = None
        self.template = None
        self.teacher_model = None
        self.teacher_server = str(getattr(input_args, "teacher_model_server", "") or "").strip()
        self.teacher_model_name = str(getattr(input_args, "teacher_model", "") or "").strip()
        self.teacher_topk = int(getattr(input_args, "gkd_logits_topk", 0) or 0)
        self.indices_field = getattr(
            input_args, "teacher_topk_indices_field", DEFAULT_TEACHER_TOPK_INDICES_FIELD
        )
        self.logprobs_field = getattr(
            input_args, "teacher_topk_logprobs_field", DEFAULT_TEACHER_TOPK_LOGPROBS_FIELD
        )
        self.response_ids_field = getattr(
            input_args, "teacher_response_token_ids_field", DEFAULT_TEACHER_RESPONSE_TOKEN_IDS_FIELD
        )
        self.storage_dtype = getattr(
            input_args, "teacher_topk_storage_dtype", DEFAULT_TEACHER_TOPK_STORAGE_DTYPE
        )
        _, self.processor = input_args.get_model_processor(load_model=False)
        self.template = input_args.get_template(self.processor)
        self.template.set_mode("train")
        self._server_fetch = None
        if self.teacher_model_name:
            self.teacher_model, _ = input_args.get_model_processor(
                model=self.teacher_model_name,
                model_type=getattr(input_args, "teacher_model_type", None),
                revision=getattr(input_args, "teacher_model_revision", None),
            )
            self.teacher_model.eval()
        elif self.teacher_server:
            self._server_fetch = fetch_teacher_server_topk
        else:
            raise ValueError("gkd_topk sampler requires either teacher_model or teacher_model_server")

        self._engine_cls = TransformersEngine  # imported to ensure runtime dependency stays available

    def _encode_row(self, row: Mapping[str, Any]) -> tuple[list[int], list[int], list[int]]:
        encoded = self.template.encode(copy.deepcopy(dict(row)), return_length=True)
        input_ids = list(encoded["input_ids"])
        labels = encoded["labels"]
        response_positions = [idx for idx, token_id in enumerate(labels) if token_id != -100]
        response_token_ids = [int(labels[idx]) for idx in response_positions]
        return input_ids, response_positions, response_token_ids

    def truncate_input(self, slices):
        return slices

    def _collect_server_topk(self, input_ids: list[int], response_positions: list[int]) -> tuple[list[list[int]], list[list[float]]]:
        bundle = self._server_fetch(self.teacher_server, [input_ids], topk=self.teacher_topk)
        logprobs, indices = bundle
        response_indices: list[list[int]] = []
        response_logprobs: list[list[float]] = []
        for token_pos in response_positions:
            row = token_pos - 1
            response_indices.append(indices[0, row].tolist())
            response_logprobs.append(
                serialize_teacher_logprobs_for_storage(logprobs[0, row], storage_dtype=self.storage_dtype)
            )
        return response_indices, response_logprobs

    def _collect_local_topk(self, input_ids: list[int], response_positions: list[int]) -> tuple[list[list[int]], list[list[float]]]:
        import torch
        import torch.nn.functional as F

        device = next(self.teacher_model.parameters()).device
        input_tensor = torch.tensor([input_ids], dtype=torch.long, device=device)
        attention_mask = torch.ones_like(input_tensor)
        with torch.no_grad():
            logits = self.teacher_model(input_ids=input_tensor, attention_mask=attention_mask).logits[0]
        response_indices: list[list[int]] = []
        response_logprobs: list[list[float]] = []
        for token_pos in response_positions:
            row = token_pos - 1
            token_logprobs = F.log_softmax(logits[row].to(torch.float32), dim=-1)
            values, idx = torch.topk(token_logprobs, k=self.teacher_topk, dim=-1)
            response_indices.append(idx.tolist())
            response_logprobs.append(
                serialize_teacher_logprobs_for_storage(values, storage_dtype=self.storage_dtype)
            )
        return response_indices, response_logprobs

    def do_sample(self, data) -> list[str]:
        rows = self._vanilla_cls.convert_data_to_rows(data)
        generated: list[str] = []
        for row in rows:
            messages = copy.deepcopy(row["messages"])
            if not messages or messages[-1].get("role") != "assistant":
                raise ValueError("gkd_topk sampler requires messages ending with an assistant response")
            input_ids, response_positions, response_token_ids = self._encode_row({"messages": messages})
            if self.teacher_model is not None:
                teacher_indices, teacher_logprobs = self._collect_local_topk(input_ids, response_positions)
                teacher_source = "local_model"
                teacher_name = self.teacher_model_name
            else:
                teacher_indices, teacher_logprobs = self._collect_server_topk(input_ids, response_positions)
                teacher_source = "teacher_model_server"
                teacher_name = self.teacher_server
            payload = copy.deepcopy(row)
            payload[self.response_ids_field] = response_token_ids
            payload[self.indices_field] = teacher_indices
            payload[self.logprobs_field] = teacher_logprobs
            payload["teacher_topk"] = self.teacher_topk
            payload["teacher_source"] = teacher_source
            payload["teacher_model_name"] = teacher_name
            payload["teacher_topk_storage_dtype"] = normalize_teacher_topk_storage_dtype(self.storage_dtype)
            generated.append(json.dumps(payload, ensure_ascii=False) + "\n")
        return generated
