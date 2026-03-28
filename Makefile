IMAGE ?= wangtong123/affine-forge
TAG   ?= latest

.PHONY: lint format check docker-build docker-push bootstrap score

# ─── Development ───────────────────────────────────────────────────
lint:
	ruff check forge/ scripts/

format:
	ruff format forge/ scripts/

check:
	python -m compileall -q forge/ scripts/

# ─── Docker ────────────────────────────────────────────────────────
docker-build:
	docker build -t $(IMAGE):$(TAG) -f forge/setup/Dockerfile .

docker-push: docker-build
	docker push $(IMAGE):$(TAG)

# ─── Targon ────────────────────────────────────────────────────────
bootstrap:
	python3 -m forge rental bootstrap --training

bootstrap-check:
	python3 -m forge rental bootstrap --check

# ─── Monitoring ────────────────────────────────────────────────────
score:
	python3 -m forge score --top 10
