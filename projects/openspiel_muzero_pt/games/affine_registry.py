from __future__ import annotations

from dataclasses import dataclass

from .game_spec import GameSpec, TASK_ID_STRIDE


OTHELLO_TASK_ID = 400_000_000
HEX_TASK_IDS = [600_000_000 + index for index in range(4)]
CLOBBER_TASK_IDS = [700_000_000 + index for index in range(3)]


@dataclass(slots=True)
class DecodedTask:
    family: str
    index: int
    config_id: int


class AffineTaskRegistry:
    def __init__(self, specs: list[GameSpec]):
        self._specs_by_task_id = {spec.task_id: spec for spec in specs}
        self._families: dict[str, list[GameSpec]] = {}
        for spec in specs:
            self._families.setdefault(spec.family, []).append(spec)
        for family_specs in self._families.values():
            family_specs.sort(key=lambda item: item.task_id)

    def __iter__(self):
        return iter(self._specs_by_task_id.values())

    def all_specs(self) -> list[GameSpec]:
        return list(self._specs_by_task_id.values())

    def families(self) -> tuple[str, ...]:
        return tuple(sorted(self._families))

    def decode_task_id(self, task_id: int) -> DecodedTask:
        task_id = int(task_id)
        index = task_id // TASK_ID_STRIDE
        config_id = task_id % TASK_ID_STRIDE
        family_by_index = {4: "othello", 6: "hex", 7: "clobber"}
        if index not in family_by_index:
            raise KeyError(f"Unsupported Affine OpenSpiel task id: {task_id}")
        return DecodedTask(family=family_by_index[index], index=index, config_id=config_id)

    def get_spec(self, task_id: int) -> GameSpec:
        task_id = int(task_id)
        try:
            return self._specs_by_task_id[task_id]
        except KeyError as exc:
            decoded = self.decode_task_id(task_id)
            if decoded.family == "hex":
                task_id = HEX_TASK_IDS[decoded.config_id % len(HEX_TASK_IDS)]
            elif decoded.family == "clobber":
                task_id = CLOBBER_TASK_IDS[decoded.config_id % len(CLOBBER_TASK_IDS)]
            elif decoded.family == "othello":
                task_id = OTHELLO_TASK_ID
            try:
                return self._specs_by_task_id[task_id]
            except KeyError as inner_exc:
                raise KeyError(f"No GameSpec registered for task_id={task_id}") from inner_exc

    def family_specs(self, family: str) -> list[GameSpec]:
        return list(self._families[family])


DEFAULT_REGISTRY = AffineTaskRegistry(
    specs=[
        GameSpec(
            family="othello",
            variant_name="othello_8x8",
            task_id=OTHELLO_TASK_ID,
            board_h=8,
            board_w=8,
            pad_h=8,
            pad_w=8,
            input_channels=5,
            action_dim=65,
            max_game_length=128,
            uses_transpose_canonicalization=False,
            baseline_max_simulations=1000,
            baseline_n_rollouts=20,
            game_name="othello",
            game_params={},
        ),
        GameSpec(
            family="hex",
            variant_name="hex_5",
            task_id=HEX_TASK_IDS[0],
            board_h=5,
            board_w=5,
            pad_h=11,
            pad_w=11,
            input_channels=5,
            action_dim=121,
            max_game_length=25,
            uses_transpose_canonicalization=True,
            baseline_max_simulations=1000,
            baseline_n_rollouts=50,
            game_name="hex",
            game_params={"board_size": 5, "swap": False},
        ),
        GameSpec(
            family="hex",
            variant_name="hex_7",
            task_id=HEX_TASK_IDS[1],
            board_h=7,
            board_w=7,
            pad_h=11,
            pad_w=11,
            input_channels=5,
            action_dim=121,
            max_game_length=49,
            uses_transpose_canonicalization=True,
            baseline_max_simulations=1000,
            baseline_n_rollouts=50,
            game_name="hex",
            game_params={"board_size": 7, "swap": False},
        ),
        GameSpec(
            family="hex",
            variant_name="hex_9",
            task_id=HEX_TASK_IDS[2],
            board_h=9,
            board_w=9,
            pad_h=11,
            pad_w=11,
            input_channels=5,
            action_dim=121,
            max_game_length=81,
            uses_transpose_canonicalization=True,
            baseline_max_simulations=1000,
            baseline_n_rollouts=50,
            game_name="hex",
            game_params={"board_size": 9, "swap": False},
        ),
        GameSpec(
            family="hex",
            variant_name="hex_11",
            task_id=HEX_TASK_IDS[3],
            board_h=11,
            board_w=11,
            pad_h=11,
            pad_w=11,
            input_channels=5,
            action_dim=121,
            max_game_length=121,
            uses_transpose_canonicalization=True,
            baseline_max_simulations=1000,
            baseline_n_rollouts=50,
            game_name="hex",
            game_params={"board_size": 11, "swap": False},
        ),
        GameSpec(
            family="clobber",
            variant_name="clobber_5",
            task_id=CLOBBER_TASK_IDS[0],
            board_h=5,
            board_w=5,
            pad_h=7,
            pad_w=7,
            input_channels=5,
            action_dim=196,
            max_game_length=24,
            uses_transpose_canonicalization=False,
            baseline_max_simulations=1500,
            baseline_n_rollouts=100,
            game_name="clobber",
            game_params={"rows": 5, "columns": 5},
        ),
        GameSpec(
            family="clobber",
            variant_name="clobber_6",
            task_id=CLOBBER_TASK_IDS[1],
            board_h=6,
            board_w=6,
            pad_h=7,
            pad_w=7,
            input_channels=5,
            action_dim=196,
            max_game_length=35,
            uses_transpose_canonicalization=False,
            baseline_max_simulations=1500,
            baseline_n_rollouts=100,
            game_name="clobber",
            game_params={"rows": 6, "columns": 6},
        ),
        GameSpec(
            family="clobber",
            variant_name="clobber_7",
            task_id=CLOBBER_TASK_IDS[2],
            board_h=7,
            board_w=7,
            pad_h=7,
            pad_w=7,
            input_channels=5,
            action_dim=196,
            max_game_length=48,
            uses_transpose_canonicalization=False,
            baseline_max_simulations=1500,
            baseline_n_rollouts=100,
            game_name="clobber",
            game_params={"rows": 7, "columns": 7},
        ),
    ]
)
