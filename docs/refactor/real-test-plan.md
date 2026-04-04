# 真实测试计划

当变更涉及以下任一内容时，不能只跑单元测试：

- runtime 行为
- 远程执行路径
- control -> execution 提交流程
- provider / target 选择逻辑
- 训练 / 评测 / 采集的实际执行路径

## 记录要求

每次真实测试都应记录：

- 日期
- 命令
- placement
- launch mode
- target / machine
- image
- 关键日志路径
- 关键产物路径
- 结果

## 当前适用的真实测试清单

### R1. Local Docker Worker Smoke

目标：

- 验证 bundle 能在本地 Docker 中执行

建议步骤：

1. `python -m forge control prepare train ...`
2. `python -m forge worker validate-bundle ...`
3. `python -m forge worker run ... --placement local --launch-mode docker_image --foreground`
4. `python -m forge worker collect ...`

### R2. Targon Rental Worker Smoke

目标：

- 验证 Targon rental runtime 的 staging、远程执行、状态查询、日志与产物收集

建议步骤：

1. `python -m forge worker run ... --placement targon_rental --launch-mode host_process --target <isolated-rental>`
2. `python -m forge worker status ...`
3. `python -m forge worker logs ...`
4. `python -m forge worker collect ...`

### R3. Control -> Targon Submit Smoke

目标：

- 验证 control plane 提交、run record、status、logs、collect 的闭环

建议步骤：

1. `python -m forge control experiment create ...`
2. `python -m forge control submit train ... --template targon-rental-host --target <isolated-rental>`
3. `python -m forge control run status ...`
4. `python -m forge control run logs ...`
5. `python -m forge control run collect ...`

### R4. Collect/Eval 真实执行验证

目标：

- 验证 collect 与 eval bundle 不仅能渲染，还能在真实执行环境中完成

建议步骤：

- 分别针对 `prepare collect` / `submit collect`
- 分别针对 `prepare eval` / `submit eval`

## 隔离要求

涉及 Targon rental 时：

- 不默认使用现有 `machines.json` 里的任意生产机器
- 使用隔离的、专门为验证准备的 rental 机器
- 在记录中明确写出该机器是验证机器

## 当前状态

本轮已执行的真实验证：

1. Local host-process worker smoke
   - 使用最小 generic bundle
   - `placement=local`
   - `launch_mode=host_process`
   - 结果：成功

2. Local docker worker smoke
   - 使用最小 generic bundle
   - `placement=local`
   - `launch_mode=docker_image`
   - `image=bash:5.2`
   - 结果：成功

3. Control prepare train + worker validate-bundle
   - 结果：成功

4. Control submit collect on local-host template
   - `env=GAME`
   - `game=othello`
   - `template=local-host`
   - 结果：成功

5. Targon rental worker smoke
   - 日期：`2026-04-04`
   - machine: `affine-refactor-validation-h200x1`
   - workload: `wrk-pvsfcppud27o`
   - host: `72.46.85.157:30559`
   - placement: `targon_rental`
   - launch_mode: `docker_image`
   - image: `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel`
   - bundle: `/tmp/affine-smoke-targon-worker`
   - 命令：
     - `python -m forge worker run /tmp/affine-smoke-targon-worker --placement targon_rental --launch-mode docker_image --target affine-refactor-validation-h200x1 --image pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel --foreground`
     - `python -m forge worker status /tmp/affine-smoke-targon-worker`
     - `python -m forge worker logs /tmp/affine-smoke-targon-worker --tail 50`
     - `python -m forge worker collect /tmp/affine-smoke-targon-worker`
   - 关键日志：
     - `logs/real-tests/2026-04-04/targon-validation/worker-run.json`
     - `logs/real-tests/2026-04-04/targon-validation/worker-status.json`
     - `logs/real-tests/2026-04-04/targon-validation/worker-logs-after-fix.txt`
     - `logs/real-tests/2026-04-04/targon-validation/worker-collect.json`
   - 结果：成功

6. Control -> Targon submit smoke
   - 日期：`2026-04-04`
   - machine: `affine-refactor-validation-h200x1`
   - workload: `wrk-pvsfcppud27o`
   - host: `72.46.85.157:30559`
   - placement: `targon_rental`
   - launch_mode: `docker_image`
   - template: `targon-rental-docker`
   - real task: `collect(NAVWORLD, n=1)`
   - experiment dir: `/tmp/affine-smoke-control-targon-nav`
   - 命令：
     - `python -m forge control --dir /tmp/affine-smoke-control-targon-nav experiment create --id v-collect-targon-nav ...`
     - `python -m forge control --dir /tmp/affine-smoke-control-targon-nav submit collect v-collect-targon-nav --template targon-rental-docker --env NAVWORLD -n 1 -o navworld.jsonl --bundle-dir /tmp/affine-smoke-control-targon-nav/bundle --target affine-refactor-validation-h200x1 --foreground`
     - `python -m forge control --dir /tmp/affine-smoke-control-targon-nav run status v-collect-targon-nav collect`
     - `python -m forge control --dir /tmp/affine-smoke-control-targon-nav run logs v-collect-targon-nav collect --tail 50`
     - `python -m forge control --dir /tmp/affine-smoke-control-targon-nav run collect v-collect-targon-nav collect`
   - 关键日志：
     - `logs/real-tests/2026-04-04/targon-validation/control-submit-navworld-run.json`
     - `logs/real-tests/2026-04-04/targon-validation/control-run-status.json`
     - `logs/real-tests/2026-04-04/targon-validation/control-run-logs.txt`
     - `logs/real-tests/2026-04-04/targon-validation/control-run-collect.json`
   - 关键产物：
     - `/tmp/affine-smoke-control-targon-nav/bundle/artifacts/staging/navworld.jsonl`
     - `/tmp/affine-smoke-control-targon-nav/bundle/artifacts/publish_result.json`
     - `/tmp/affine-smoke-control-targon-nav/bundle/artifacts/mixed/mixed-train.parquet`
   - 结果：成功

本轮真实验证中出现的非阻塞问题：

- `GAME/othello` 在远端默认 image 上缺少 `pyspiel`，因此不适合作为当前 Targon collect smoke
- foreground Targon docker logs 回退和 bannered-host 下载回退都在本轮真实验证中暴露，并已修复

## Targon Direct-Image Host Validation

日期：`2026-04-04`

1. Targon rental host-process worker smoke
   - workload: `wrk-trnf5w09ih95`
   - machine: `affine-targon-host-dropbear-h200`
   - host: `72.46.85.157:32753`
   - image: `wangtong123/affine-forge:latest`
   - placement: `targon_rental`
   - launch_mode: `host_process`
   - bundle: `/tmp/affine-targon-host-worker`
   - commands:
     - `python -m forge worker validate-bundle /tmp/affine-targon-host-worker`
     - `python -m forge worker run /tmp/affine-targon-host-worker --placement targon_rental --launch-mode host_process --target affine-targon-host-dropbear-h200 --foreground`
     - `python -m forge worker status /tmp/affine-targon-host-worker`
     - `python -m forge worker logs /tmp/affine-targon-host-worker --tail 50`
     - `python -m forge worker collect /tmp/affine-targon-host-worker`
   - result: success

2. Control -> Targon host-process submit smoke
   - experiment dir: `/tmp/affine-targon-host-control`
   - task: `collect(NAVWORLD, n=1)`
   - template: `targon-rental-host`
   - commands:
     - `python -m forge control --dir /tmp/affine-targon-host-control experiment create --id v-targon-host-nav ...`
     - `python -m forge control --dir /tmp/affine-targon-host-control submit collect v-targon-host-nav --template targon-rental-host --env NAVWORLD -n 1 -o navworld.jsonl --bundle-dir /tmp/affine-targon-host-control/bundle --target affine-targon-host-dropbear-h200 --foreground`
     - `python -m forge control --dir /tmp/affine-targon-host-control run status v-targon-host-nav collect`
     - `python -m forge control --dir /tmp/affine-targon-host-control run logs v-targon-host-nav collect --tail 100`
     - `python -m forge control --dir /tmp/affine-targon-host-control run collect v-targon-host-nav collect`
   - result: success

## M5-M9 回归记录

日期：`2026-04-04`

1. Local host worker smoke
   - bundle: `/tmp/affine-m5m9-worker-host`
   - commands:
     - `python -m forge worker validate-bundle /tmp/affine-m5m9-worker-host`
     - `python -m forge worker run /tmp/affine-m5m9-worker-host --placement local --launch-mode host_process --foreground`
     - `python -m forge worker status /tmp/affine-m5m9-worker-host`
     - `python -m forge worker logs /tmp/affine-m5m9-worker-host --tail 20`
     - `python -m forge worker collect /tmp/affine-m5m9-worker-host`
   - evidence:
     - `logs/real-tests/2026-04-04/m5-m9-validation/local-worker-host/status.json`
     - `logs/real-tests/2026-04-04/m5-m9-validation/local-worker-host/logs.txt`
     - `logs/real-tests/2026-04-04/m5-m9-validation/local-worker-host/collect.json`
   - result: success

2. Local docker worker smoke
   - bundle: `/tmp/affine-m5m9-worker-docker`
   - image: `bash:5.2`
   - commands:
     - `python -m forge worker run /tmp/affine-m5m9-worker-docker --placement local --launch-mode docker_image --image bash:5.2 --foreground`
     - `python -m forge worker collect /tmp/affine-m5m9-worker-docker`
     - `python -m forge worker logs /tmp/affine-m5m9-worker-docker --tail 20`
   - evidence:
     - `logs/real-tests/2026-04-04/m5-m9-validation/local-worker-docker/status.json`
     - `logs/real-tests/2026-04-04/m5-m9-validation/local-worker-docker/logs.txt`
     - `logs/real-tests/2026-04-04/m5-m9-validation/local-worker-docker/collect.json`
   - result: success

3. Local control submit smoke
   - experiment dir: `/tmp/affine-m5m9-debug`
   - task: `collect(GAME, game=othello, n=1)`
   - commands:
     - `python -m forge control --dir /tmp/affine-m5m9-debug experiment create --id v-debug ...`
     - `python -m forge control --dir /tmp/affine-m5m9-debug submit collect v-debug --template local-host --env GAME -n 1 -o game.jsonl --game othello --bundle-dir /tmp/affine-m5m9-debug/bundle --foreground`
     - `python -m forge control --dir /tmp/affine-m5m9-debug run status v-debug collect`
     - `python -m forge control --dir /tmp/affine-m5m9-debug run logs v-debug collect --tail 30`
     - `python -m forge control --dir /tmp/affine-m5m9-debug run collect v-debug collect`
   - result: success

4. Targon rental worker smoke
   - workload: `wrk-65rlqubugtj0`
   - machine: `affine-m5-m9-validation-h200x1`
   - host: `72.46.85.157:31673`
   - image: `pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel`
   - commands:
     - `python -m forge worker run /tmp/affine-m5m9-worker-docker --placement targon_rental --launch-mode docker_image --target affine-m5-m9-validation-h200x1 --image pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel --foreground`
     - `python -m forge worker status /tmp/affine-m5m9-worker-docker`
     - `python -m forge worker logs /tmp/affine-m5m9-worker-docker --tail 50`
     - `python -m forge worker collect /tmp/affine-m5m9-worker-docker`
   - provisioning fix:
     - installed `nvidia-container-toolkit`
     - set `no-cgroups = true`
     - restarted docker
   - evidence:
     - `logs/real-tests/2026-04-04/m5-m9-validation/targon/workload.json`
     - `logs/real-tests/2026-04-04/m5-m9-validation/targon/nvidia-toolkit-install.log`
   - result: success

5. Control -> Targon submit smoke
   - experiment dir: `/tmp/affine-m5m9-control-targon-nav`
   - task: `collect(NAVWORLD, n=1)`
   - commands:
     - `python -m forge control --dir /tmp/affine-m5m9-control-targon-nav experiment create --id v-m5m9-targon-nav ...`
     - `python -m forge control --dir /tmp/affine-m5m9-control-targon-nav submit collect v-m5m9-targon-nav --template targon-rental-docker --env NAVWORLD -n 1 -o navworld.jsonl --bundle-dir /tmp/affine-m5m9-control-targon-nav/bundle --target affine-m5-m9-validation-h200x1 --foreground`
     - `python -m forge control --dir /tmp/affine-m5m9-control-targon-nav run status v-m5m9-targon-nav collect`
     - `python -m forge control --dir /tmp/affine-m5m9-control-targon-nav run logs v-m5m9-targon-nav collect --tail 50`
     - `python -m forge control --dir /tmp/affine-m5m9-control-targon-nav run collect v-m5m9-targon-nav collect`
   - evidence:
     - `logs/real-tests/2026-04-04/m5-m9-validation/targon/control-status.json`
     - `logs/real-tests/2026-04-04/m5-m9-validation/targon/control-logs.txt`
   - `logs/real-tests/2026-04-04/m5-m9-validation/targon/control-collect.json`
   - result: success

   cleanup:
   - validation workload `wrk-65rlqubugtj0` deleted after evidence capture
   - local `machines.json` restored to pre-validation state
