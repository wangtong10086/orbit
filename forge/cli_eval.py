"""Evaluation CLI family."""

import json
import click

from forge.pipeline.eval import EvaluationPipeline


@click.group()
def eval():
    """Evaluation commands."""
    pass


@eval.command(name="run")
@click.option("--model", required=True, help="Model path or identifier")
@click.option("--envs", default="GAME,NAVWORLD,LIVEWEB", help="Comma-separated environments")
@click.option("--samples", default=100, type=int, help="Samples per environment")
@click.option("--base-url", default="http://172.17.0.1:30000/v1", help="Inference API base URL")
@click.option("--output-dir", default="", help="Directory for raw eval artifacts")
@click.option("--concurrency", default=5, type=int, help="Per-environment concurrency")
@click.option("--seed", default=42, type=int, help="Random seed")
@click.option("--affinetes-dir", default="/root/affinetes", help="affinetes repo path")
@click.option("--api-key", default="", help="API key for eval environments")
@click.option("--skip-build/--build", default=True, help="Skip rebuilding eval images")
@click.option("--json", "as_json", is_flag=True, help="Print JSON summary")
def run(model, envs, samples, base_url, output_dir, concurrency, seed, affinetes_dir, api_key, skip_build, as_json):
    """Run the real evaluation pipeline."""
    env_list = [env.strip() for env in envs.split(",") if env.strip()]
    pipeline = EvaluationPipeline(envs=env_list)
    report = pipeline.run(
        model_path=model,
        samples_per_env=samples,
        base_url=base_url,
        output_dir=output_dir,
        concurrency=concurrency,
        seed=seed,
        affinetes_dir=affinetes_dir,
        api_key=api_key,
        skip_build=skip_build,
    )
    if as_json:
        click.echo(
            json.dumps(
                {
                    "model_path": report.model_path,
                    "geo_mean": report.geo_mean,
                    "results": {
                        name: {
                            "mean_score": result.mean_score,
                            "sample_count": result.sample_count,
                            "completeness": result.completeness,
                        }
                        for name, result in report.results.items()
                    },
                },
                indent=2,
            )
        )
    else:
        click.echo(report.summary())
