from __future__ import annotations

import asyncio
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

from swift.infer_engine.protocol import (
    ChatCompletionResponse,
    ChatCompletionResponseChoice,
    ChatMessage,
    RequestConfig,
    RolloutInferRequest,
    RolloutOutput,
    UsageInfo,
)
from swift.rollout import ContextManager, Env, context_managers, envs
from swift.rollout.multi_turn import GYMScheduler
from swift.rlhf_trainers.args_mixin import RolloutTrainerArgumentsMixin


class _FakeGymContext(ContextManager):
    def manage_context(self, history, trajectory_id):  # type: ignore[override]
        return list(history)


class _FakeGymEnv(Env):
    closed_sessions: list[int] = []

    def __init__(self, env_config):
        super().__init__(env_config)
        self.turn = 0

    async def reset(self, config):  # type: ignore[override]
        return "obs-0", {"stage": "reset"}, "system-prompt"

    async def step(self, action):  # type: ignore[override]
        self.turn += 1
        if self.turn == 1:
            return "obs-1", 0.25, False, {"turn": 1}
        return "done", 0.75, True, {"turn": 2}

    async def close(self):  # type: ignore[override]
        self.closed_sessions.append(self.turn)


class _FakeInferEngine:
    def __init__(self, contents: list[str]):
        self.contents = list(contents)
        self.calls = 0

    async def infer_async(self, infer_request, request_config, **kwargs):
        content = self.contents[self.calls]
        self.calls += 1
        return ChatCompletionResponse(
            model="fake-model",
            choices=[
                ChatCompletionResponseChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=content),
                    finish_reason="stop",
                    logprobs={"content": [{"logprob": -0.1}]},
                    token_ids=[self.calls, self.calls + 10],
                )
            ],
            usage=UsageInfo(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )


class _FakeDriverInfer:
    def __init__(self):
        self.turn = 0
        self.calls: list[list[str]] = []

    def __call__(self, infer_requests, request_config):
        self.turn += 1
        self.calls.append([request.uuid or "" for request in infer_requests])
        outputs = []
        for idx, _request in enumerate(infer_requests):
            outputs.append(
                RolloutOutput(
                    response=ChatCompletionResponse(
                        model="fake-model",
                        choices=[
                            ChatCompletionResponseChoice(
                                index=0,
                                message=ChatMessage(role="assistant", content=f"turn-{self.turn}-action-{idx}"),
                                finish_reason="stop",
                                token_ids=[self.turn, idx + 10],
                            )
                        ],
                        usage=UsageInfo(prompt_tokens=1, completion_tokens=2, total_tokens=3),
                    )
                )
            )
        return outputs


class _LoopbackCommandExecutor:
    def __init__(self):
        self.commands = []

    def broadcast(self, command):
        assert command is not None
        self.commands.append(command)
        return command


class _ScriptedCommandExecutor:
    def __init__(self, commands):
        self.commands = list(commands)

    def broadcast(self, command):
        assert self.commands, "no scripted TP command remaining"
        return self.commands.pop(0)


def _load_colocate_driver_module():
    path = Path("packages/affine_ms_swift/vendor/ms_swift_fork/swift/rlhf_trainers/colocate_driver.py")
    spec = importlib.util.spec_from_file_location("affine_ms_swift_colocate_driver", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_fork_training_arguments_module():
    path = Path("packages/affine_ms_swift/vendor/ms_swift_fork/swift/trainers/arguments.py")
    spec = importlib.util.spec_from_file_location("affine_ms_swift_training_arguments", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _memorygym_like_request() -> RolloutInferRequest:
    return RolloutInferRequest(
        messages=[{"role": "user", "content": "seed"}],
        data_dict={
            "env_config": {"name": "fake_gym"},
            "ctx_config": {"name": "fake_ctx"},
        },
        uuid="traj-1",
    )


def test_build_paths_use_local_ms_swift_fork_and_not_upstream_pins():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    bootstrap = Path("orbit/setup/bootstrap.sh").read_text(encoding="utf-8")
    installer = Path("orbit/setup/install_local_rl_stack.sh").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "packages/affine_ms_swift/vendor/ms_swift_fork" in dockerfile
    assert "repos/MemoryGym" in dockerfile
    assert "install_local_rl_stack.sh" in dockerfile
    assert '"ms-swift==' not in dockerfile
    assert '"ms-swift==' not in bootstrap
    assert 'apply_ms_swift_patches.py' not in installer
    assert 'uv pip install --no-cache "${FORK_ROOT}"' in installer
    assert '"ms-swift>=' not in pyproject


async def _run_scheduler_server_path():
    scheduler = GYMScheduler(
        _FakeInferEngine(["first-action", "final-action"]),
        max_turns=4,
        gym_env="fake_gym",
        context_manager="fake_ctx",
    )
    request = _memorygym_like_request()
    return await scheduler.run(request, RequestConfig(max_tokens=32, n=1))


def test_gym_scheduler_server_run_tracks_episode_reward_and_turns():
    envs["fake_gym"] = _FakeGymEnv
    context_managers["fake_ctx"] = _FakeGymContext
    _FakeGymEnv.closed_sessions.clear()
    try:
        output = asyncio.run(_run_scheduler_server_path())
    finally:
        envs.pop("fake_gym", None)
        context_managers.pop("fake_ctx", None)

    assert output.rollout_infos["num_turns"] == 2
    assert output.rollout_infos["total_reward"] == 1.0
    assert output.rollout_infos["step_rewards"] == [0.25, 0.75]
    assert output.rollout_infos["trajectory_info"][0]["stage"] == "reset"
    assert output.rollout_infos["trajectory_info"][-1]["turn"] == 2
    assert output.messages[0]["role"] == "system"
    assert output.messages[-1]["content"] == "final-action"
    assert output.response_token_ids == [[1, 11], [2, 12]]
    assert output.response_loss_mask == [[1, 1], [1, 1]]
    assert _FakeGymEnv.closed_sessions


def test_gym_scheduler_prepare_and_advance_support_colocate_contract():
    envs["fake_gym"] = _FakeGymEnv
    context_managers["fake_ctx"] = _FakeGymContext
    _FakeGymEnv.closed_sessions.clear()
    scheduler = GYMScheduler(
        infer_engine=None,
        max_turns=4,
        gym_env="fake_gym",
        context_manager="fake_ctx",
    )
    try:
        request = asyncio.run(scheduler.prepare_request(_memorygym_like_request(), RequestConfig(max_tokens=32, n=1)))
        assert request.messages[0]["role"] == "system"
        assert request.messages[1]["content"] == "obs-0"

        request.messages.append({"role": "assistant", "content": "first-action"})
        first_choice = ChatCompletionResponseChoice(
            index=0,
            message=ChatMessage(role="assistant", content="first-action"),
            finish_reason="stop",
            token_ids=[1, 11],
        )
        first_step = asyncio.run(scheduler.advance(request, first_choice, 1))
        assert first_step["finished"] is False
        assert first_step["rollout_infos"]["total_reward"] == 0.25
        assert first_step["response_token_ids"] == [1, 11]
        next_request = first_step["infer_request"]
        assert next_request.messages[-1]["content"] == "obs-1"

        next_request.messages.append({"role": "assistant", "content": "final-action"})
        second_choice = ChatCompletionResponseChoice(
            index=0,
            message=ChatMessage(role="assistant", content="final-action"),
            finish_reason="stop",
            token_ids=[2, 12],
        )
        second_step = asyncio.run(scheduler.advance(next_request, second_choice, 2))
        assert second_step["finished"] is True
        assert second_step["rollout_infos"]["total_reward"] == 1.0
        assert second_step["rollout_infos"]["step_rewards"] == [0.25, 0.75]
    finally:
        envs.pop("fake_gym", None)
        context_managers.pop("fake_ctx", None)


def test_rollout_trainer_arguments_accept_gym_env_fields():
    args = RolloutTrainerArgumentsMixin(use_vllm=True, vllm_mode="colocate", gym_env="memorygym_env")
    assert args.gym_env == "memorygym_env"
    assert args.use_gym_env is True


def test_fork_training_arguments_disable_bad_ddp_defaults_for_gradient_checkpointing(tmp_path):
    module = _load_fork_training_arguments_module()
    args = module.TrainingArguments(
        output_dir=str(tmp_path / "out"),
        gradient_checkpointing=True,
        report_to=["wandb"],
    )
    assert args.ddp_find_unused_parameters is False
    assert args.ddp_broadcast_buffers is False


def test_rollout_mixin_uses_leader_submit_all_rank_step_for_tp_group():
    source = Path(
        "packages/affine_ms_swift/vendor/ms_swift_fork/swift/rlhf_trainers/rollout_mixin.py"
    ).read_text(encoding="utf-8")
    assert "def _engine_infer_tp_group(" in source
    assert "leader-only request submission and all-rank stepping" in source
    assert "llm_engine.step()" in source
    assert "engine_wrapper._add_request(" in source
    assert "torch.distributed.broadcast_object_list(status_payload" in source


def test_gym_scheduler_can_be_instantiated_without_infer_engine():
    scheduler = GYMScheduler(max_turns=4, gym_env="fake_gym")
    assert scheduler.max_turns == 4
    assert scheduler.gym_env_name == "fake_gym"


def test_colocate_episode_driver_leader_path_produces_consistent_outputs():
    module = _load_colocate_driver_module()
    envs["fake_gym"] = _FakeGymEnv
    context_managers["fake_ctx"] = _FakeGymContext
    _FakeGymEnv.closed_sessions.clear()
    try:
        first = _memorygym_like_request()
        second = deepcopy(first)
        second.uuid = "traj-2"
        executor = _LoopbackCommandExecutor()
        infer = _FakeDriverInfer()
        scheduler = GYMScheduler(max_turns=4, gym_env="fake_gym", context_manager="fake_ctx")
        driver = module.ColocateEpisodeDriver(
            executor=executor,
            scheduler=scheduler,
            infer_fn=infer,
            request_config=RequestConfig(max_tokens=32, n=1),
            local_rank_in_group=0,
            local_input_lengths=(2,),
            extract_logprobs_fn=lambda choice: [],
            is_leader=True,
        )

        outputs = driver.run([first, second])
    finally:
        envs.pop("fake_gym", None)
        context_managers.pop("fake_ctx", None)

    assert len(outputs) == 2
    assert all(output.rollout_infos["total_reward"] == 1.0 for output in outputs)
    assert all(output.rollout_infos["step_rewards"] == [0.25, 0.75] for output in outputs)
    assert [command.command_type for command in executor.commands] == [
        module.COMMAND_INIT,
        module.COMMAND_GENERATE,
        module.COMMAND_STOP,
    ]
    assert infer.calls == [["traj-1", "traj-2"], ["traj-1", "traj-2"]]


def test_colocate_episode_driver_follower_never_touches_scheduler():
    module = _load_colocate_driver_module()
    fake_output = RolloutOutput(
        response=ChatCompletionResponse(
            model="fake-model",
            choices=[
                ChatCompletionResponseChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content="done"),
                    finish_reason="stop",
                    token_ids=[1, 2],
                )
            ],
            usage=UsageInfo(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )
    )

    class _ForbiddenScheduler:
        def prepare_request(self, *_args, **_kwargs):
            raise AssertionError("follower should not prepare requests")

        def advance(self, *_args, **_kwargs):
            raise AssertionError("follower should not advance env state")

    infer = _FakeDriverInfer()
    executor = _ScriptedCommandExecutor(
        [
            module.TPGroupCommand(
                command_type=module.COMMAND_INIT,
                turn_id=1,
                infer_requests=[_memorygym_like_request()],
                metadata={"stage": "test", "batch_size": 1},
            ),
            module.TPGroupCommand(
                command_type=module.COMMAND_STOP,
                turn_id=1,
                rank_outputs=[[], [fake_output]],
                metadata={"stage": "test", "batch_size": 1},
            ),
        ]
    )
    driver = module.ColocateEpisodeDriver(
        executor=executor,
        scheduler=_ForbiddenScheduler(),
        infer_fn=infer,
        request_config=RequestConfig(max_tokens=32, n=1),
        local_rank_in_group=1,
        local_input_lengths=(0, 1),
        extract_logprobs_fn=lambda choice: [],
        is_leader=False,
    )

    outputs = driver.run([_memorygym_like_request()])
    assert outputs == [fake_output]
    assert infer.calls == [["traj-1"]]


def test_colocate_episode_driver_fails_fast_on_turn_mismatch():
    module = _load_colocate_driver_module()
    infer = _FakeDriverInfer()
    executor = _ScriptedCommandExecutor(
        [
            module.TPGroupCommand(
                command_type=module.COMMAND_INIT,
                turn_id=1,
                infer_requests=[_memorygym_like_request()],
                metadata={"stage": "test", "batch_size": 1},
            ),
            module.TPGroupCommand(
                command_type=module.COMMAND_GENERATE,
                turn_id=3,
                infer_requests=[_memorygym_like_request()],
                metadata={"stage": "test", "batch_size": 1},
            ),
        ]
    )
    driver = module.ColocateEpisodeDriver(
        executor=executor,
        scheduler=object(),
        infer_fn=infer,
        request_config=RequestConfig(max_tokens=32, n=1),
        local_rank_in_group=0,
        local_input_lengths=(1,),
        extract_logprobs_fn=lambda choice: [],
        is_leader=False,
    )

    try:
        driver.run([_memorygym_like_request()])
    except RuntimeError as exc:
        assert "expected=2 got=3" in str(exc)
    else:
        raise AssertionError("expected turn mismatch to raise RuntimeError")


def test_gym_scheduler_source_normalizes_memorygym_aliases():
    source = Path(
        "packages/affine_ms_swift/vendor/ms_swift_fork/swift/rollout/multi_turn.py"
    ).read_text(encoding="utf-8")

    assert "alias_map = {" in source
    assert "'memorygym': 'memorygym_env'" in source


def test_profiling_context_source_logs_locally():
    source = Path(
        "packages/affine_ms_swift/vendor/ms_swift_fork/swift/rlhf_trainers/utils.py"
    ).read_text(encoding="utf-8")

    assert "logger.info(f'[profiling:start] {stage_name}')" in source
    assert "logger.info(f'[profiling:end] {stage_name} took={duration:.6f}s')" in source
    assert "def safe_gather_variable_tensor(" in source
    assert "[collective:pre]" in source


def test_rollout_mixin_source_uses_colocate_driver_for_tp_multi_turn():
    source = Path(
        "packages/affine_ms_swift/vendor/ms_swift_fork/swift/rlhf_trainers/rollout_mixin.py"
    ).read_text(encoding="utf-8")

    assert "from .colocate_driver import ColocateEpisodeDriver, TorchTPGroupCommandExecutor, gather_rank_metadata" in source
    assert "def _colocate_multi_turn_driver(" in source
    assert "driver = ColocateEpisodeDriver(" in source
    assert "return driver.run(global_requests)" in source


def test_rollout_mixin_source_propagates_gym_fields_in_colocate_and_scheduler():
    source = Path(
        "packages/affine_ms_swift/vendor/ms_swift_fork/swift/rlhf_trainers/rollout_mixin.py"
    ).read_text(encoding="utf-8")

    assert "self.use_gym_env = bool(getattr(args, 'use_gym_env', False))" in source
    assert "aggressive_empty_cache()" in source
    assert "gym_env=getattr(args, 'gym_env', None)," in source
    assert "context_manager=getattr(args, 'context_manager', None)," in source


def test_rlhf_args_source_sets_cpu_device_map_for_single_process_grpo_colocate():
    source = Path(
        "packages/affine_ms_swift/vendor/ms_swift_fork/swift/arguments/rlhf_args.py"
    ).read_text(encoding="utf-8")

    assert "self.use_vllm and self.vllm_mode == 'colocate' and self.device_map is None and not is_mp()" in source
    assert "self.device_map = 'cpu'" in source


def test_rollout_mixin_source_guards_grpo_max_model_len_cleanup():
    source = Path(
        "packages/affine_ms_swift/vendor/ms_swift_fork/swift/rlhf_trainers/rollout_mixin.py"
    ).read_text(encoding="utf-8")

    assert "patched_max_model_len = False" in source
    assert "if patched_max_model_len and hasattr(self.engine, 'set_grpo_max_model_len'):" in source
