from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, TYPE_CHECKING

import torch.distributed as dist

from swift.rollout.multi_turn import RolloutTurnAccumulator, resolve_sync
from swift.utils import get_logger, remove_response

if TYPE_CHECKING:
    from swift.infer_engine import RequestConfig
    from swift.infer_engine.protocol import ChatCompletionResponseChoice, RolloutInferRequest, RolloutOutput
    from swift.rollout import MultiTurnScheduler


logger = get_logger()


COMMAND_INIT = 'INIT'
COMMAND_GENERATE = 'GENERATE'
COMMAND_STOP = 'STOP'
COMMAND_ABORT = 'ABORT'


@dataclass
class TPGroupCommand:
    command_type: str
    turn_id: int
    infer_requests: List['RolloutInferRequest'] = field(default_factory=list)
    rank_outputs: List[List['RolloutOutput']] = field(default_factory=list)
    error_message: str = ''
    metadata: Dict[str, Any] = field(default_factory=dict)


class TPGroupCommandExecutor(Protocol):

    def broadcast(self, command: Optional[TPGroupCommand]) -> TPGroupCommand:
        ...


def gather_rank_metadata(metadata: Dict[str, Any], *, group=None) -> List[Dict[str, Any]]:
    if not dist.is_available() or not dist.is_initialized() or group is None:
        return [metadata]
    world_size = dist.get_world_size(group=group)
    gathered = [None] * world_size
    dist.all_gather_object(gathered, metadata, group=group)
    return gathered


def broadcast_command_object(command: Optional[TPGroupCommand], *, group, src_rank: int) -> TPGroupCommand:
    if not dist.is_available() or not dist.is_initialized() or group is None:
        if command is None:
            raise RuntimeError('broadcast_command_object requires a command when no process group is active')
        return command
    payload = [command]
    dist.broadcast_object_list(payload, src=src_rank, group=group)
    result = payload[0]
    if result is None:
        raise RuntimeError('broadcast_command_object received no command payload')
    return result


@dataclass
class TorchTPGroupCommandExecutor:
    group: Any
    src_rank: int
    local_rank: int
    group_size: int

    def broadcast(self, command: Optional[TPGroupCommand]) -> TPGroupCommand:
        result = broadcast_command_object(command, group=self.group, src_rank=self.src_rank)
        logger.info(
            '[tp_command] stage=%s command_type=%s turn_id=%s src_rank=%s local_rank=%s group_size=%s batch_size=%s',
            result.metadata.get('stage', ''),
            result.command_type,
            result.turn_id,
            self.src_rank,
            self.local_rank,
            self.group_size,
            result.metadata.get('batch_size', 0),
        )
        return result


@dataclass
class _EpisodeState:
    request: 'RolloutInferRequest'
    accumulator: RolloutTurnAccumulator = field(default_factory=RolloutTurnAccumulator)


@dataclass
class ColocateEpisodeDriver:
    executor: TPGroupCommandExecutor
    scheduler: 'MultiTurnScheduler'
    infer_fn: Callable[[List['RolloutInferRequest'], 'RequestConfig'], List['RolloutOutput']]
    request_config: 'RequestConfig'
    local_rank_in_group: int
    local_input_lengths: Sequence[int]
    extract_logprobs_fn: Callable[['ChatCompletionResponseChoice'], List[float]]
    is_leader: bool

    def __post_init__(self):
        self._group_size = len(self.local_input_lengths)
        self._local_start_idx = sum(self.local_input_lengths[:self.local_rank_in_group])
        self._local_end_idx = self._local_start_idx + self.local_input_lengths[self.local_rank_in_group]
        self._last_executed_turn = 0

    def _rank_slices(self, outputs: List['RolloutOutput']) -> List[List['RolloutOutput']]:
        rank_outputs: List[List['RolloutOutput']] = []
        cursor = 0
        for length in self.local_input_lengths:
            rank_outputs.append(outputs[cursor:cursor + length])
            cursor += length
        return rank_outputs

    def _validate_command(self, command: TPGroupCommand) -> None:
        if command.command_type in {COMMAND_INIT, COMMAND_GENERATE}:
            expected_turn = self._last_executed_turn + 1
            if command.turn_id != expected_turn:
                raise RuntimeError(
                    f'TP command turn mismatch: expected={expected_turn} got={command.turn_id} '
                    f'command_type={command.command_type}'
                )
            self._last_executed_turn = command.turn_id
        elif command.command_type in {COMMAND_STOP, COMMAND_ABORT}:
            if command.turn_id < self._last_executed_turn:
                raise RuntimeError(
                    f'TP terminal command turn mismatch: last_seen={self._last_executed_turn} got={command.turn_id} '
                    f'command_type={command.command_type}'
                )
        else:
            raise RuntimeError(f'Unsupported TP command type: {command.command_type}')

    def _build_abort(self, *, turn_id: int, error_message: str, stage: str) -> TPGroupCommand:
        return TPGroupCommand(
            command_type=COMMAND_ABORT,
            turn_id=turn_id,
            error_message=error_message,
            metadata={'stage': stage, 'batch_size': 0},
        )

    def run(self, global_requests: List['RolloutInferRequest']) -> List['RolloutOutput']:
        pending_command: Optional[TPGroupCommand] = None
        states: Dict[int, _EpisodeState] = {}
        active_indices: List[int] = []
        final_outputs: List[Optional['RolloutOutput']] = [None] * len(global_requests)

        if self.is_leader:
            try:
                prepared_requests = [
                    resolve_sync(self.scheduler.prepare_request(deepcopy(request), self.request_config))
                    for request in global_requests
                ]
                active_indices = list(range(len(prepared_requests)))
                states = {index: _EpisodeState(request=req) for index, req in zip(active_indices, prepared_requests)}
                pending_command = TPGroupCommand(
                    command_type=COMMAND_INIT,
                    turn_id=1,
                    infer_requests=prepared_requests,
                    metadata={
                        'stage': 'colocate_episode_init',
                        'batch_size': len(prepared_requests),
                        'active_indices': list(active_indices),
                    },
                )
            except Exception as exc:  # pragma: no cover - exercised via broadcast path
                pending_command = self._build_abort(
                    turn_id=0,
                    error_message=f'leader prepare_request failed: {exc}',
                    stage='colocate_episode_init',
                )

        while True:
            command = self.executor.broadcast(pending_command)
            pending_command = None
            self._validate_command(command)

            if command.command_type == COMMAND_ABORT:
                raise RuntimeError(command.error_message or 'TP colocate episode aborted')

            if command.command_type == COMMAND_STOP:
                if not command.rank_outputs:
                    raise RuntimeError('TP STOP command missing rank_outputs')
                return command.rank_outputs[self.local_rank_in_group]

            outputs = self.infer_fn(command.infer_requests, self.request_config)
            if not self.is_leader:
                continue

            try:
                next_active_indices: List[int] = []
                next_requests: List['RolloutInferRequest'] = []
                for global_index, current_request, output in zip(active_indices, command.infer_requests, outputs):
                    state = states[global_index]
                    response_choice = output.response.choices[0]
                    messages = state.request.messages
                    if messages[-1]['content'] is None:
                        remove_response(messages)

                    completion = response_choice.message.content or ''
                    is_continuation = False
                    if messages[-1]['role'] == 'assistant':
                        messages[-1]['content'] += completion
                        is_continuation = True
                    else:
                        messages.append({'role': 'assistant', 'content': completion})

                    step_result = resolve_sync(self.scheduler.advance(state.request, response_choice, command.turn_id))
                    current_logprobs = step_result.get('rollout_logprobs') or self.extract_logprobs_fn(response_choice)
                    if step_result.get('rollout_infos'):
                        state.accumulator.rollout_infos.update(step_result['rollout_infos'])

                    if step_result.get('finished'):
                        state.accumulator.record_final_response(
                            response_choice,
                            is_continuation=is_continuation,
                            current_logprobs=current_logprobs,
                        )
                        final_outputs[global_index] = state.accumulator.build_output(
                            response=output.response,
                            messages=state.request.messages,
                            current_turn=command.turn_id,
                        )
                        continue

                    next_request = step_result['infer_request']
                    state.accumulator.record_step_result(
                        step_result,
                        is_continuation=is_continuation,
                        current_logprobs=current_logprobs,
                    )
                    if next_request.messages[-1]['role'] == 'assistant':
                        next_request.messages.append({'role': 'assistant', 'content': None})
                    state.request = next_request
                    next_active_indices.append(global_index)
                    next_requests.append(next_request)

                if next_active_indices:
                    active_indices = next_active_indices
                    pending_command = TPGroupCommand(
                        command_type=COMMAND_GENERATE,
                        turn_id=command.turn_id + 1,
                        infer_requests=next_requests,
                        metadata={
                            'stage': 'colocate_episode_generate',
                            'batch_size': len(next_requests),
                            'active_indices': list(next_active_indices),
                        },
                    )
                else:
                    if any(output is None for output in final_outputs):
                        raise RuntimeError('TP episode finished without producing outputs for every trajectory')
                    pending_command = TPGroupCommand(
                        command_type=COMMAND_STOP,
                        turn_id=command.turn_id,
                        rank_outputs=self._rank_slices(final_outputs),  # type: ignore[arg-type]
                        metadata={
                            'stage': 'colocate_episode_stop',
                            'batch_size': len(final_outputs),
                        },
                    )
            except Exception as exc:
                pending_command = self._build_abort(
                    turn_id=command.turn_id,
                    error_message=f'leader episode advance failed: {exc}',
                    stage='colocate_episode_advance',
                )
