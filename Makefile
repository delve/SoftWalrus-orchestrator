
# todo: make idempotent
setup:
	curl -LsSf https://astral.sh/uv/install.sh | sh
	uv venv
	uv pip install -e .

venv:
	source .venv/bin/activate

# todo: make this a dependency
sync:
	uv sync

