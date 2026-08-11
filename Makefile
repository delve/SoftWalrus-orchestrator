
# todo: make idempotent
setup:
	curl -LsSf https://astral.sh/uv/install.sh | sh
	uv venv
	uv pip install -e .

# todo: this fails for some stupid make reason.
# $ make venv
# source .venv/bin/activate
# make: source: No such file or directory
# make: *** [Makefile:9: venv] Error 127
venv:
	source .venv/bin/activate

# todo: make this a dependency
sync:
	uv sync

