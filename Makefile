IMAGE ?= wangtong123/orbit
TAG   ?= latest

.PHONY: lint format check docker-build docker-push bootstrap score

# ─── Development ───────────────────────────────────────────────────
lint:
	ruff check orbit/ scripts/

format:
	ruff format orbit/ scripts/

check:
	python -m compileall -q orbit/ scripts/

# ─── Docker ────────────────────────────────────────────────────────
docker-build:
	docker build -t $(IMAGE):$(TAG) -f orbit/setup/Dockerfile .

docker-push: docker-build
	docker push $(IMAGE):$(TAG)

# ─── Targon ────────────────────────────────────────────────────────
bootstrap:
	python3 -m orbit rental bootstrap --training

bootstrap-check:
	python3 -m orbit rental bootstrap --check

# ─── Monitoring ────────────────────────────────────────────────────
score:
	python3 -m orbit score --top 10
